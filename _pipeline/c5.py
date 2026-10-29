#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""c5.py · 单作品证据链自校验（C5 五条的新库实现）

用法：
    python3 _pipeline/c5.py w-0001          # 校验并写 reports/c5-w-0001.md
    python3 _pipeline/c5.py w-0001 --quiet  # 只回写 coverage，不打印明细

为什么要有这个文件：
    validate.py 管的是"全库级"一致性（ID、索引、计数、状态机）。
    C5 管的是"一部作品内部"证据链是否自洽——beats / 字幕 / 卷宗三者互相对得上。
    两者层级不同，混在一起会让报错无法定位。

五条检查（对应 methods/10-入库SOP.md 闸门 5）：

    F1 时间轴单调     beats 的 t0 严格递增；srt 条目按时间升序
    F2 文字可回溯     beats.sub 非空 → 09 卷须有对应「字幕「…」」登记（若 09 存在）
    F3 跨卷锚点一致   片长 / 格数 / 起止秒 在三处（beats、srt、05）说法一致
    F4 格覆盖完整     c-NN 连续无重号，区间首尾相接，末格贴片长
    F5 srt ↔ 05 双向  srt 条目与 05 表行一一对应；起始秒命中 05 秒集合

输出纪律：
    - 0 error 才能把 status 推到 verified（validate 会读 coverage.c5_errors）
    - 每条 WARN 必须在报告里写"为什么可接受"，不许只报不解释
    - 卷宗尚未产出时，对应检查标 SKIP 并计入 skipped，不算通过也不算失败
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent

errors: list[str] = []
warns: list[str] = []
skips: list[str] = []
passed: list[str] = []


def load_vocab() -> set[str]:
    p = ROOT / "vocab" / "elements.yaml"
    if not p.exists():
        return set()
    try:
        d = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    except Exception:
        return set()
    return {e["id"] for e in (d.get("elements") or []) if isinstance(e, dict) and e.get("id")}


def err(m: str) -> None:
    errors.append(m)


def warn(m: str) -> None:
    warns.append(m)


def skip(m: str) -> None:
    skips.append(m)


def ok(m: str) -> None:
    passed.append(m)


