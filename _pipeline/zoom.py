#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""zoom.py · 按**秒号**放大画面局部，用于逐字亲读定稿

用法：
    python3 _pipeline/zoom.py <wid> <sec> <y0> <y1> [x0] [x1] [scale] [out]

    例：底部字幕带（最常用）
        python3 _pipeline/zoom.py w-0001 63 0.80 0.98 0.1 0.9 5 /tmp/a.png
    例：中部旁白板
        python3 _pipeline/zoom.py w-0001 104 0.45 0.75 0 1 3 /tmp/b.png
    例：全帧定位（不知道字在哪时先看这个）
        python3 _pipeline/zoom.py w-0001 30 0 1 0 1 1 /tmp/c.png

坐标全是 0–1 比例。输出默认 /tmp/zoom_<wid>_<sec>.png。

**帧号与秒号的换算（踩过的坑，写死在这里）**
    抽帧是 1fps，第 1 帧对应第 0 秒：`f_{sec+1:04d}.jpg`
    所以「94 秒」在 f_0095.jpg 里，不是 f_0094.jpg。
    以前按帧号传参、嘴上说秒号，导致整批亲读结果错位一秒。
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent


def frames_dir(wid: str) -> Path:
    for name in ("frames", "frames_hd"):
        p = ROOT / "works" / wid / name
        if p.exists():
            return p
    return ROOT / "works" / wid / "frames"


def main() -> int:
    if len(sys.argv) < 4:
        print(__doc__)
        return 2
    wid = sys.argv[1].rstrip("/").split("/")[-1]
    sec = int(sys.argv[2])
    y0, y1 = float(sys.argv[3]), float(sys.argv[4])
    x0 = float(sys.argv[5]) if len(sys.argv) > 5 else 0.0
    x1 = float(sys.argv[6]) if len(sys.argv) > 6 else 1.0
    scale = float(sys.argv[7]) if len(sys.argv) > 7 else 3
    out = sys.argv[8] if len(sys.argv) > 8 else f"/tmp/zoom_{wid}_{sec:03d}.png"

    if not (0 <= y0 < y1 <= 1) or not (0 <= x0 < x1 <= 1):
        print(f"坐标越界：y {y0}-{y1} / x {x0}-{x1}（都应在 0–1 且 y0<y1、x0<x1）")
        return 2

    fd = frames_dir(wid)
    frame_no = sec + 1
    p = fd / f"f_{frame_no:04d}.jpg"
    if not p.exists():
        have = sorted(x.name for x in fd.glob("f_*.jpg"))
        if not have:
            print(f"{fd} 里没有帧。先跑抽帧（闸门 2）。")
        else:
            print(f"找不到 {p.name}（秒 {sec} → 帧 {frame_no}）。"
                  f"现有帧范围 {have[0]} … {have[-1]}，共 {len(have)} 帧。")
        return 2

    im = Image.open(p).convert("RGB")
    W, H = im.size
    box = (int(W * x0), int(H * y0), int(W * x1), int(H * y1))
    crop = im.crop(box)
    if scale != 1:
        crop = crop.resize((int(crop.width * scale), int(crop.height * scale)), Image.LANCZOS)
    crop.save(out)
    print(f"{p.name}（秒 {sec}）→ {out} {crop.size}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
