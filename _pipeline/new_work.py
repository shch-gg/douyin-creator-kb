#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""new_work.py · 一条命令建档（作品 + 博主）

用法：
    python3 _pipeline/new_work.py --creator "煎饼果仔" --title "晒月光 第三集" \
        --aweme 7427807581223111999 --url "https://v.douyin.com/xxx/" \
        --duration-ms 215340 --published 2026-08-12T10:46:55Z \
        --series "晒月光" --episode 3

    python3 _pipeline/new_work.py --list          # 看已用 ID 与作品清单

做的事：查重 → 分配 w-NNNN（博主不存在则先建 c-NNNN）→ 建目录 → 写 profile.json 骨架。
不做：下载、抽帧、精读。那些是后续闸门。

纪律：ID 一旦分配不复用；目录名只用 ASCII；中文只进 title。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIMS = ["hook", "structure", "character", "visual", "performance",
        "sound", "text", "edit", "emotion", "spread"]


def today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def next_id(prefix: str, folder: Path) -> str:
    mx = 0
    for p in folder.glob(f"{prefix}-*"):
        m = re.fullmatch(rf"{prefix}-(\d{{4}})", p.name)
        if m:
            mx = max(mx, int(m.group(1)))
    return f"{prefix}-{mx + 1:04d}"


