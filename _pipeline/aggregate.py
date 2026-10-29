#!/usr/bin/env python3
"""aggregate.py —— 从 beats + profile 算客观统计量，不写任何判断。

只输出可机验的计数与比率。凡是需要「我觉得」的字段一律不出现，
理由：知识卡的证据必须是能重算的数字，不是叙述。

产出：
    catalog/stats.json     机读
    reports/stats.md       人读（可直接贴进知识卡 evidence）

用法：
    python3 _pipeline/aggregate.py
"""
from __future__ import annotations

import json
import re
import statistics
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CJK = re.compile(r"[\u4e00-\u9fff]")

CUTS = [(0, 60, "<60s"), (60, 120, "60–120s"), (120, 300, "120–300s"),
        (300, 600, "300–600s"), (600, 10 ** 9, ">600s")]


def load(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def cjk_len(s: str | None) -> int:
    return len(CJK.findall(s or ""))


def work_stats(wid: str, prof: dict) -> dict:
    bp = ROOT / "works" / wid / "beats.jsonl"
    beats = []
    if bp.exists():
        for ln in bp.read_text(encoding="utf-8").splitlines():
            ln = ln.strip()
            if ln:
                try:
                    beats.append(json.loads(ln))
                except json.JSONDecodeError:
                    pass
    n = len(beats)
    subs = [b for b in beats if b.get("sub")]
    scrs = [b for b in beats if b.get("screen")]
    dur = (prof.get("duration_ms") or 0) / 1000
    chars = sum(cjk_len(b.get("sub")) for b in beats)
    scr_chars = sum(cjk_len(b.get("screen")) for b in beats)
    first_beat = next((b for b in beats if b.get("sub")), None)
    first = first_beat["t0"] if first_beat else None
    first_grid = int(first_beat["grid"][2:]) if first_beat else None
    last = max((b["t0"] for b in subs), default=None)
    # 开场 12 秒（前 3 格）与收尾 1 格
    head_subs = sum(1 for b in beats[:3] if b.get("sub"))
    tail_sub = 1 if beats and beats[-1].get("sub") else 0
    registered = (prof.get("coverage") or {}).get("beats_registered") or 0
    return {
        "wid": wid,
        "title": prof.get("title"),
        "creator_id": prof.get("creator_id"),
        "series_id": prof.get("series_id"),
        "episode": prof.get("episode"),
        "status": prof.get("status"),
        # data_ready：格已亲读登记，统计才有意义。骨架未填的（beats 有但 visual 全空）标 false。
        "data_ready": registered > 0 and n > 0,
        "duration_s": round(dur, 3),
        "grids": n,
        "sub_grids": len(subs),
        "sub_ratio": round(len(subs) / n, 3) if n else 0,
        # 画面文字单列：UI／片名卡／署名／招牌／常驻免责。混进 sub 会把字幕密度算成假高，
        # ENEMY 那种「零对白 + 满屏 UI 红字」的作品尤其会被误判成有台词。
        "screen_grids": len(scrs),
        "screen_ratio": round(len(scrs) / n, 3) if n else 0,
        "screen_chars": scr_chars,
        "cjk_chars": chars,
        "chars_per_s": round(chars / dur, 2) if dur else 0,
        "first_sub_s": first,
        "first_sub_grid": first_grid,
        "last_sub_s": last,
        "head12_sub_grids": head_subs,
        "tail_sub": tail_sub,
        "has_dialogue": len(subs) > 0,
        "category": next((lb for lo, hi, lb in CUTS if lo <= dur < hi), "?"),
    }


def bucket(rows: list[dict], key: str) -> dict:
    vals = [r[key] for r in rows if isinstance(r.get(key), (int, float))]
    if not vals:
        return {}
    return {"n": len(vals), "min": round(min(vals), 3), "max": round(max(vals), 3),
            "median": round(statistics.median(vals), 3),
            "mean": round(sum(vals) / len(vals), 3)}


def main() -> int:
    creators = {p.parent.name: load(p) for p in (ROOT / "creators").glob("c-*/profile.json")}
    series = load(ROOT / "_pipeline" / "series_map.json")
    works_all = []
    for p in sorted((ROOT / "works").glob("w-*/profile.json")):
        prof = load(p)
        if prof:
            works_all.append(work_stats(p.parent.name, prof))
    # 统计只用已亲读登记的作品：骨架未填的进 stats 但不算入分布，
    # 否则「零字幕」这种假数据会污染中位数。
    works = [w for w in works_all if w["data_ready"]]
    excluded = [w["wid"] for w in works_all if not w["data_ready"]]

    # 按博主
    by_creator = []
    for cid, c in sorted(creators.items()):
        mine = [w for w in works if w["creator_id"] == cid]
        if not mine:
            continue
        by_creator.append({
            "creator_id": cid, "name": c.get("name"),
            "works": len(mine),
            "series": len({w["series_id"] for w in mine if w["series_id"]}),
            "duration": bucket(mine, "duration_s"),
            "sub_ratio": bucket(mine, "sub_ratio"),
            "screen_ratio": bucket(mine, "screen_ratio"),
            "chars_per_s": bucket(mine, "chars_per_s"),
            "first_sub_s": bucket(mine, "first_sub_s"),
            "no_dialogue_works": sum(1 for w in mine if not w["has_dialogue"]),
        })

    # 按系列：时长序列
    by_series = []
    for sid, name in sorted(series.items()):
        mine = [w for w in works if w["series_id"] == sid]
        if not mine:
            continue
        mine.sort(key=lambda w: (w["episode"] is None, w["episode"] or 0))
        by_series.append({
            "series_id": sid, "name": name, "episodes": len(mine),
            "duration_seq": [w["duration_s"] for w in mine],
            "title_seq": [w["title"] for w in mine],
            "monotonic_up": all(a < b for a, b in zip(
                [w["duration_s"] for w in mine], [w["duration_s"] for w in mine][1:])),
        })

    # 全库分档
    cat = {}
    for w in works:
        cat.setdefault(w["category"], []).append(w)
    by_category = [{
        "category": k, "works": len(v),
        "duration_median": round(statistics.median([x["duration_s"] for x in v]), 2),
        "sub_ratio_median": round(statistics.median([x["sub_ratio"] for x in v]), 3),
        "chars_per_s_median": round(statistics.median([x["chars_per_s"] for x in v]), 2),
    } for k, v in sorted(cat.items())]

    out = {
        "schema": "kb-stats/1",
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "totals": {
            "creators": len(creators),
            "works": len(works_all),
            "works_counted": len(works),
            "beats": sum(w["grids"] for w in works),
            "sub_grids": sum(w["sub_grids"] for w in works),
            "screen_grids": sum(w["screen_grids"] for w in works),
            "cjk_chars": sum(w["cjk_chars"] for w in works),
            "screen_chars": sum(w["screen_chars"] for w in works),
            "no_dialogue_works": sum(1 for w in works if not w["has_dialogue"]),
        },
        "overall": {
            "duration": bucket(works, "duration_s"),
            "sub_ratio": bucket(works, "sub_ratio"),
            "screen_ratio": bucket(works, "screen_ratio"),
            "chars_per_s": bucket(works, "chars_per_s"),
            "first_sub_s": bucket(works, "first_sub_s"),
        },
        "by_creator": by_creator,
        "by_series": by_series,
        "by_category": by_category,
        "works": works_all,
        "excluded_from_stats": excluded,
    }
    (ROOT / "catalog" / "stats.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    # ---- 人读报告 ----
    L: list[str] = []
    t = out["totals"]
    L.append("# 全库客观统计\n")
    L.append(f"> 由 `_pipeline/aggregate.py` 从 beats.jsonl 重算，无手工填值。"
             f"生成时间 {out['generated_at']}。\n")
    if excluded:
        L.append(f"> **统计口径**：仅计已亲读登记画面的 {len(works)} 部；"
                 f"{len(excluded)} 部（{'、'.join(excluded)}）画面尚未登记，不进任何分布。\n")
    L.append(f"博主 {t['creators']} / 作品 {t['works']} / 格 {t['beats']} / "
             f"带对白格 {t['sub_grids']}（{t['sub_grids']/max(1,t['beats'])*100:.1f}%）/ "
             f"带画面文字格 {t['screen_grids']}（{t['screen_grids']/max(1,t['beats'])*100:.1f}%）/ "
             f"中文字符 {t['cjk_chars']}（画面文字另 {t['screen_chars']}）/ 无对白作品 {t['no_dialogue_works']}\n")
    L.append("> **sub / screen 口径（2026-10-30 分列）**：`sub` 是人物的对白字幕，`screen` 是画面文字"
             "（系统 UI／片名卡／署名卡／招牌／道具字／常驻免责）。05 卷有权威表的 36 部由 "
             "`_pipeline/text05.py` 按 `text05_map.json` 重建，无权威表的用 09 卷行文解析（`sub_src` 标来源）。"
             "ENEMY 五部为零对白作品，其 UI 红字全部计入 `screen`，`sub` 为 0。\n")

    L.append("## 一、全库分布\n")
    L.append("| 量 | n | min | median | max |\n|---|---|---|---|---|")
    for k, lb in (("duration", "片长 s"), ("sub_ratio", "对白格占比"),
                  ("screen_ratio", "画面文字格占比"),
                  ("chars_per_s", "中文字符/秒"), ("first_sub_s", "首句字幕落点 s")):
        b = out["overall"].get(k) or {}
        if b:
            L.append(f"| {lb} | {b['n']} | {b['min']} | {b['median']} | {b['max']} |")
    L.append("")

    L.append("## 二、按博主\n")
    L.append("| 博主 | 作品 | 系列 | 片长中位 | 对白格占比中位 | 画面文字格中位 | 字/秒中位 | 首句落点中位 | 无对白 |")
    L.append("|---|---|---|---|---|---|---|---|---|")
    for c in by_creator:
        L.append(f"| {c['name']} | {c['works']} | {c['series']} | "
                 f"{c['duration'].get('median')} | {c['sub_ratio'].get('median')} | "
                 f"{c['screen_ratio'].get('median')} | "
                 f"{c['chars_per_s'].get('median')} | {c['first_sub_s'].get('median')} | "
                 f"{c['no_dialogue_works']} |")
    L.append("")

    L.append("## 三、系列时长序列\n")
    L.append("| 系列 | 集数 | 时长序列 | 严格递增 |\n|---|---|---|---|")
    for s in by_series:
        L.append(f"| {s['name']} | {s['episodes']} | "
                 f"{' → '.join(str(x) for x in s['duration_seq'])} | "
                 f"{'是' if s['monotonic_up'] else '否'} |")
    L.append("")

    L.append("## 四、按片长档\n")
    L.append("| 档位 | 作品 | 片长中位 | 字幕格占比中位 | 字/秒中位 |\n|---|---|---|---|---|")
    for c in by_category:
        L.append(f"| {c['category']} | {c['works']} | {c['duration_median']} | "
                 f"{c['sub_ratio_median']} | {c['chars_per_s_median']} |")
    L.append("")

    L.append("## 五、每部明细\n")
    L.append("| # | 作品 | 博主 | 时长 | 格 | 字幕格 | 占比 | 字/秒 | 首句 | 末格有字 |")
    L.append("|---|---|---|---|---|---|---|---|---|---|")
    for w in sorted(works, key=lambda x: -(x["duration_s"] or 0)):
        cname = next((c["name"] for c in by_creator if c["creator_id"] == w["creator_id"]), "?")
        L.append(f"| {w['wid']} | {w['title']} | {cname} | {w['duration_s']} | {w['grids']} | "
                 f"{w['sub_grids']} | {w['sub_ratio']} | {w['chars_per_s']} | "
                 f"{w['first_sub_s']} | {w['tail_sub']} |")
    L.append("")

    (ROOT / "reports" / "stats.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"OK 统计完成：{len(works)} 部 / {t['beats']} 格 → catalog/stats.json + reports/stats.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