def load(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def fm(p: Path) -> dict:
    try:
        t = p.read_text(encoding="utf-8")
    except Exception:
        return {}
    if not t.startswith("---"):
        return {}
    i = t.find("\n---", 3)
    if i == -1:
        return {}
    try:
        d = yaml.safe_load(t[3:i]) or {}
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def load_beats(wid: str) -> list[dict]:
    p = ROOT / "works" / wid / "beats.jsonl"
    if not p.exists():
        return []
    out = []
    for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except Exception as e:
            err(f"beats.jsonl 第 {i} 行解析失败：{e}")
    return out


# ---------- F0 内容完整性 ----------

def f0_content(wid: str, beats: list[dict]) -> None:
    """格子填满了不等于内容做了。visual 空、sub/speech 混装都算未完成。"""
    if not beats:
        err("F0 无 beats 数据")
        return
    vocab = load_vocab()
    empty = [b.get("grid", "?") for b in beats if not (b.get("visual") or "").strip()]
    if empty:
        head = "、".join(empty[:8]) + ("…" if len(empty) > 8 else "")
        err(f"F0 {len(empty)}/{len(beats)} 格 visual 为空（画面亲读未完成）：{head}")
    else:
        ok(f"F0 {len(beats)} 格 visual 全部非空")

    # 自造元素标签
    bad_func = set()
    for b in beats:
        for f in b.get("func") or []:
            if vocab and f not in vocab:
                bad_func.add(f)
    if bad_func:
        err(f"F0 元素标签不在 vocab/elements.yaml：{sorted(bad_func)}")

    # sub 与 speech 混装：sub 是屏幕字，speech 是听到的话，两者不该一模一样还不写 note
    mixed = 0
    for b in beats:
        sub = (b.get("sub") or "").strip()
        sp = b.get("speech") or []
        sp_txt = " ".join((x.get("text") or "") for x in sp if isinstance(x, dict)).strip()
        if sub and sp_txt and sub == sp_txt and not (b.get("note") or "").strip():
            mixed += 1
    if mixed:
        warn(f"F0 {mixed} 格 sub 与 speech 文本相同且无 note 说明"
             f"（若两者确实一致，在 note 里写一句；若不一致说明抄错了）")

    # 格内秒号越界
    for b in beats:
        t0, t1 = b.get("t0"), b.get("t1")
        for s in b.get("speech") or []:
            if not isinstance(s, dict):
                continue
            t = s.get("t")
            if isinstance(t, (int, float)) and isinstance(t0, (int, float)) and isinstance(t1, (int, float)):
                if not (t0 - 0.001 <= t <= t1 + 0.001):
                    err(f"F0 {b.get('grid')} speech 落点 t={t} 不在格区间 [{t0},{t1}]")

    # 定字修订必须三要素齐全（D-004：不许只写"改过了"）
    n_corr = 0
    for b in beats:
        for c in b.get("correction") or []:
            n_corr += 1
            if not isinstance(c, dict):
                err(f"F0 {b.get('grid')} correction 项不是对象")
                continue
            miss = [k for k in ("source", "was", "is") if not c.get(k)]
            if miss:
                err(f"F0 {b.get('grid')} correction 缺 {miss}"
                    f"（要写清谁错了、原值是什么、改成什么）")
            if c.get("was") and c.get("is") and c["was"] == c["is"]:
                warn(f"F0 {b.get('grid')} correction 的 was 与 is 相同，等于没改")
    if n_corr:
        ok(f"F0 已登记 {n_corr} 条定字修订")


# ---------- F1 时间轴单调 ----------

def f1_monotonic(wid: str, beats: list[dict]) -> None:
    if not beats:
        err("F1 无 beats 数据")
        return
    prev_t0 = None
    bad = 0
    for b in beats:
        t0 = b.get("t0")
        if not isinstance(t0, (int, float)):
            err(f"F1 {b.get('grid')} t0 非数值")
            bad += 1
            continue
        if prev_t0 is not None and t0 <= prev_t0:
            err(f"F1 {b.get('grid')} t0={t0} 未递增（上格 t0={prev_t0}）")
            bad += 1
        prev_t0 = t0
    if not bad:
        ok(f"F1 beats {len(beats)} 格 t0 严格递增")


# ---------- F4 格覆盖完整 ----------

def f4_coverage(wid: str, beats: list[dict], duration: float) -> None:
    if not beats:
        err("F4 无 beats 数据")
        return
    prev_t1 = None
    prev_n = 0
    bad = 0
    for b in beats:
        g = b.get("grid", "")
        m = re.fullmatch(r"c-(\d{2})", g)
        if not m:
            err(f"F4 grid 格式不合规：{g!r}（应 c-NN）")
            bad += 1
            continue
        n = int(m.group(1))
        if n != prev_n + 1:
            err(f"F4 格号不连续：{g}，上格 c-{prev_n:02d}")
            bad += 1
        expect_t0 = 4 * (n - 1)
        if abs((b.get("t0") or 0) - expect_t0) > 0.001:
            err(f"F4 {g} t0={b.get('t0')}，按 4 秒格应为 {expect_t0}")
            bad += 1
        if prev_t1 is not None and abs((b.get("t0") or 0) - prev_t1) > 0.001:
            err(f"F4 {g} 与上格不衔接：t0={b.get('t0')} vs 上格 t1={prev_t1}")
            bad += 1
        prev_t1 = b.get("t1")
        prev_n = n
    # 末格贴片长
    if prev_t1 is not None and duration > 0:
        if abs(prev_t1 - duration) > 0.05:
            err(f"F4 末格 t1={prev_t1} 与片长 {duration:.3f}s 相差 {prev_t1-duration:+.3f}s")
        else:
            ok(f"F4 {len(beats)} 格连续覆盖 0–{prev_t1}s，末格贴片长")
    if not bad:
        ok("F4 格号与区间全部合规")


# ---------- F3 锚点：片长 ----------

def f3_anchors(wid: str, beats: list[dict], duration: float) -> None:
    if duration <= 0:
        err("F3 duration_ms 非法，无法校验锚点")
        return
    if beats:
        last = beats[-1].get("t1")
        if isinstance(last, (int, float)) and abs(last - duration) > 0.05:
            err(f"F3 beats 末格 t1={last} 与 profile.duration_ms={duration:.3f}s 不符")
        else:
            ok("F3 beats 末格与片长锚点一致")
    # 卷宗若已产出，抽其中的片长登记
    d = ROOT / "works" / wid / "dossier"
    m05 = d / "05_画面文字.md"
    if m05.exists():
        txt = m05.read_text(encoding="utf-8")
        secs = [int(x) for x in re.findall(r"^\|\s*(\d{3,4})[–\-]", txt, re.M)]
        if secs:
            mx = max(secs)
            if mx > duration + 1:
                err(f"F3 05 卷最大登记秒 {mx}s 超过片长 {duration:.3f}s")


# ---------- F2 文字可回溯 ----------

def parse_subs_from_09(path: Path) -> list[tuple[int, str]]:
    """从 09 卷抽「NNNs … 字幕「…」」登记。返回 [(秒, 文本)]。"""
    out = []
    try:
        txt = path.read_text(encoding="utf-8")
    except Exception:
        return out
    for line in txt.splitlines():
        m = re.match(r"^\s*[-*]?\s*(\d{3,4})s\b", line)
        if not m:
            continue
        sec = int(m.group(1))
        for q in re.findall(r"字幕「([^」]*)」", line):
            out.append((sec, q))
        for q in re.findall(r"字幕“([^”]*)”", line):
            out.append((sec, q))
    return out


def f2_traceable(wid: str, beats: list[dict]) -> None:
    d = ROOT / "works" / wid / "dossier"
    m09 = d / "09_画面实录.md"
    if not m09.exists():
        skip("F2 09 卷未产出，跳过回溯检查")
        return
    reg = parse_subs_from_09(m09)
    if not reg:
        warn("F2 09 卷未检出「字幕「…」」登记（格式或缺失），无法回溯")
        return
    reg_text = "\n".join(t for _, t in reg)
    miss = []
    for b in beats:
        s = (b.get("sub") or "").strip()
        if not s:
            continue
        # 六级匹配：exact → contain → prefix → 去标点 → 去空白
        cands = [s, s.rstrip("。！？…"), re.sub(r"[，。！？、：；\"'（）\s]", "", s)]
        if not any(c and (c in reg_text) for c in cands):
            miss.append(f"{b.get('grid')}「{s}」")
    if miss:
        for x in miss[:10]:
            err(f"F2 beats 字幕无法在 09 卷回溯：{x}")
        if len(miss) > 10:
            err(f"F2 另有 {len(miss)-10} 条无法回溯（见报告）")
    else:
        n = len([b for b in beats if (b.get("sub") or "").strip()])
        ok(f"F2 {n} 条 beats 字幕全部可在 09 卷回溯")

    # 反向：09 有登记但 beats 无 sub
    beat_text = "\n".join((b.get("sub") or "") for b in beats)
    orphan = [t for _, t in reg if t and t not in beat_text]
    if orphan:
        warn(f"F2 09 卷有 {len(orphan)} 条字幕未落进任何 beats.sub（示例：{orphan[0][:20]}）")


# ---------- F5 srt ↔ 05 ----------

def parse_srt(path: Path) -> list[tuple[int, int, str]]:
    out = []
    try:
        txt = path.read_text(encoding="utf-8")
    except Exception:
        return out
    blocks = re.split(r"\n\s*\n", txt.strip())
    for blk in blocks:
        lines = [l for l in blk.splitlines() if l.strip()]
        if len(lines) < 2:
            continue
        tm = re.search(r"(\d{2}):(\d{2}):(\d{2})[,.](\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2})[,.](\d{3})", blk)
        if not tm:
            continue
        h1, m1, s1, _, h2, m2, s2, _ = tm.groups()
        start = int(h1) * 3600 + int(m1) * 60 + int(s1)
        end = int(h2) * 3600 + int(m2) * 60 + int(s2)
        text = " ".join(lines[2:]) if len(lines) > 2 else ""
        out.append((start, end, text.strip()))
    return out


def parse_05(path: Path) -> list[tuple[int, str]]:
    """解析 05 卷两列表：`| 000–001s | 文字 |`。"""
    out = []
    try:
        txt = path.read_text(encoding="utf-8")
    except Exception:
        return out
    for line in txt.splitlines():
        m = re.match(r"^\|\s*(\d{3,4})\s*[–\-]\s*\d{3,4}s\s*\|\s*(.+?)\s*\|", line)
        if m:
            out.append((int(m.group(1)), m.group(2).strip()))
    return out


def f5_srt(wid: str, duration: float) -> None:
    d = ROOT / "works" / wid / "dossier"
    srt = d / "subtitles.srt"
    m05 = d / "05_画面文字.md"
    if not srt.exists():
        skip("F5 subtitles.srt 未产出，跳过")
        return
    entries = parse_srt(srt)
    if not entries:
        err("F5 srt 无法解析出任何条目")
        return
    # 单调
    prev = -1
    for i, (st, en, tx) in enumerate(entries, 1):
        if st < prev:
            err(f"F5 srt 第 {i} 条起始秒 {st} 小于上一条")
        if en <= st:
            err(f"F5 srt 第 {i} 条止秒 {en} 不大于起始秒 {st}")
        if en > duration + 1:
            err(f"F5 srt 第 {i} 条止秒 {en}s 超过片长 {duration:.3f}s")
        prev = st
    if not errors:
        ok(f"F5 srt {len(entries)} 条时间轴合规")
    if m05.exists():
        rows = parse_05(m05)
        if not rows:
            warn("F5 05 卷未解析出表格行（格式不符），无法与 srt 对齐")
            return
        if len(rows) != len(entries):
            err(f"F5 srt {len(entries)} 条 ≠ 05 卷 {len(rows)} 行（一条对一行）")
        starts05 = {s for s, _ in rows}
        off = [st for st, _, _ in entries if st not in starts05]
        if off:
            err(f"F5 srt 有 {len(off)} 条起始秒未命中 05 秒集合（如 {off[:5]}）")
        else:
            ok(f"F5 srt {len(entries)} 条与 05 卷 {len(rows)} 行双向对齐")
    else:
        skip("F5 05 卷未产出，只校验 srt 自身")


# ---------- 报告 ----------

def write_report(wid: str, prof: dict) -> Path:
    d = ROOT / "reports"
    d.mkdir(exist_ok=True)
    p = d / f"c5-{wid}.md"
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    lines = [
        f"# C5 校验报告 · {wid}《{prof.get('title','')}》",
        "",
        f"> 生成时间：{ts}　｜　脚本：`_pipeline/c5.py`　｜　**本文件为脚本产物，手改无效**",
        "",
        f"## 结果",
        "",
        f"| 项 | 数 |",
        f"|---|---|",
        f"| ERROR | {len(errors)} |",
        f"| WARN | {len(warns)} |",
        f"| SKIP（卷宗未产出） | {len(skips)} |",
        f"| PASS | {len(passed)} |",
        "",
    ]
    for title, items, mark in (("ERROR（阻断 verified）", errors, "ERROR"),
                               ("WARN（需在此逐条说明为什么可接受）", warns, "WARN"),
                               ("SKIP（对应产物尚未产出）", skips, "SKIP"),
                               ("PASS", passed, "PASS")):
        if not items:
            continue
        lines += [f"## {title}", ""]
        for it in items:
            lines.append(f"- [{mark}] {it}")
        lines.append("")
    if warns:
        lines += ["## WARN 说明", "", "> 每条 WARN 必须在这里写清楚为什么不影响结论。留空视为未处理。", ""]
        for w in warns:
            lines.append(f"- `{w[:40]}…` → 待说明")
            lines.append("")
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    quiet = "--quiet" in sys.argv
    if not args:
        print("用法：python3 _pipeline/c5.py w-0001")
        return 2
    wid = args[0]
    prof = load(ROOT / "works" / wid / "profile.json")
    if not isinstance(prof, dict):
        print(f"读不到 works/{wid}/profile.json")
        return 2
    duration = (prof.get("duration_ms") or 0) / 1000
    beats = load_beats(wid)

    f0_content(wid, beats)
    f1_monotonic(wid, beats)
    f4_coverage(wid, beats, duration)
    f3_anchors(wid, beats, duration)
    f2_traceable(wid, beats)
    f5_srt(wid, duration)

    # 回写 coverage（validate 的 verified 检查读这里）
    prof.setdefault("coverage", {})
    prof["coverage"]["c5_errors"] = len(errors)
    prof["coverage"]["c5_warns"] = len(warns)
    prof["coverage"]["c5_checked_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    (ROOT / "works" / wid / "profile.json").write_text(
        json.dumps(prof, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    rp = write_report(wid, prof)
    # c5 回写了 profile.coverage，索引随即过期。这里顺手重建，
    # 否则下次 validate 会报两条与内容无关的"索引过期"，盖住真正的错。
    import subprocess
    r = subprocess.run([sys.executable, str(ROOT / "_pipeline" / "build_index.py")],
                       capture_output=True, text=True)
    if r.returncode != 0:
        warn("c5 完成后自动重建索引失败，请手动跑 build_index.py")
    if not quiet:
        for x in errors:
            print(f"ERROR {x}")
        for x in warns:
            print(f"WARN  {x}")
        for x in skips:
            print(f"SKIP  {x}")
        for x in passed:
            print(f"PASS  {x}")
    print(f"\n{wid}：{len(errors)} error / {len(warns)} warn / {len(skips)} skip"
          f"　报告 → reports/{rp.name}")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