def load(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def find_creator(name: str):
    for p in sorted((ROOT / "creators").glob("c-*/profile.json")):
        d = load(p)
        if isinstance(d, dict) and (d.get("name") == name or name in (d.get("aliases") or [])):
            return d
    return None


CREATOR_INDEX_TPL = """# {name}

> 状态：profiled ｜ 更新：{date}

## 一句话定位

（收编后重写：给谁看、解决什么、凭什么被记住）

## 内容矩阵

| 形态 | 数量 | 代表作 | 说明 |
|---|---|---|---|
| — | — | — | 待收编 |

## 基础信息

| 项 | 值 |
|---|---|
| ID | `{cid}` |
| 抖音号 | {douyin} |
| 主页 | {homepage} |
| 更新节奏 | 待确认 |
| 已收编作品 | 0 |

## 代表作（待填）

## 指纹摘要

见 [fingerprint.md](fingerprint.md)（需 ≥2 部作品才能下判断）

## 备注
"""

FINGERPRINT_TPL = """# {name} · 作者指纹

> 定义：换一部片子，哪些东西**不变**。
> 纪律：每条指纹 ≥2 部支撑才可写"倾向"，≥4 部才可写"稳定手法"；必须写变体与反例。

当前置信度：**none**（0 部作品）

## 指纹表

| # | 维度 | 观察 | 支撑作品 | 变体 / 反例 | 置信度 |
|---|---|---|---|---|---|
| F-01 | 开场 | — | — | — | none |
| F-02 | 信息释放 | — | — | — | none |
| F-03 | 文字系统 | — | — | — | none |
| F-04 | 镜头 | — | — | — | none |
| F-05 | 声音 | — | — | — | none |
| F-06 | 转场 | — | — | — | none |
| F-07 | 母题 | — | — | — | none |
| F-08 | 集末钩子 | — | — | — | none |

## 详细记录

（每条指纹展开：观察、证据秒号、变体、反例、可复制动作）
"""

MATRIX_TPL = """# {name} · 能力矩阵

> 十维 × 每部作品，0–10。空格写 `—` 并在表下说明未评原因。
> 作用：看同一人在不同题材上的强弱漂移，不是排名。

| 作品 | 时长 | 钩子 | 结构 | 人物 | 视听 | 表演 | 声音 | 文字 | 剪辑 | 情绪 | 传播 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| — | — | — | — | — | — | — | — | — | — | — | — |

## 未评说明

## 强弱结论（≥3 部后才写）
"""

TRAJECTORY_TPL = """# {name} · 生长轨迹

> 按 `published_at` 升序。只写有证据的变化，不许把"时间顺序"当"在进步"。

| 序 | 作品 | 发布 | 变化 | 类型 |
|---|---|---|---|---|
| — | — | — | — | — |

类型：`转折点` / `能力跃迁` / `退化` / `未见变化`

## 说明
"""


def create_creator(name: str, douyin: str | None, homepage: str | None) -> dict:
    cid = next_id("c", ROOT / "creators")
    d = ROOT / "creators" / cid
    d.mkdir(parents=True, exist_ok=True)
    prof = {
        "id": cid,
        "name": name,
        "aliases": [],
        "douyin_id": douyin,
        "homepage": homepage,
        "status": "profiled",
        "positioning": "",
        "format": [],
        "tags": [],
        "cadence": None,
        "works_count": 0,
        "independent_works": 0,
        "series_ids": [],
        "matrix": {},
        "fingerprint_confidence": "none",
        "platform": {"followers": None, "total_likes": None, "captured_at": None},
        "paths": {
            "index": f"creators/{cid}/index.md",
            "fingerprint": f"creators/{cid}/fingerprint.md",
            "matrix": f"creators/{cid}/matrix.md",
            "trajectory": f"creators/{cid}/trajectory.md",
        },
        "created_at": now_iso(),
        "updated": today(),
    }
    (d / "profile.json").write_text(json.dumps(prof, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    ctx = {"name": name, "cid": cid, "date": today(),
           "douyin": douyin or "待确认", "homepage": homepage or "待确认"}
    (d / "index.md").write_text(CREATOR_INDEX_TPL.format(**ctx), encoding="utf-8")
    (d / "fingerprint.md").write_text(FINGERPRINT_TPL.format(**ctx), encoding="utf-8")
    (d / "matrix.md").write_text(MATRIX_TPL.format(**ctx), encoding="utf-8")
    (d / "trajectory.md").write_text(TRAJECTORY_TPL.format(**ctx), encoding="utf-8")
    print(f"新建博主 {cid}《{name}》")
    return prof


def series_id_for(name: str) -> str:
    """中文系列名 → 稳定的 s-NNNN。已存在同名映射则复用，否则分配新号。"""
    mp_path = ROOT / "_pipeline" / "series_map.json"
    mp = load(mp_path) or {}
    for sid, sname in mp.items():
        if sname == name:
            return sid
    mx = 0
    for sid in mp:
        m = re.fullmatch(r"s-(\d{4})", sid)
        if m:
            mx = max(mx, int(m.group(1)))
    sid = f"s-{mx + 1:04d}"
    mp[sid] = name
    mp_path.write_text(json.dumps(mp, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return sid


def dup_check(aweme: str | None, title: str, duration_ms: int | None) -> tuple[str, str] | None:
    """返回 (级别, 说明)。级别 = block（同一 aweme_id，拒绝建档）/ warn（疑似同素材换 ID）。

    2026-10-30 修：原实现只在**没有** aweme_id 时才比 title+duration，
    于是同一部片换了个 aweme_id（抖音重发、多平台搬运）会被当成新作品收进来，
    而 AGENTS 规则 9 明令「同一素材多平台分发只算 1 部」。
    现在两道都查：aweme 命中直接拦；aweme 不同但标题+时长吻合，给出疑似提示让人判断。
    """
    for p in sorted((ROOT / "works").glob("w-*/profile.json")):
        d = load(p)
        if not isinstance(d, dict):
            continue
        if aweme and d.get("aweme_id") == aweme:
            return ("block", f"aweme_id 重复：{d.get('id')}《{d.get('title')}》")
        same_title = d.get("title") == title
        same_dur = (duration_ms is not None
                    and d.get("duration_ms") is not None
                    and abs(d["duration_ms"] - duration_ms) <= 1000)
        if same_title and same_dur:
            why = "aweme_id 不同" if aweme and d.get("aweme_id") != aweme else "无 aweme_id"
            return ("warn", f"标题+时长与 {d.get('id')}《{d.get('title')}》吻合（{why}）："
                            f"若是同一素材换 ID 重发，按规则 9 只算 1 部，请确认后加 --force")
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--creator")
    ap.add_argument("--creator-id")
    ap.add_argument("--title")
    ap.add_argument("--aweme")
    ap.add_argument("--url")
    ap.add_argument("--duration-ms", type=int)
    ap.add_argument("--published")
    ap.add_argument("--series")
    ap.add_argument("--episode", type=int)
    ap.add_argument("--force", action="store_true",
                    help="标题+时长吻合但确认不是同一素材时，跳过疑似重复拦截")
    a = ap.parse_args()

    if a.list:
        for p in sorted((ROOT / "creators").glob("c-*/profile.json")):
            d = load(p) or {}
            print(f"{d.get('id')}  {d.get('name')}  works={d.get('works_count')}")
        for p in sorted((ROOT / "works").glob("w-*/profile.json")):
            d = load(p) or {}
            print(f"{d.get('id')}  {d.get('creator_id')}  《{d.get('title')}》  {d.get('status')}")
        return 0

    if not (a.creator and a.title):
        ap.error("至少给 --creator 和 --title")

    hit = dup_check(a.aweme, a.title, a.duration_ms)
    if hit:
        level, why = hit
        if level == "block":
            print(f"拒绝建档：{why}")
            return 2
        if not a.force:
            print(f"疑似重复：{why}")
            return 2
        print(f"WARN {why}")

    creator = None
    if a.creator_id:
        p = ROOT / "creators" / a.creator_id / "profile.json"
        creator = load(p) if p.exists() else None
    creator = creator or find_creator(a.creator)
    if not creator:
        creator = create_creator(a.creator, None, None)

    wid = next_id("w", ROOT / "works")
    wd = ROOT / "works" / wid
    for sub in ("media", "data", "frames", "contact", "dossier"):
        (wd / sub).mkdir(parents=True, exist_ok=True)

    prof = {
        "id": wid,
        "creator_id": creator["id"],
        "series_id": None,
        "episode": a.episode,
        "title": a.title,
        "aweme_id": a.aweme,
        "url": a.url,
        "duration_ms": a.duration_ms or 0,
        "published_at": a.published,
        "status": "planned",
        "platform": {"digg": None, "comment": None, "share": None,
                     "collect": None, "play": None, "hashtags": [], "music": None},
        "source": {"type": "pointer", "path": f"works/{wid}/media/raw.mp4", "sha256": "", "bytes": 0},
        "spec": {},
        "tags": [],
        "coverage": {"beats_total": 0, "beats_registered": 0, "dims_total": 10,
                     "dims_done": 0, "c5_errors": 0, "c5_warns": 0, "ending_checked": False},
        "assessment": {k: None for k in DIMS},
        "knowledge_delta": {"added": [], "revised": [], "refuted": [], "none_reason": ""},
        "paths": {"beats": f"works/{wid}/beats.jsonl",
                  "assessment": f"works/{wid}/assessment.md",
                  "dossier": f"works/{wid}/dossier/",
                  "data": f"works/{wid}/data/"},
        "created_at": now_iso(),
        "updated": today(),
    }
    if a.series:
        prof["series_id"] = series_id_for(a.series)
    (wd / "profile.json").write_text(json.dumps(prof, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    print(f"新建作品 {wid}《{a.title}》→ 博主 {creator['id']}《{creator['name']}》")
    print(f"目录 works/{wid}/（media data frames contact dossier）")
    print("下一步：落原片 → 记 sha256 → status=ingested；或跑 next_task.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
