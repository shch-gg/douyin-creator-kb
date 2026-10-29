#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""next_task.py · 告诉你下一步做什么（不要靠猜状态）

用法：
    python3 _pipeline/next_task.py
    python3 _pipeline/next_task.py --all     # 列出全部待办，不只前 5 条

输出优先级：投料 → 阻塞修复 → 生产推进 → 上卷 → 知识复审 → 索引重建
"""
from __future__ import annotations

import json
import re
import sys
from datetime import date, datetime
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
DIMS = ["hook", "structure", "character", "visual", "performance",
        "sound", "text", "edit", "emotion", "spread"]
STAGE_NEXT = {
    "planned": ("拿到原片并落盘", "闸门 1：解析 aweme_id、下载、记 sha256"),
    "ingested": ("跑技术前处理", "闸门 2：抽帧/拼图/音频/Whisper/OCR/切点/黑场/曲线"),
    "prepped": ("逐格精读并写 beats.jsonl", "闸门 3：全片登记，字幕亲读定字（_pipeline/zoom.py 按秒号放大）"),
    "read": ("写十维卷与评估", "闸门 4：00–10 卷 + assessment.md"),
    "decomposed": ("跑 C5 自校验并修到 0 error", "闸门 5：python3 _pipeline/c5.py <wid>"),
    "blocked": ("先解阻塞", "看 profile 的 note 与 open-questions"),
}


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
    try:
        d = yaml.safe_load(t[3:i]) or {}
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def inbox_pending() -> list[str]:
    out = []
    p = ROOT / "_inbox" / "urls.txt"
    if not p.exists():
        return out
    status_p = ROOT / "_inbox" / "status.json"
    status = load(status_p) or {}
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if status.get(line) in ("done", "skipped"):
            continue
        out.append(line)
    return out


def works_stage() -> list[tuple[str, str, str]]:
    rows = []
    for p in sorted((ROOT / "works").glob("w-*/profile.json")):
        d = load(p)
        if not isinstance(d, dict):
            continue
        st = d.get("status", "planned")
        if st == "verified":
            continue
        wid = d.get("id", p.parent.name)
        cov = d.get("coverage") or {}
        if st in STAGE_NEXT:
            act, why = STAGE_NEXT[st]
            detail = f"{wid}《{d.get('title','')}》"
            if cov.get("beats_total"):
                detail += f" beats {cov.get('beats_registered',0)}/{cov['beats_total']}"
            if cov.get("dims_done") is not None:
                detail += f" 十维 {cov['dims_done']}/10"
            rows.append((act, detail, why))
    return rows


def knowledge_todo() -> list[tuple[str, str, str]]:
    rows = []
    work_index = {}
    for p in sorted((ROOT / "works").glob("w-*/profile.json")):
        d = load(p)
        if isinstance(d, dict) and d.get("id"):
            work_index[d["id"]] = d

    for p in sorted((ROOT / "knowledge").glob("kc-*.md")):
        d = fm(p)
        if not d:
            continue
        kid = d.get("id", p.stem)
        ss = d.get("sample_size") or 0
        cc = d.get("creator_count") or 0
        m = d.get("maturity")

        # 到期复审
        ra = str(d.get("review_after") or "")
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", ra) and date.today() > datetime.strptime(ra, "%Y-%m-%d").date():
            rows.append(("复审知识卡", f"{kid}《{d.get('title','')}》", f"已过复审期 {ra}：重判支持/收窄/推翻"))
            continue

        # 达标可升级
        if m == "observation" and ss >= 3 and cc >= 2:
            rows.append(("升级知识卡", f"{kid} 观察 → 模式", f"样本 {ss} / 博主 {cc} 已达模式门槛"))
        elif m == "observation" and ss >= 3 and cc < 2:
            # 这是最容易卡住的地方：一个博主拆得再多也升不了级，
            # 因为成熟度考的是"换个博主还成不成立"，不是"样本够不够多"。
            rows.append(("收编第二位博主", f"{kid} 已有 {ss} 部样本，但只来自 {cc} 位博主",
                         "跨博主验证才叫模式：再补 1 位博主的 3 部作品，或把结论降级为博主指纹"))
        elif m == "pattern" and ss >= 6 and cc >= 3:
            rows.append(("升级知识卡", f"{kid} 模式 → 规律", f"样本 {ss} / 博主 {cc} 已达规律门槛"))
        elif m == "rule" and ss >= 15 and cc >= 5:
            rows.append(("评估升定律", f"{kid} 规律 → 定律", "需再确认跨 3 题材 + 实战复现 1 次"))

    # 孤儿卡
    claimed = set()
    for w in work_index.values():
        kd = w.get("knowledge_delta") or {}
        claimed |= set((kd.get("added") or []) + (kd.get("revised") or []) + (kd.get("refuted") or []))
    for p in sorted((ROOT / "knowledge").glob("kc-*.md")):
        d = fm(p)
        if d.get("id") and d["id"] not in claimed:
            rows.append(("处理孤儿卡", f"{d['id']}《{d.get('title','')}》", "没有作品引用它：挂到触发它的作品，或删除"))
    return rows


def creator_todo() -> list[tuple[str, str, str]]:
    rows = []
    works = []
    for p in sorted((ROOT / "works").glob("w-*/profile.json")):
        d = load(p)
        if isinstance(d, dict):
            works.append(d)
    for p in sorted((ROOT / "creators").glob("c-*/profile.json")):
        d = load(p)
        if not isinstance(d, dict):
            continue
        cid = d.get("id", p.parent.name)
        mine = [w for w in works if w.get("creator_id") == cid]
        series = {w.get("series_id") for w in mine if w.get("series_id")}
        indep = len([w for w in mine if not w.get("series_id")]) + len(series)
        fc = d.get("fingerprint_confidence")
        if indep >= 4 and fc != "stable":
            rows.append(("重算作者指纹", f"{cid}《{d.get('name','')}》",
                         f"已有 {indep} 部独立作品，指纹可升到 stable"))
        elif indep >= 2 and fc in (None, "none", "single_work"):
            rows.append(("重算作者指纹", f"{cid}《{d.get('name','')}》",
                         f"已有 {indep} 部独立作品，指纹可升到 tendency"))
        # 矩阵缺格
        for w in mine:
            if w.get("status") == "verified" and not (w.get("assessment") or {}).get("hook"):
                rows.append(("补能力矩阵", f"{cid} ← {w.get('id')}", "该作品已 verified 但矩阵缺分"))
    return rows


def main() -> int:
    show_all = "--all" in sys.argv
    pending = inbox_pending()
    wrows = works_stage()
    krows = knowledge_todo()
    crows = creator_todo()

    mf = load(ROOT / "MANIFEST.json") or {}
    c = mf.get("counts", {})
    print(f"库版本 {mf.get('version','?')} ｜ 博主 {c.get('creators',0)} / 作品 {c.get('works',0)}"
          f" / beats {c.get('beats',0)} / 知识卡 {c.get('knowledge',0)}\n")

    bf = []
    for p in sorted((ROOT / "works").glob("w-*/profile.json")):
        d = load(p)
        if isinstance(d, dict) and d.get("status") == "backfilled":
            bf.append(f"{d['id']}《{d.get('title','')}》")

    groups = [
        ("投料待建档", [(f"处理 {u}", "闸门 0–1", "解析 aweme_id、查重、下载、登记") for u in pending], 5),
        ("作品推进", wrows, 5),
        ("知识层", krows, 5),
        ("博主层", crows, 3),
    ]
    total = 0
    for title, rows, cap in groups:
        if not rows:
            continue
        print(f"## {title}（{len(rows)}）")
        for act, detail, why in (rows if show_all else rows[:cap]):
            print(f"  - {act}｜{detail}｜{why}")
        if not show_all and len(rows) > cap:
            print(f"  … 还有 {len(rows)-cap} 条（--all 看全部）")
        print()
        total += len(rows)

    if total == 0:
        print("没有待办。下一步：往 _inbox/urls.txt 贴链接，或给一个博主主页做全量收编。")
        return 0
    if bf:
        print(f"> 另有 {len(bf)} 部为「档案回收」（backfilled）：beats 由既有 09 卷解析而来，"
              f"未过本库闸门 2。05 卷画面文字已由 text05.py 回填；要升 verified 还差九卷进库与十维评估（D-013）。")
        print(f"> 例：{'、'.join(bf[:5])}{' …' if len(bf) > 5 else ''}")
    print("规则：按顺序做，不要跳。做完一步重跑本命令。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
