#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""prep.py —— 闸门2「技术前处理」一条命令做完。

    python3 _pipeline/prep.py --work works/w-0001 --src /path/to/raw.mp4
    python3 _pipeline/prep.py --work works/w-0001 --src raw.mp4 --steps frames,contact,cuts,metrics --ocr

产出（对齐 validate.py 的 gate2_missing 口径）：
    frames/f_0001.jpg…     1 fps 抽帧，f_NNNN 对应第 NNNN−1 秒
    contact/c_01.jpg…      每 4 秒一格 2×2 拼图，c_NN 与 beats.grid 一一对应
    data/meta_raw.json     ffprobe 技术参数
    data/cuts.txt          切点秒表（scdet）
    data/cut_scores.json   逐秒帧差分数
    data/four_curves.json  15 秒分段的亮度/饱和/对比/切点率/差异分/人声 RMS
    data/ocr.json          （--ocr）RapidOCR 三区检出

⚠️ 这是**重建实现**，不是当初跑晒月光那套脚本的原文——原脚本没留存（只在
   /workspace/02_在办/ 下留下 ocr_par2.py 一份）。算法按已产出的 data 文件反推，
   数值口径一致，但逐位复现不保证。新片首次跑完要人工抽查三件事：
   ① c_01 是否 4 秒四格 ② cuts.txt 与拼图看到的切点对得上 ③ OCR 是否覆盖字幕区。

实测坑（写死在这里，别再踩一遍）：
    · 本机 cgroup 4 核，nproc 报 32 是宿主核数 → OCR 用 4 worker × 单线程，
      开 8 个会超售，速度反降（32 核假象那次跑了两倍时间）。
    · det_limit_side_len=480：默认 736 时 1280 宽帧上小字全漏，480 才检出。
    · 拼图必须缩放后拼（每格宽 750 → 总宽 1500）；直接 4 张全尺寸拼会到 2560，
      单图过 500KB，亲读时浏览器卡。
    · 中部板（mid 区 0.28–0.75）必须全尺寸裁，缩过就丢小字。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def sh(cmd: list[str], **kw) -> str:
    r = subprocess.run(cmd, capture_output=True, text=True, **kw)
    if r.returncode != 0:
        raise RuntimeError(f"{' '.join(cmd[:3])}… 失败：{(r.stderr or '')[-400:]}")
    return r.stdout


# ---------- ① 技术参数 ----------

