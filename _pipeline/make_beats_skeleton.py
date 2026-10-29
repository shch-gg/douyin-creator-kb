#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""make_beats_skeleton.py · 从抽帧目录生成 beats.jsonl 骨架

用法：
    python3 _pipeline/make_beats_skeleton.py w-0001
    python3 _pipeline/make_beats_skeleton.py w-0001 --force   # 覆盖已有（会丢手写内容，慎用）

做的事：按 frames/ 的帧数算出格数，生成 grid / t0 / t1，visual 留空待亲读。
不做：识别画面、写字幕。**骨架不是成品**，visual 为空时 validate 会报 ERROR，这是设计如此。

格规则：c-NN 覆盖 [4×(N−1), 4×(N−1)+3] 秒，与 2×2 拼图一一对应；末格按实际时长截断。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# 闸门 2「技术前处理」的产物清单，对应 methods/10-入库SOP.md 的完成标志。
# 判据必须是产物，不是目录——空目录不能证明做过任何事。
GATE2_FILES = ["data/meta_raw.json", "data/cuts.txt"]


def gate2_missing(wd: Path) -> list[str]:
    """返回闸门2 缺失的产物清单；空列表表示已完成。"""
    miss = [f for f in GATE2_FILES if not (wd / f).exists()]
    fr = list((wd / "frames").glob("f_*.jpg")) if (wd / "frames").exists() else []
    if not fr:
        miss.append("frames/ 抽帧")
    ct = list((wd / "contact").glob("c_*.jpg")) if (wd / "contact").exists() else []
    if not ct:
        miss.append("contact/ 拼图")
    data = wd / "data"
    jsons = [p.name for p in data.glob("*.json")] if data.exists() else []
    if not any(n.startswith("ocr") for n in jsons):
        miss.append("data/ocr.json")
    if not [n for n in jsons if not n.startswith("ocr") and n != "meta_raw.json"]:
        miss.append("Whisper json")
    return miss


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("wid")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()

    wd = ROOT / "works" / a.wid
    if not wd.exists():
        print(f"没有 works/{a.wid}")
        return 2

    prof_p = wd / "profile.json"
    try:
        prof = json.loads(prof_p.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"profile.json 读不了：{e}")
        return 2

    frames = sorted((wd / "frames").glob("f_*.jpg"))
    n_frames = len(frames)
    if n_frames == 0:
        print("frames/ 是空的，先跑抽帧（闸门 2）")
        return 2

    dur = (prof.get("duration_ms") or 0) / 1000
    # 帧数即秒数（1fps）；片长未知时用帧数兜底
    total_sec = dur if dur > 0 else float(n_frames)
    n_grid = (n_frames + 3) // 4

    out = wd / "beats.jsonl"
    if out.exists() and not a.force:
        print(f"{out} 已存在；要覆盖加 --force（会丢手写内容）")
        return 2

    lines = []
    for i in range(1, n_grid + 1):
        # t0/t1 是**连续区间** [4(N-1), 4N)，末格截到片长。
        # 2026-10-30 修：原实现前格写秒点(t1=3)、末格写片长(t1=215.34)，
        # 同一字段两种含义，且 [0,3] 到 [4,7] 之间漏掉 3–4 秒，
        # 与 AGENTS「每行 t0/t1 连续无缝」直接矛盾。
        # 现统一为区间：c-01=[0,4) c-02=[4,8) … c-54=[212,215.34)。
        t0 = 4 * (i - 1)
        t1 = total_sec if i == n_grid else 4 * i
        lines.append(json.dumps({
            "wid": a.wid,
            "grid": f"c-{i:02d}",
            "t0": t0,
            "t1": round(t1, 3),
            "shot": None,
            "move": None,
            "visual": "",
            "sub": None,
            "speech": [],
            "sound": None,
            "music": None,
            "func": [],
            "correction": [],
            "note": None,
        }, ensure_ascii=False))

    out.write_text("\n".join(lines) + "\n", encoding="utf-8")

    prof.setdefault("coverage", {})
    prof["coverage"]["beats_total"] = n_grid
    prof["coverage"]["beats_registered"] = 0
    # 闸门 2 完成判据：看产物，不看目录。
    # 2026-10-30 修：原实现只判断 data/ 目录是否存在——而 new_work.py 建的就是空
    # data/，于是任何新作品生成骨架后立刻变 prepped，即使抽帧/Whisper/OCR 全没做。
    gate2 = gate2_missing(wd)
    if prof.get("status") in ("planned", "ingested", "prepped"):
        if gate2:
            prof["status"] = "ingested"
            prof.setdefault("note", "")
            base = prof["note"].split("｜闸门2 未完成")[0].strip()
            prof["note"] = (base + " ｜闸门2 未完成，缺：" + "、".join(gate2)).strip("｜ ")
        else:
            prof["status"] = "prepped"
            prof["note"] = prof.get("note", "").split("｜闸门2 未完成")[0].strip() or None
    prof_p.write_text(json.dumps(prof, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    print(f"{a.wid}：{n_frames} 帧 → {n_grid} 格骨架，已写 {out}")
    if gate2:
        print(f"注意：闸门2 产物不全（缺 {', '.join(gate2)}），status 停在 {prof['status']}")
    print("下一步：逐格亲读补 visual/sub/speech/func；visual 空着 validate 会报错，属于正常未完成态")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
