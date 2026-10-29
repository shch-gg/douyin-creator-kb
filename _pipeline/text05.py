#!/usr/bin/env python3
"""text05.py —— 把 05 卷「画面文字/对白」权威表解析进 beats。

为什要做：`backfill.py` 只从 09 卷行文里抠「字幕「…」」，05 卷那些结构化表格
（ENEMY 的 UI 红字、片名卡、署名卡、招牌、常驻免责声明）一直躺在档案里没进库。
结果是 beats.sub 只是**下界**，且画面文字与对白混在一个字段里，字幕密度口径被污染。

本脚本做两件事：
1. 按 `text05_map.json` 逐部指定「取哪几节」——不猜。标题前缀匹配，找不到就报错。
2. 拆成两个字段：
   - `sub`    对白字幕（人物说的话）
   - `screen` 画面文字（UI / 片名卡 / 署名 / 招牌 / 道具字 / 常驻免责）
   带「画面文字·」「【画面文字·X】」前缀的行归 screen，其余归 sub；配方可整节 force。

用法：
    python3 _pipeline/text05.py --dry-run       # 只统计不落盘
    python3 _pipeline/text05.py --apply         # 写入 beats.jsonl
    python3 _pipeline/text05.py --apply --only w-0026
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from kbtext import demd  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
MAP = ROOT / "_pipeline" / "text05_map.json"
SRC_ROOT = Path("/workspace/01_最终交付")

HEAD_KEYS = ("秒", "起", "时间", "位置", "#", "序", "组", "whisper", "ASR", "类型", "内容", "维度", "功能", "作品", "检查项", "分数段", "拼图", "版本", "项")

SEC_RE = re.compile(r"^(#{1,6})\s*(.+?)\s*$")
# 画面文字前缀，三种形制必须分先后处理：
#   【画面文字·游戏UI①】正文   → 连标签一起剥
#   （画面文字·红纸）正文       → 连标签一起剥
#   画面文字·门牌 102           → 只剥「画面文字·」四个字 + 间隔号，后面是内容
# 注意：绝不能把「画面文字·」后的整段都当标签——「画面文字·欢迎新同学 许颂」里
# 「欢迎新同学 许颂」就是字卡内容，剥掉就丢了一条真实画面文字。
BRACKET_TAG_RE = re.compile(r"^[【\[]\s*画面文字\s*[·・:：]\s*[^】\]]{0,14}[】\]]\s*")
PAREN_TAG_RE = re.compile(r"^[（(]\s*画面文字\s*[·・:：]\s*[^）)]{0,14}[）)]\s*")
PREFIX_RE = re.compile(r"^画面文字\s*[·・:：]\s*")
TAG_RE = re.compile(r"^[\[【（(](系统|微恐提醒|对白|画面|署名卡|片名卡|音效|提示)[\]】）)]\s*")
# 整条都是说明（不是文字本身）时跳过；句子里夹一个「不可辨」不算——那是真实对白缺一字
ONLY_NOTE_RE = re.compile(r"^[（(][^）)]*?(不可辨|未读出|模糊|待确认)[^）)]*?[）)]$")


def strip_md(s: str) -> str:
    """与 backfill 共用一套清洗规则（kbtext.demd），避免两条通道清理力度不一。"""
    return demd(s)


def parse_span(cell: str):
    """把秒域单元格解析成 (t0, t1)。解析不出返回 None。"""
    s = strip_md(cell).strip()
    if not s:
        return None
    s = s.replace("–", "-").replace("—", "-").replace("~", "-").replace("－", "-")
    s = s.replace(" ", "").replace("　", "")
    s = re.sub(r"[sS]$", "", s)
    s = re.sub(r"^第|起$|止$", "", s)
    # 031.x / 031.X → 031
    s = re.sub(r"\.([xX])", "", s)
    m = re.match(r"^(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)", s)
    if m:
        t0, t1 = float(m.group(1)), float(m.group(2))
        return (t0, t1) if t1 >= t0 else (t1, t0)
    m = re.match(r"^(\d+(?:\.\d+)?)", s)
    if m:
        t = float(m.group(1))
        return (t, t)
    return None


def split_row(line: str):
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|"):
        line = line[:-1]
    return [c.strip() for c in line.split("|")]


def is_sep(line: str) -> bool:
    return bool(re.match(r"^\|[\s:|\-]+\|?$", line.strip()))


def is_header(cells) -> bool:
    if not cells:
        return True
    c0 = strip_md(cells[0])
    if not c0:
        return True
    return any(c0.startswith(k) for k in HEAD_KEYS) and not re.match(r"^\d", c0)


def sections(text: str):
    """按标题切节，返回 [(level, title, [lines])]，保持文档顺序。"""
    out = []
    cur = (0, "（文首）", [])
    for line in text.split("\n"):
        m = SEC_RE.match(line)
        if m:
            out.append(cur)
            cur = (len(m.group(1)), m.group(2), [])
        else:
            cur[2].append(line)
    out.append(cur)
    return out


def clean_text(raw: str):
    """返回 (text, has_screen_prefix)"""
    t = strip_md(raw)
    forced = False
    for rx in (BRACKET_TAG_RE, PAREN_TAG_RE):
        if rx.match(t):
            forced = True
            t = rx.sub("", t, count=1)
            break
    else:
        if PREFIX_RE.match(t):
            forced = True
            t = PREFIX_RE.sub("", t, count=1)
    m = TAG_RE.match(t)
    if m:
        forced = True
        t = TAG_RE.sub("", t, count=1)
    t = t.strip(" 　／/|")
    return t, forced


def load_beats(wid: str):
    p = ROOT / "works" / wid / "beats.jsonl"
    if not p.exists():
        return None, p
    rows = [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]
    return rows, p


def parse_work(wid: str, cfg: dict, work: dict):
    """解析一部作品，返回 (items, stats)"""
    rel = work["src"]
    p = SRC_ROOT / rel / "05_画面文字.md"
    st = {"wid": wid, "title": work["title"], "file": str(rel), "rows": 0,
          "kept": 0, "sub": 0, "screen": 0, "bad_span": 0, "undecidable": 0,
          "missing_sections": [], "claim": cfg.get("claim"), "warn": []}
    if not p.exists():
        st["warn"].append("05 卷缺失")
        return [], st

    secs = sections(p.read_text(encoding="utf-8"))
    items = []
    for spec in cfg["sections"]:
        if isinstance(spec, str):
            spec = {"sec": spec}
        want, force, occ = spec["sec"], spec.get("force") or cfg.get("force"), spec.get("occ", 1)
        hits = [s for s in secs if s[1].startswith(want)]
        if len(hits) < occ:
            st["missing_sections"].append(want)
            continue
        _, title, lines = hits[occ - 1]
        for line in lines:
            if not line.strip().startswith("|") or is_sep(line):
                continue
            cells = split_row(line)
            st["rows"] += 1
            if is_header(cells):
                continue
            if "pairs" in cfg:
                spans = cfg["pairs"]
            else:
                spans = [[0, cfg.get("text_col", 1)]]
            for sc, tc in spans:
                if tc >= len(cells) or sc >= len(cells):
                    continue
                span = parse_span(cells[sc])
                raw = cells[tc]
                if span is None or not raw.strip():
                    # pairs 模式下第二对空列属正常的单句行，不算解析失败
                    if len(spans) == 1:
                        st["bad_span"] += 1
                    continue
                txt, pref = clean_text(raw)
                if not txt:
                    st["bad_span"] += 1
                    continue
                if ONLY_NOTE_RE.match(txt) or txt in ("—", "-", "／", "—／"):
                    st["undecidable"] += 1
                    continue
                kind = force or ("screen" if pref else "sub")
                items.append({"t0": span[0], "t1": span[1], "text": txt, "kind": kind,
                              "sec": title})
                st[kind] += 1
                st["kept"] += 1
    return items, st


def norm(s: str) -> str:
    return re.sub(r"[\s，。！？、：；""''（）()「」【】\*`／/·.]", "", s or "")


def apply_to_beats(wid: str, items, beats, zero_dialogue: bool = False):
    """把 items 落到 beats 格。返回 (changed, detail)

    zero_dialogue=True 时，把 09 卷解析出的 sub 清空并并入 screen——ENEMY 那类
    零对白作品的 sub 本来就是「虚构娱乐剧情 无不良引导」这类画面文字，
    留在 sub 里会让 has_dialogue 判成 true，直接推翻 kc-002。
    """
    if not beats:
        return 0, {"drop": 0, "dup": 0, "grid": 0}
    n = len(beats)
    bucket = {}   # grid_idx -> {"sub": [], "screen": []}
    drop = dup = 0
    for it in items:
        idx = int(it["t0"] // 4)
        if 0 <= idx < n:
            gi = idx
        elif idx >= n:
            gi = n - 1
            drop += 1
        else:
            drop += 1
            continue
        b = bucket.setdefault(gi, {"sub": [], "screen": []})
        key = norm(it["text"])
        if not key:
            continue
        if any(norm(x) == key for x in b[it["kind"]]):
            dup += 1
            continue
        b[it["kind"]].append(it["text"])

    changed = 0
    for gi, b in bucket.items():
        beat = beats[gi]
        new_sub = " ／ ".join(b["sub"]) if b["sub"] else None
        new_scr = " ／ ".join(b["screen"]) if b["screen"] else None
        touched = False
        # sub：仅当 05 卷给出对白时重建；05 卷无对白（零对白片）则保留 09 卷原值不动
        if new_sub:
            old = beat.get("sub") or ""
            if norm(old) != norm(new_sub):
                beat["sub"] = new_sub
                beat["sub_src"] = "05"
                touched = True
        if new_scr:
            if beat.get("screen") != new_scr:
                beat["screen"] = new_scr
                touched = True
        if touched:
            note = beat.get("note") or ""
            if "05卷" not in note:
                beat["note"] = (note + "+05卷") if note else "backfill:05卷"
            changed += 1

    if zero_dialogue:
        for beat in beats:
            old = (beat.get("sub") or "").strip()
            if not old:
                continue
            scr = (beat.get("screen") or "").strip()
            if norm(old) not in norm(scr):
                beat["screen"] = (scr + " ／ " + old) if scr else old
            beat["sub"] = None
            beat["sub_src"] = None
            changed += 1
    return changed, {"drop": drop, "dup": dup, "grid": len(bucket)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--only", default=None)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    cfg_all = json.loads(MAP.read_text(encoding="utf-8"))
    rep = json.loads((ROOT / "_pipeline" / "backfill_report.json").read_text(encoding="utf-8"))
    works = {it["wid"]: it for it in rep["items"]}

    report = {"works": [], "totals": {}}
    tot = {"sub": 0, "screen": 0, "kept": 0, "changed": 0}
    print(f"{'wid':7} {'行':>4} {'留':>4} {'sub':>4} {'scr':>4} {'格':>4} {'改':>4}  状态")
    for wid in sorted(cfg_all):
        if wid.startswith("_"):
            continue
        if a.only and wid != a.only:
            continue
        if wid not in works:
            print(f"{wid:7} 配方存在但无档案，跳过")
            continue
        items, st = parse_work(wid, cfg_all[wid], works[wid])
        beats, _ = load_beats(wid)
        if beats is None:
            st["warn"].append("beats.jsonl 缺失")
            report["works"].append(st)
            continue
        changed, det = apply_to_beats(wid, items, beats, bool(cfg_all[wid].get("zero_dialogue")))
        st["changed"] = changed
        st["dup"] = det["dup"]
        st["drop"] = det["drop"]
        st["grids"] = det["grid"]
        if st["claim"] and st["kept"] and abs(st["kept"] - st["claim"]) > 0:
            st["warn"].append(f"条数差：解析 {st['kept']} vs 标题自称 {st['claim']}")
        flag = "!" if (st["missing_sections"] or st["warn"]) else " "
        print(f"{wid:7} {st['rows']:4} {st['kept']:4} {st['sub']:4} {st['screen']:4} {det['grid']:4} {changed:4} {flag} " +
              ("/".join(st["missing_sections"][:2]) + ("…" if len(st["missing_sections"]) > 2 else "") if st["missing_sections"] else ""))
        report["works"].append(st)
        tot["sub"] += st["sub"]; tot["screen"] += st["screen"]
        tot["kept"] += st["kept"]; tot["changed"] += changed

        if a.apply and changed:
            p = ROOT / "works" / wid / "beats.jsonl"
            with p.open("w", encoding="utf-8") as f:
                for b in beats:
                    f.write(json.dumps(b, ensure_ascii=False) + "\n")

    report["totals"] = tot
    out = ROOT / "reports" / "text05.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n合计：解析 {tot['kept']} 条（对白 {tot['sub']} / 画面文字 {tot['screen']}），改格 {tot['changed']}")
    print(f"报告：{out.relative_to(ROOT)}" + ("（dry-run，未落盘）" if not a.apply else "（已落盘）"))
    if a.apply:
        print("提示：接着跑 build_index.py 与 validate.py 复核")


if __name__ == "__main__":
    sys.exit(main())