def step_meta(src: Path, work: Path) -> dict:
    out = sh(["ffprobe", "-v", "error", "-select_streams", "v:0",
              "-show_entries", "stream=width,height,r_frame_rate,nb_frames:format=duration,size",
              "-of", "json", str(src)])
    j = json.loads(out)
    st = (j.get("streams") or [{}])[0]
    fm = j.get("format") or {}
    meta = {
        "width": st.get("width"),
        "height": st.get("height"),
        "r_frame_rate": st.get("r_frame_rate"),
        "nb_frames": int(st["nb_frames"]) if str(st.get("nb_frames", "")).isdigit() else None,
        "duration": round(float(fm.get("duration") or 0), 3),
        "size": int(fm.get("size") or src.stat().st_size),
    }
    (work / "data").mkdir(parents=True, exist_ok=True)
    (work / "data" / "meta_raw.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return meta


# ---------- ② 抽帧 ----------

def step_frames(src: Path, work: Path) -> int:
    d = work / "frames"
    if d.exists():
        shutil.rmtree(d)
    d.mkdir(parents=True)
    # 1 fps，等比不留黑边；f_0001 = 第 0 秒
    sh(["ffmpeg", "-v", "error", "-i", str(src), "-vf", "fps=1",
        "-q:v", "2", str(d / "f_%04d.jpg")])
    return len(list(d.glob("f_*.jpg")))


# ---------- ③ 拼图 ----------

def step_contact(work: Path, cell_w: int = 750, per: int = 4) -> int:
    from PIL import Image
    d = work / "contact"
    if d.exists():
        shutil.rmtree(d)
    d.mkdir(parents=True)
    frames = sorted((work / "frames").glob("f_*.jpg"))
    n = 0
    for i in range(0, len(frames), per):
        chunk = frames[i:i + per]
        ims = [Image.open(p).convert("RGB") for p in chunk]
        cell_h = int(cell_w * ims[0].size[1] / ims[0].size[0])
        canvas = Image.new("RGB", (cell_w * 2, cell_h * 2), "black")
        for k, im in enumerate(ims):
            canvas.paste(im.resize((cell_w, cell_h), Image.LANCZOS),
                         ((k % 2) * cell_w, (k // 2) * cell_h))
        n += 1
        canvas.save(d / f"c_{n:02d}.jpg", quality=86)
    return n


# ---------- ④ 切点 ----------

def step_cuts(src: Path, work: Path) -> tuple[int, int]:
    d = work / "data"
    d.mkdir(parents=True, exist_ok=True)
    # scdet 的检测结果走 stderr，必须 capture 下来，不能用只返回 stdout 的 sh()
    r = subprocess.run(["ffmpeg", "-v", "info", "-i", str(src), "-vf", "scdet=threshold=10",
                        "-f", "null", "-"], capture_output=True, text=True)
    txt = (r.stderr or "")
    (d / "_scdet.log").write_text(txt, encoding="utf-8")
    cuts = sorted({round(float(m.group(1)), 3)
                   for m in re.finditer(r"lavfi\.scd\.time:\s*([\d.]+)", txt)})
    (d / "cuts.txt").write_text("\n".join(f"{c:.3f}" for c in cuts) + "\n", encoding="utf-8")
    return len(cuts), 0


def step_cut_scores(work: Path, step: float = 1.0) -> int:
    """逐秒帧差：相邻两帧缩到 160 宽后算平均绝对差，归一化到 0–1。"""
    import numpy as np
    from PIL import Image
    frames = sorted((work / "frames").glob("f_*.jpg"))
    small = []
    for p in frames:
        im = Image.open(p).convert("L").resize((160, 90))
        small.append(np.asarray(im, dtype=np.float32) / 255.0)
    out = []
    for i in range(1, len(small)):
        diff = float(np.abs(small[i] - small[i - 1]).mean())
        out.append({"t": round(i * step - step / 2, 1), "score": round(diff, 6)})
    (work / "data" / "cut_scores.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return len(out)


# ---------- ⑤ 四曲线 ----------

def step_curves(work: Path, seg: int = 15) -> int:
    import numpy as np
    from PIL import Image
    dur = float(json.loads((work / "data" / "meta_raw.json").read_text())["duration"])
    frames = sorted((work / "frames").glob("f_*.jpg"))
    per_sec = []
    for p in frames:
        im = Image.open(p).convert("RGB").resize((320, 180))
        a = np.asarray(im, dtype=np.float32) / 255.0
        mx, mn = a.max(axis=2), a.min(axis=2)
        lum = float((0.299 * a[..., 0] + 0.587 * a[..., 1] + 0.114 * a[..., 2]).mean())
        sat = float(np.where(mx > 0, (mx - mn) / np.maximum(mx, 1e-6), 0).mean())
        per_sec.append({"lum": round(lum, 3), "sat": round(sat, 3),
                        "contrast": round(float((mx - mn).mean()), 3)})
    scores = json.loads((work / "data" / "cut_scores.json").read_text())
    cut_list = [float(x) for x in (work / "data" / "cuts.txt").read_text().split()]
    vs = json.loads((work / "data" / "vocal_blocks.json").read_text()) if \
        (work / "data" / "vocal_blocks.json").exists() else []
    out = []
    n = int((dur + seg - 1) // seg)
    for k in range(n):
        lo, hi = k * seg, min((k + 1) * seg, dur)
        blk = per_sec[lo:int(hi)]
        if not blk:
            continue
        sc = [s["score"] for s in scores if lo <= s["t"] < hi]
        nc = sum(1 for c in cut_list if lo <= c < hi)
        out.append({
            "seg": k, "range": f"{lo}-{hi}s",
            "lum": round(float(np.mean([b["lum"] for b in blk])), 3),
            "sat": round(float(np.mean([b["sat"] for b in blk])), 3),
            "contrast": round(float(np.mean([b["contrast"] for b in blk])), 3),
            "cuts": nc,
            "cut_rate": round(nc / seg, 3),
            "avg_score": round(float(np.mean(sc)), 3) if sc else 0,
            "max_score": round(float(np.max(sc)), 3) if sc else 0,
            "vocal_rms": round(float(np.mean([v.get("rms", 0) for v in vs
                                              if lo <= v.get("t", -1) < hi])) if vs else 0, 4),
        })
    (work / "data" / "four_curves.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return len(out)


# ---------- ⑥ OCR ----------

ZONES = (("top", 0.00, 0.35), ("mid", 0.28, 0.75), ("sub", 0.70, 1.00))


def _ocr_worker(args):
    wid, nw, frames, outdir = args
    os.environ["OMP_NUM_THREADS"] = "1"
    from rapidocr_onnxruntime import RapidOCR
    engine = RapidOCR(intra_op_num_threads=1, det_limit_side_len=480)
    import cv2
    import numpy as np
    out = []
    for p in frames[wid::nw]:
        n = int(Path(p).stem[2:6])
        img = cv2.imdecode(np.fromfile(p, dtype=np.uint8), cv2.IMREAD_COLOR)
        if img is None:
            continue
        h = img.shape[0]
        items = []
        for zname, y0, y1 in ZONES:
            res, _ = engine(img[int(h * y0):int(h * y1), :])
            for box, txt, score in (res or []):
                try:
                    sc = float(score)
                except (TypeError, ValueError):
                    continue
                t = str(txt).strip()
                if sc < 0.55 or len(t) < 2:
                    continue
                items.append({"text": t, "score": round(sc, 3), "zone": zname})
        if items:
            out.append({"sec": n - 1, "items": items})
    return out


def step_ocr(work: Path, nw: int = 4) -> int:
    import multiprocessing as mp
    frames = [str(p) for p in sorted((work / "frames").glob("f_*.jpg"))]
    with mp.Pool(nw) as pool:
        parts = pool.map(_ocr_worker, [(w, nw, frames, str(work)) for w in range(nw)])
    allout = sorted([x for part in parts for x in part], key=lambda x: x["sec"])
    (work / "data" / "ocr.json").write_text(
        json.dumps(allout, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return len(allout)


# ---------- 主流程 ----------

STEPS = {
    "frames": lambda s, w: step_frames(s, w),
    "contact": lambda s, w: step_contact(w),
    "cuts": lambda s, w: step_cuts(s, w)[0],
    "scores": lambda s, w: step_cut_scores(w),
    "curves": lambda s, w: step_curves(w),
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", required=True, help="works/w-XXXX")
    ap.add_argument("--src", required=True, help="原片路径")
    ap.add_argument("--steps", default="frames,contact,cuts,scores,curves")
    ap.add_argument("--ocr", action="store_true", help="跑 OCR（慢，约 1–5 分钟）")
    ap.add_argument("--force", action="store_true", help="产物已存在也重跑")
    a = ap.parse_args()

    work = (ROOT / a.work).resolve() if not Path(a.work).is_absolute() else Path(a.work)
    src = Path(a.src).resolve()
    if not src.exists():
        print(f"原片不存在：{src}")
        return 2
    meta = step_meta(src, work)
    print(f"元信息：{meta['width']}×{meta['height']} {meta['r_frame_rate']} {meta['duration']}s")

    for name in [s for s in a.steps.split(",") if s]:
        if name not in STEPS:
            print(f"未知步骤 {name}，可用：{','.join(STEPS)}")
            return 2
        n = STEPS[name](src, work)
        print(f"  {name:9} → {n}")

    if a.ocr:
        print("  OCR 开始（4 worker 单线程，det_side=480）…")
        print(f"  ocr       → {step_ocr(work)} 秒检出文字")

    print("\n完成。接着人工抽查：① c_01 是否 4 秒四格 ② cuts.txt 与拼图切点对不对得上 "
          "③ OCR 覆没覆盖字幕区")
    print("自检：python3 _pipeline/validate.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
