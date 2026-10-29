#!/usr/bin/env python3
"""fix_md.py —— 就地清洗 beats 文本字段里的 markdown 渲染标记。

背景（2026-10-30）：
  09 卷正文用 `**加粗**` 标关键信息，backfill 直接搬进 visual/sub，导致
  1990 格 visual、567 格 sub 带星号。后果不是"不好看"，是检索失效——
  搜「生日礼物」搜不到实际存的 `**生日礼物**`；知识卡引用字幕会带符号；
  做词频/共现统计时标记符参与分词。

  修在源头（backfill.py / text05.py 已接 kbtext.demd）之外，还要洗一遍已落盘的数据，
  否则历史 36 部仍然是脏的。

用法：
  python3 _pipeline/fix_md.py --dry-run   # 只看会改多少格
  python3 _pipeline/fix_md.py --apply
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from kbtext import demd, has_md  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
FIELDS = ("visual", "sub", "screen")


def main() -> int:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--apply", action="store_true")
    ap.add_argument("--only", default=None, help="只处理某部作品，如 w-0005")
    a = ap.parse_args()

    report = {"schema": "fix_md.v1", "fields": list(FIELDS), "works": [], "totals": {}}
    tot = {"works": 0, "beats": 0, "changed_beats": 0, "changed_fields": 0, "chars_removed": 0}

    for bf in sorted((ROOT / "works").glob("*/beats.jsonl")):
        wid = bf.parent.name
        if a.only and wid != a.only:
            continue
        beats, changed, fields, removed = [], 0, 0, 0
        for line in bf.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            b = json.loads(line)
            hit = False
            for f in FIELDS:
                v = b.get(f)
                if not v or not has_md(v):
                    continue
                nv = demd(v)
                if nv != v:
                    removed += len(v) - len(nv)
                    b[f] = nv
                    fields += 1
                    hit = True
            if hit:
                changed += 1
            beats.append(b)

        if changed:
            tot["works"] += 1
            tot["changed_beats"] += changed
            tot["changed_fields"] += fields
            tot["chars_removed"] += removed
            report["works"].append({"wid": wid, "changed_beats": changed,
                                    "changed_fields": fields, "chars_removed": removed})
            if a.apply:
                bf.write_text("\n".join(json.dumps(b, ensure_ascii=False) for b in beats) + "\n",
                              encoding="utf-8")
        tot["beats"] += len(beats)

    report["totals"] = tot
    (ROOT / "reports").mkdir(exist_ok=True)
    if a.apply:
        (ROOT / "reports" / "fix_md.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    print(f"{'作品':8} {'改格':>5} {'改字段':>6} {'去字符':>7}")
    for w in report["works"]:
        print(f"{w['wid']:8} {w['changed_beats']:5} {w['changed_fields']:6} {w['chars_removed']:7}")
    print(f"\n合计 作品 {tot['works']} / 格 {tot['changed_beats']} / 字段 {tot['changed_fields']} "
          f"/ 去掉 {tot['chars_removed']} 字符（总格 {tot['beats']}）")
    if not a.apply:
        print("（dry-run，未落盘）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
