#!/usr/bin/env python3
"""backfill.py —— 把既有 11 卷档案回填成库内 works/<id>/ 数据。

来源：/workspace/01_最终交付/ 下所有含 00_总览.md 的作品目录。
产出：profile.json + beats.jsonl（grid/t0/t1/visual/sub）+ backfill_report.json。

原则：
- 只搬档案原文，不生成任何新描述。visual 直接取 09 卷 c_NN 块正文。
- 解析不出来就留空，绝不猜。shot/move/speech/func 一律 null/[]，因为档案里没有逐格结构化字段。
- 每格 note 标注来源为 backfill，与「本次亲读」区分开。

用法：
    python3 _pipeline/backfill.py --dry-run          # 只看解析率，不落盘
    python3 _pipeline/backfill.py --apply            # 正式回填
    python3 _pipeline/backfill.py --apply --only 逃出大英博物馆
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from kbtext import demd  # noqa: E402  去 markdown 渲染标记

ROOT = Path(__file__).resolve().parent.parent
SRC = Path("/workspace/01_最终交付")

C_HEAD = re.compile(r"^\*\*c_(\d+)（(\d+)–(\d+)s）\*\*")
# 字幕写法至少有三种：字幕「…」/ 字幕=「…」/ 字幕：「…」
SUB_RE = re.compile(r"字幕\s*[=＝：:]?\s*「([^」]*)」")
# 兜底：有的作品通篇不用「字幕」二字，直接以引号标台词（野生布里茨《山鸟》）
QUOTE_RE = re.compile(r"「([^「」]{2,60})」")
SEC_LINE = re.compile(r"^(\d{3,4})s\s+")
CELL = re.compile(r"^\|\s*([^|]+?)\s*\|\s*([^|]*?)\s*\|")

# 博主目录名 → (name, aliases)。不做任何推断归并：档案自己说「发布账号待确认」的，
# 就老老实实单列一个 creator，绝不因为「看起来是同一团队」就合账。
CREATOR_ALIAS = {
    "煎饼果仔（张问初）": ("煎饼果仔", ["张问初"]),
    "晒月光（短剧）": ("晒月光（短剧）", []),
}

CN_NUM = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
          "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}


def cn2int(s: str) -> int | None:
    if s.isdigit():
        return int(s)
    if s in CN_NUM:
        return CN_NUM[s]
    if s.startswith("十") and len(s) == 2 and s[1] in CN_NUM:
        return 10 + CN_NUM[s[1]]
    if len(s) == 2 and s[0] in CN_NUM and s[1] in CN_NUM:
        return CN_NUM[s[0]] * 10 + CN_NUM[s[1]]
    return None


def episode_of(title: str) -> int | None:
    m = re.search(r"第([一二三四五六七八九十\d]+)集", title)
    return cn2int(m.group(1)) if m else None


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def read(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="replace") if p.exists() else ""


def kv_table(md: str) -> dict[str, str]:
    """从 00 卷的「| 项 | 值 |」表里取键值。"""
    out: dict[str, str] = {}
    for line in md.splitlines():
        m = CELL.match(line)
        if not m:
            continue
        k, v = m.group(1).strip(), m.group(2).strip()
        if k in ("项", "---") or k.startswith("---") or not v:
            continue
        out.setdefault(k, v)
    return out


def pick(kv: dict[str, str], *keys: str) -> str | None:
    for k in keys:
        for kk, vv in kv.items():
            if k in kk:
                return vv
    return None


def clean(v: str | None) -> str | None:
    if v is None:
        return None
    return v.replace("**", "").replace("`", "").strip() or None


def parse_duration_s(text: str | None) -> float | None:
    text = clean(text)
    if not text:
        return None
    m = re.search(r"([\d.]+)\s*(?:s\b|秒)", text)
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            return None
    m = re.search(r"(\d+):(\d+(?:\.\d+)?)", text)  # 2:43.77
    if m:
        return round(int(m.group(1)) * 60 + float(m.group(2)), 3)
    return None


def parse_spec(text: str | None) -> dict:
    if not text:
        return {}
    out: dict = {}
    m = re.search(r"(\d{2,5})\s*[×x]\s*(\d{2,5})", text)
    if m:
        out["width"], out["height"] = int(m.group(1)), int(m.group(2))
    m = re.search(r"([\d.]+)\s*fps", text, re.I)
    if m:
        out["fps"] = float(m.group(1))
    m = re.search(r"\b(h26[45]|hevc|av1)\b", text, re.I)
    if m:
        out["codec"] = m.group(1).lower()
    return out


def parse_platform(text: str | None) -> dict:
    out = {"digg": None, "comment": None, "share": None, "collect": None,
           "play": None, "hashtags": [], "music": None}
    if not text:
        return out
    for key, pat in (("digg", r"点赞\s*([\d,]+)"), ("comment", r"评论\s*([\d,]+)"),
                     ("share", r"转发\s*([\d,]+)"), ("collect", r"收藏\s*([\d,]+)"),
                     ("play", r"播放\s*([\d,]+)")):
        m = re.search(pat, text)
        if m:
            out[key] = int(m.group(1).replace(",", ""))
    return out


LAST_ANOMALY: dict = {}


def parse_beats(md: str, wid: str) -> list[dict]:
    """解析 09 卷的 c_NN 块。返回 beats 列表（按格号排序）。

    兼容两类档案缺陷（均已实证）：
    1. 合并标题：`**c_20（76–79s）–c_21（80–83s）** 076s…083s 同一长镜`
       —— 一行登记两格，正文共用，需拆成两个 beat。
    2. 物理乱序：c_96/c_97 被写到文档中段，c_90–c_95 在文末
       —— 按格号重排，不按文档顺序。
    """
    lines = md.splitlines()
    quote_mode = len(SUB_RE.findall(md)) < 5   # 几乎不用「字幕「…」」→ 改用引号兜底
    blocks: list[tuple[int, list[tuple[int, int, int]], str]] = []
    for i, ln in enumerate(lines):
        s = ln.strip()
        if not s.startswith("**"):
            continue
        close = s.find("**", 2)
        if close < 0:
            continue
        head, rest = s[2:close], s[close + 2:].strip()
        cells: list[tuple[int, int, int]] = []
        for m in re.finditer(r"c_(\d+)(?:–c_(\d+))?（(\d+)–(\d+)s）", head):
            n1 = int(m.group(1))
            n2 = int(m.group(2)) if m.group(2) else n1
            for n in range(n1, n2 + 1):      # 范围式 c_81–c_82（320–327s）展开成两格
                cells.append((n, int(m.group(3)), int(m.group(4))))
        if cells:
            blocks.append((i, cells, rest))

    raw: list[dict] = []
    merged_blocks = 0
    doc_order: list[int] = []
    for bi, (li, cells, inline) in enumerate(blocks):
        end = blocks[bi + 1][0] if bi + 1 < len(blocks) else len(lines)
        if len(cells) > 1:
            merged_blocks += 1
        doc_order.extend(n for n, _a, _b in cells)
        body: list[str] = [inline] if inline else []
        for ln in lines[li + 1:end]:
            s = ln.strip()
            if not s or s.startswith("#") or s.startswith(">") or s.startswith("---"):
                continue
            s = SEC_LINE.sub("", s)          # 去掉逐秒行首的 000s
            body.append(s)
        text = " ".join(x for x in body if x).strip()
        subs: list[str] = []
        pat = QUOTE_RE if quote_mode else SUB_RE
        for m in pat.finditer(text):
            # 档案正文里的 `**强调**` 是排版，不是内容：不清就会变成
            # `**山茶**` 这种脏字幕，搜"山茶"搜不到（2026-10-30 全库清洗）。
            v = demd(m.group(1)).strip()
            if v and v not in subs:
                subs.append(v)
        for n, _s0, _s1 in cells:            # 同一段正文分配给合并标题里的每一格
            raw.append({
                "wid": wid,
                "grid": f"c-{n:02d}",
                # 档案写「秒点」区间 [4(N−1), 4(N−1)+3]，库内规则是「连续」区间 [4(N−1), 4N)；
                # 统一转成连续式，末格由 scan() 按实际片长裁齐。
                "t0": 4 * (n - 1),
                "t1": 4 * n,
                "shot": None,
                "move": None,
                "visual": demd(text)[:600] if text else "",
                "sub": " ／ ".join(subs) if subs else None,
                "speech": [],
                "sound": None,
                "music": None,
                "func": [],
                "correction": [],
                "note": "backfill:09卷" + ("；sub 由引号回退提取" if quote_mode else ""),
            })
    raw.sort(key=lambda b: int(b["grid"][2:]))
    LAST_ANOMALY.clear()
    LAST_ANOMALY.update({
        "merged_blocks": merged_blocks,
        "out_of_order": doc_order != sorted(doc_order),
        "max_gap": max((b - a for a, b in zip(sorted(doc_order), sorted(doc_order)[1:])), default=1),
    })
    return raw


def scan() -> list[dict]:
    """扫描源库，返回作品条目。"""
    items: list[dict] = []
    for ov in sorted(SRC.rglob("00_总览.md")):
        d = ov.parent
        rel = d.relative_to(SRC)
        parts = rel.parts
        if len(parts) < 2:
            continue
        creator_dir = parts[0]
        series_dir = parts[1] if len(parts) >= 3 else None
        series_hint = None
        if series_dir and re.search(r"（系列）|\(系列\)", series_dir):
            series_hint = re.sub(r"（系列）|\(系列\)", "", series_dir).strip()
        kv = kv_table(read(ov))
        md09 = read(d / "09_画面实录.md")
        beats = parse_beats(md09, "TMP")
        anomaly = dict(LAST_ANOMALY)
        dur = parse_duration_s(pick(kv, "时长", "片长", "duration"))
        # 末格裁到实际片长：档案末格常写满 4 秒（如 104.5s 片的 c_27 标到 107s）
        if beats and dur:
            last = beats[-1]
            if last["t1"] > dur + 0.01:
                last["t1"] = round(dur, 3)
        items.append({
            "dir": d,
            "rel": str(rel),
            "creator_dir": creator_dir,
            "series_hint": series_hint,
            "raw_title": d.name,
            "title": d.name,
            "aweme_id": clean(pick(kv, "aweme")),
            "published_at": clean(pick(kv, "发布")),
            "duration_s": dur,
            "spec": parse_spec(pick(kv, "画面", "规格")),
            "platform": parse_platform(pick(kv, "数据")),
            "beats": beats,
            "anomaly": anomaly,
            "n_vol": len(list(d.glob("*.md"))),
            "has_srt": (d / "subtitles.srt").exists(),
            "has_05": (d / "05_画面文字.md").exists(),
        })

    # 第二级系列识别：博主目录名（去机构后缀）本身即系列名时，该博主全部作品归入
    # 例：「晒月光（短剧）」下 晒月光第一集／第二集／第一集番外 → 系列「晒月光」
    by_creator: dict[str, list[dict]] = {}
    for it in items:
        by_creator.setdefault(it["creator_dir"], []).append(it)
    for cdir, group in by_creator.items():
        if any(g["series_hint"] for g in group):
            continue
        base = re.sub(r"（[^）]*）|\([^)]*\)", "", cdir).strip()
        if base and any(base in g["raw_title"] for g in group):
            for g in group:
                g["series_hint"] = base

    # title 补上系列名（避免全库一堆同名「第一集」），并抽 episode
    for it in items:
        sh = it["series_hint"]
        if sh and not it["raw_title"].startswith(sh):
            it["title"] = f"{sh} {it['raw_title']}"
        else:
            it["title"] = it["raw_title"]
        it["episode"] = episode_of(it["raw_title"])
        if "番外" in it["raw_title"]:
            it["episode"] = None
    return items


def creator_name(d: str) -> tuple[str, list[str]]:
    if d in CREATOR_ALIAS:
        return CREATOR_ALIAS[d]
    m = re.match(r"^(.*?)（(.+)）$", d)
    if m:
        return m.group(1), [m.group(2)]
    return d, []


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--only", default=None)
    ap.add_argument("--rewrite", action="store_true",
                    help="已存在的作品按 aweme_id 匹配后重写 beats 与 coverage，不新建")
    a = ap.parse_args()
    if not (a.dry_run or a.apply):
        ap.error("需要 --dry-run 或 --apply")

    items = scan()
    if a.only:
        items = [it for it in items if a.only in it["rel"]]

    # 汇总
    print(f"扫描到 {len(items)} 部作品\n")
    print(f"{'作品':40s} {'卷':>3s} {'beats':>5s} {'字幕':>5s} {'时长':>7s} {'系列':>10s}")
    print("-" * 82)
    tot_b = tot_s = 0
    bad: list[str] = []
    for it in items:
        bs = it["beats"]
        nb, ns = len(bs), sum(1 for b in bs if b["sub"])
        nv = sum(1 for b in bs if b["visual"])
        tot_b += nb
        tot_s += ns
        flag = ""
        if nb == 0:
            flag = "  <-- 无 c_NN"
            bad.append(it["rel"])
        elif nv < nb:
            flag = f"  <-- {nb-nv} 格空画面"
        an = it.get("anomaly") or {}
        marks = []
        if an.get("merged_blocks"):
            marks.append(f"{an['merged_blocks']}处合并标题")
        if an.get("out_of_order"):
            marks.append("格号乱序")
        if (an.get("max_gap") or 1) > 1:
            marks.append(f"跳号{an['max_gap']}")
        if marks:
            flag += "  [档案缺陷:" + "/".join(marks) + "]"
        print(f"{it['rel'][:38]:40s} {it['n_vol']:3d} {nb:5d} {ns:5d} "
              f"{(it['duration_s'] or 0):7.1f} {(it['series_hint'] or '-')[:10]:>10s}{flag}")
    print("-" * 76)
    print(f"合计 beats {tot_b}，其中带字幕 {tot_s}（{tot_s/max(1,tot_b)*100:.1f}%）")
    if bad:
        print(f"解析失败 {len(bad)} 部：{bad}")
    print(f"\n博主 {len({it['creator_dir'] for it in items})} 位："
          f"{sorted({it['creator_dir'] for it in items})}")

    if a.dry_run:
        print("\n[dry-run] 未落盘")
        return 0

    # ---- 正式回填 ----
    state_p = ROOT / "_pipeline" / "id_state.json"
    state = json.loads(read(state_p) or "{}") or {"creator": 0, "work": 0, "series": 0}
    # 按磁盘实际最大号校正
    def maxno(pat: str) -> int:
        ns = [int(m.group(1)) for p in ROOT.glob(pat) if (m := re.search(r"-(\d+)$", p.name))]
        return max(ns) if ns else 0
    state["creator"] = max(state.get("creator", 0), maxno("creators/c-*"))
    state["work"] = max(state.get("work", 0), maxno("works/w-*"))

    # 系列映射持久化
    smap_p = ROOT / "_pipeline" / "series_map.json"
    smap: dict[str, str] = json.loads(read(smap_p) or "{}")
    smap_rev = {v: k for k, v in smap.items()}
    state["series"] = max(state.get("series", 0), len(smap))

    # 已有作品索引：aweme_id → wid（查重）
    known: dict[str, str] = {}
    for p in (ROOT / "works").glob("w-*/profile.json"):
        d = json.loads(read(p) or "{}")
        if d.get("aweme_id"):
            known[d["aweme_id"]] = d["id"]
        known[f"title::{d.get('title')}"] = d["id"]

    report = {"generated_at": now(), "source": str(SRC), "items": []}
    for it in items:
        key = it["aweme_id"] or f"title::{it['title']}"
        if key in known and not a.rewrite:
            print(f"跳过（已存在 {known[key]}）：{it['rel']}")
            continue
        # creator
        cname, calias = creator_name(it["creator_dir"])
        cid = None
        for p in (ROOT / "creators").glob("c-*/profile.json"):
            d = json.loads(read(p) or "{}")
            if d.get("name") == cname:
                cid = d["id"]
                break
        if not cid:
            state["creator"] += 1
            cid = f"c-{state['creator']:04d}"
            cd = ROOT / "creators" / cid
            cd.mkdir(parents=True, exist_ok=True)
            (cd / "profile.json").write_text(json.dumps({
                "id": cid, "name": cname, "aliases": calias,
                "douyin_id": None, "homepage": None, "status": "profiled",
                "positioning": "", "format": [], "tags": [], "cadence": None,
                "works_count": 0, "independent_works": 0, "series_ids": [],
                "matrix": {}, "fingerprint_confidence": "none",
                "platform": {"followers": None, "total_likes": None, "captured_at": None},
                "paths": {"index": f"creators/{cid}/index.md",
                          "fingerprint": f"creators/{cid}/fingerprint.md",
                          "matrix": f"creators/{cid}/matrix.md",
                          "trajectory": f"creators/{cid}/trajectory.md"},
                "created_at": now(), "updated": today(),
            }, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
            for page, tpl in (("index", f"# {cname}\n\n> 待补：账号定位与内容矩阵。\n"),
                              ("fingerprint", f"# {cname} · 作者指纹\n\n> 待补：跨作品稳定手法。\n"),
                              ("matrix", f"# {cname} · 内容矩阵\n\n> 待补。\n"),
                              ("trajectory", f"# {cname} · 作品序列\n\n> 待补。\n")):
                f = cd / f"{page}.md"
                if not f.exists():
                    f.write_text(tpl, encoding="utf-8")

        # series
        sid = None
        if it["series_hint"]:
            sid = smap_rev.get(it["series_hint"])
            if not sid:
                state["series"] += 1
                sid = f"s-{state['series']:04d}"
                smap[sid] = it["series_hint"]
                smap_rev[it["series_hint"]] = sid

        # work
        beats = it["beats"]
        if key in known:                      # --rewrite：命中已有作品，只重写 beats 与计数
            wid = known[key]
            wd = ROOT / "works" / wid
            for sub in ("media", "data", "contact", "dossier"):
                (wd / sub).mkdir(parents=True, exist_ok=True)
            for b in beats:
                b["wid"] = wid
            (wd / "beats.jsonl").write_text(
                "\n".join(json.dumps(b, ensure_ascii=False) for b in beats) + ("\n" if beats else ""),
                encoding="utf-8")
            prof = json.loads(read(wd / "profile.json") or "{}")
            prof.setdefault("coverage", {})
            prof["coverage"]["beats_total"] = len(beats)
            prof["coverage"]["beats_registered"] = sum(1 for b in beats if b["visual"])
            if str(prof.get("note") or "").startswith("backfill") and prof.get("status") in (
                    "decomposed", "read"):
                prof["status"] = "backfilled"
            if it["duration_s"]:
                prof["duration_ms"] = int(round(it["duration_s"] * 1000))
            if it["spec"]:
                prof["spec"] = it["spec"]
            prof["updated"] = today()
            (wd / "profile.json").write_text(json.dumps(prof, ensure_ascii=False, indent=1) + "\n",
                                            encoding="utf-8")
            report["items"].append({"wid": wid, "title": it["title"], "src": it["rel"],
                                    "beats": len(beats), "vol": it["n_vol"], "rewrite": True})
            print(f"  ↻ {wid}  {it['title'][:24]:26s} beats {len(beats):3d}  重写")
            continue

        state["work"] += 1
        wid = f"w-{state['work']:04d}"
        wd = ROOT / "works" / wid
        for sub in ("media", "data", "contact", "dossier"):
            (wd / sub).mkdir(parents=True, exist_ok=True)
        for b in beats:
            b["wid"] = wid
        (wd / "beats.jsonl").write_text(
            "\n".join(json.dumps(b, ensure_ascii=False) for b in beats) + ("\n" if beats else ""),
            encoding="utf-8")
        dur_ms = int(round((it["duration_s"] or 0) * 1000)) or (
            int(beats[-1]["t1"] * 1000) if beats else 0)
        prof = {
            "id": wid, "creator_id": cid, "series_id": sid, "episode": it["episode"],
            "title": it["title"], "aweme_id": it["aweme_id"], "url": None,
            "duration_ms": dur_ms, "published_at": it["published_at"],
            "status": "backfilled",
            "platform": it["platform"],
            "source": {"type": "pointer", "path": str(it["dir"]), "sha256": "", "bytes": 0},
            "spec": it["spec"], "tags": ["backfill"],
            "coverage": {"beats_total": len(beats),
                         "beats_registered": sum(1 for b in beats if b["visual"]),
                         "dims_total": 10, "dims_done": 0,
                         "c5_errors": None, "c5_warns": None,
                         "ending_checked": False, "c5_checked_at": None},
            "assessment": {k: None for k in ("hook", "structure", "character", "visual",
                                             "performance", "sound", "text", "edit",
                                             "emotion", "spread")},
            "knowledge_delta": {"added": [], "revised": [], "refuted": [], "none_reason": ""},
            "paths": {"beats": f"works/{wid}/beats.jsonl",
                      "assessment": f"works/{wid}/assessment.md",
                      "dossier": f"works/{wid}/dossier/",
                      "data": f"works/{wid}/data/"},
            "created_at": now(), "updated": today(),
            "note": f"backfill 自 {it['rel']}（09 卷 c_NN 解析）；shot/move/speech/func 未回填，需重读补",
        }
        (wd / "profile.json").write_text(json.dumps(prof, ensure_ascii=False, indent=1) + "\n",
                                        encoding="utf-8")
        known[key] = wid
        report["items"].append({"wid": wid, "title": it["title"], "src": it["rel"],
                                "beats": len(beats), "vol": it["n_vol"]})
        print(f"  → {wid}  {it['title'][:24]:26s} beats {len(beats):3d}  {cid}")

    state_p.write_text(json.dumps(state, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    smap_p.write_text(json.dumps(smap, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    (ROOT / "_pipeline" / "backfill_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"\n回填 {len(report['items'])} 部，报告 _pipeline/backfill_report.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
