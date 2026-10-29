#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_index.py · 重建机读索引、MANIFEST 与状态块

用法：
    python3 _pipeline/build_index.py            # 重建 catalog/*.json + MANIFEST.json + 状态块
    python3 _pipeline/build_index.py --check    # 只比对是否过期，不写盘（validate 调用）

纪律：catalog/、MANIFEST.json、START-HERE.md 的 STATUS 块都是本脚本的产物，
      手改会在下次运行被覆盖。要改内容，改 creators/ works/ knowledge/ 下的源文件。
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
CATALOG = ROOT / "catalog"
DIMS = ["hook", "structure", "character", "visual", "performance",
        "sound", "text", "edit", "emotion", "spread"]


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def load_json(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def read_frontmatter(p: Path) -> dict:
    """读 md 的 YAML frontmatter；坏文件返回 {}。"""
    try:
        text = p.read_text(encoding="utf-8")
    except Exception:
        return {}
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end == -1:
        return {}
    try:
        data = yaml.safe_load(text[3:end]) or {}
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


# ---------- 采集 ----------

def collect_creators() -> list[dict]:
    out = []
    for p in sorted((ROOT / "creators").glob("c-*/profile.json")):
        d = load_json(p)
        if not isinstance(d, dict):
            continue
        cid = d.get("id") or p.parent.name
        works = sorted((ROOT / "works").glob("w-*/profile.json"))
        mine = []
        for wp in works:
            wd = load_json(wp)
            if isinstance(wd, dict) and wd.get("creator_id") == cid:
                mine.append(wd)
        series = sorted({w.get("series_id") for w in mine if w.get("series_id")})
        independent = len([w for w in mine if not w.get("series_id")]) + len(series)
        out.append({
            "id": cid,
            "name": d.get("name", ""),
            "status": d.get("status", "planned"),
            "positioning": d.get("positioning", ""),
            "format": d.get("format", []),
            "tags": d.get("tags", []),
            "works_count": len(mine),
            "independent_works": independent,
            "series_ids": series,
            "fingerprint_confidence": d.get("fingerprint_confidence", "none"),
            "path": f"creators/{cid}/index.md",
            "profile": f"creators/{cid}/profile.json",
            "updated": d.get("updated", ""),
        })
    return out


def collect_works() -> list[dict]:
    out = []
    for p in sorted((ROOT / "works").glob("w-*/profile.json")):
        d = load_json(p)
        if not isinstance(d, dict):
            continue
        wid = d.get("id") or p.parent.name
        # beats 进度以文件实际内容为准，不信 coverage 自述
        bp = ROOT / "works" / wid / "beats.jsonl"
        expected = filled = 0
        if bp.exists():
            for line in bp.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                expected += 1
                try:
                    if (json.loads(line).get("visual") or "").strip():
                        filled += 1
                except Exception:
                    pass
        asmt = {k: d.get("assessment", {}).get(k) for k in DIMS}
        scored = {k: v for k, v in asmt.items() if isinstance(v, (int, float))}
        cov = d.get("coverage", {})
        out.append({
            "id": wid,
            "creator_id": d.get("creator_id"),
            "series_id": d.get("series_id"),
            "episode": d.get("episode"),
            "title": d.get("title", ""),
            "aweme_id": d.get("aweme_id"),
            "duration_ms": d.get("duration_ms", 0),
            "published_at": d.get("published_at"),
            "status": d.get("status", "planned"),
            "tags": d.get("tags", []),
            "assessment": asmt,
            "top_dim": max(scored, key=scored.get) if scored else None,
            "low_dim": min(scored, key=scored.get) if scored else None,
            "coverage": cov,
            "beats_expected": expected or cov.get("beats_total", 0),
            "beats_filled": filled,
            "beats_registered": filled,
            "beats_total": expected or cov.get("beats_total", 0),
            "c5_errors": cov.get("c5_errors"),
            "verified": d.get("status") == "verified",
            "path": f"works/{wid}/assessment.md",
            "beats": f"works/{wid}/beats.jsonl",
            "updated": d.get("updated", ""),
        })
    return out


def collect_knowledge() -> list[dict]:
    out = []
    for p in sorted((ROOT / "knowledge").glob("kc-*.md")):
        fm = read_frontmatter(p)
        if not fm:
            continue
        out.append({
            "id": fm.get("id") or p.stem.split("-")[0] + "-" + p.stem.split("-")[1],
            "type": fm.get("type"),
            "title": fm.get("title", ""),
            "claim": fm.get("claim", ""),
            "maturity": fm.get("maturity"),
            "sample_size": fm.get("sample_size", 0),
            "creator_count": fm.get("creator_count", 0),
            "confidence": fm.get("confidence"),
            "status": fm.get("status", "active"),
            "works": fm.get("works", []),
            "boundary": fm.get("boundary", ""),
            "review_after": fm.get("review_after", ""),
            "path": f"knowledge/{p.name}",
        })
    return out


def load_vocab() -> list[dict]:
    """读 vocab/elements.yaml 受控词表（含 name / desc）。"""
    p = ROOT / "vocab" / "elements.yaml"
    if not p.exists():
        return []
    try:
        d = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    except Exception:
        return []
    ns = d.get("namespaces") or {}
    out = []
    for e in d.get("elements") or []:
        if not isinstance(e, dict) or not e.get("id"):
            continue
        eid = e["id"]
        out.append({
            "id": eid,
            "namespace": eid.split(".")[0],
            "name": e.get("name", ""),
            "desc": e.get("desc", ""),
            "ns_desc": ns.get(eid.split(".")[0], ""),
        })
    return out


def collect_elements(works: list[dict]) -> tuple[list[dict], list[dict]]:
    """统计词表元素的实际使用情况。

    2026-10-30 修：原实现把 beats 里出现的任何标签直接写进 elements.json，
    而 validate 又拿这个文件当白名单——等于谁写谁合法。现在词表是手维护的
    （vocab/elements.yaml），这里只做两件事：
      1. 统计词表内每个元素被哪些作品用过、用了几次
      2. 把词表外的标签单独列进 unregistered，供 validate 报 ERROR
    """
    usage: dict[str, dict] = {}
    for w in works:
        bp = ROOT / "works" / w["id"] / "beats.jsonl"
        if not bp.exists():
            continue
        for line in bp.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                b = json.loads(line)
            except Exception:
                continue
            for f in b.get("func") or []:
                e = usage.setdefault(f, {"works": set(), "count": 0, "grids": []})
                e["works"].add(w["id"])
                e["count"] += 1
                if len(e["grids"]) < 8:
                    e["grids"].append(f"{w['id']}#{b.get('grid')}")

    vocab = load_vocab()
    known = {v["id"] for v in vocab}
    items = []
    for v in vocab:
        u = usage.get(v["id"])
        items.append({**v,
                      "works": sorted(u["works"]) if u else [],
                      "count": u["count"] if u else 0,
                      "sample_refs": u["grids"] if u else []})
    items.sort(key=lambda x: (-x["count"], x["id"]))

    unreg = []
    for eid, u in usage.items():
        if eid not in known:
            unreg.append({"id": eid, "works": sorted(u["works"]),
                          "count": u["count"], "sample_refs": u["grids"]})
    unreg.sort(key=lambda x: (-x["count"], x["id"]))
    return items, unreg


# ---------- 生成 ----------

def build() -> dict:
    CATALOG.mkdir(exist_ok=True)
    creators = collect_creators()
    works = collect_works()
    knowledge = collect_knowledge()
    # 方法层由 _pipeline/methods.py 从「创作方法论」七篇生成，本脚本只读不写，
    # 避免两个脚本抢同一个 catalog 文件的写权。
    mcat = load_json(CATALOG / "methods.json") or {}
    methods = mcat.get("items") or []
    elements, unregistered = collect_elements(works)

    beats_total = sum(w["beats_expected"] for w in works)
    beats_filled = sum(w["beats_filled"] for w in works)
    verified = [w for w in works if w["verified"]]

    docs = {
        "creators.json": {
            "schema": "../schemas/kb.schema.json#/definitions/creator",
            "updated": today(),
            "count": len(creators),
            "items": creators,
        },
        "works.json": {
            "schema": "../schemas/kb.schema.json#/definitions/work",
            "updated": today(),
            "count": len(works),
            "items": works,
        },
        "knowledge.json": {
            "schema": "../schemas/kb.schema.json#/definitions/knowledge",
            "updated": today(),
            "count": len(knowledge),
            "items": knowledge,
        },
        "elements.json": {
            "schema": None,
            "updated": today(),
            "count": len([x for x in elements if x["count"] > 0]),
            "vocab_size": len(elements),
            "note": "词表来自 vocab/elements.yaml（手维护，唯一授权源）；本文件只是使用统计。"
                    "unregistered 里的标签是词表外的非法使用，validate 会报 ERROR。",
            "unregistered": unregistered,
            "items": elements,
        },
    }

    # 总索引：紧凑、可一次读完，不含正文
    index = {
        "schema_version": 1,
        "updated": now_iso(),
        "counts": {
            "creators": len(creators),
            "works": len(works),
            "works_verified": len(verified),
            "beats": beats_filled,
            "beats_expected": beats_total,
            "knowledge": len(knowledge),
            "methods": len(methods),
            "methods_total": sum(m.get("methods_count", 0) for m in methods),
            "elements": len([x for x in elements if x["count"] > 0]),
            "elements_vocab": len(elements),
        },
        "routes": {
            "creator": "catalog/creators.json",
            "work": "catalog/works.json",
            "knowledge": "catalog/knowledge.json",
            "method": "catalog/methods.json",
            "element": "catalog/elements.json",
        },
        "budget": {"pages": 5, "beats_queries": 3, "dossier_volumes": 2, "never": ["load_full_dossier", "scan_all"]},
        "creators": creators,
        "works": works,
        "knowledge": knowledge,
        "methods": [{k: m.get(k) for k in
                     ("id", "type", "title", "one_line", "methods_count", "works", "path")}
                    for m in methods],
    }
    docs["index.json"] = index

    # MANIFEST
    ver = "0.1.0"
    # 方法层：比对每个维度登记的 source_sha256 与源文件实际哈希。
    # 源文件改了而 methods.py 没重跑，这里必须红——否则方法层会悄悄落后于源。
    import hashlib
    for it in ((load_json(CATALOG / "methods.json") or {}).get("items") or []):
        sp = Path(it.get("source") or "")
        if not sp.exists():
            problems.append(f"方法层 {it['id']} 的源文件不存在：{sp}")
            continue
        cur_hash = hashlib.sha256(sp.read_bytes()).hexdigest()
        if cur_hash != it.get("source_sha256"):
            problems.append(f"方法层 {it['id']} 已落后于源文件（sha256 不符），跑 methods.py 重建")

    mf = load_json(ROOT / "MANIFEST.json")
    if isinstance(mf, dict) and mf.get("version"):
        ver = mf["version"]
    manifest = {
        "kb": "抖音博主知识库",
        "version": ver,
        "schema_version": 1,
        "updated": now_iso(),
        "counts": index["counts"],
        "maturity": {
            "observation": len([k for k in knowledge if k["maturity"] == "observation"]),
            "pattern": len([k for k in knowledge if k["maturity"] == "pattern"]),
            "rule": len([k for k in knowledge if k["maturity"] == "rule"]),
            "law": len([k for k in knowledge if k["maturity"] == "law"]),
        },
        "capabilities": [
            "creator.profile", "creator.fingerprint", "creator.matrix",
            "work.assess", "work.beat", "work.text", "work.edit",
            "knowledge.query", "method.lookup", "element.search", "coverage.check", "kb.stats",
        ],
        "paths": {
            "kb": "KB.md", "agents": "AGENTS.md", "start": "START-HERE.md",
            "flow": "FLOW.md", "catalog": "catalog/index.json",
        },
    }

    return {"docs": docs, "manifest": manifest, "index": index}


def write(docs: dict, manifest: dict) -> None:
    for name, payload in docs.items():
        (CATALOG / name).write_text(
            json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    (ROOT / "MANIFEST.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    update_status_block(manifest)


STATUS_RE = re.compile(r"(<!-- STATUS:BEGIN -->)(.*?)(<!-- STATUS:END -->)", re.S)


def update_status_block(manifest: dict) -> None:
    p = ROOT / "START-HERE.md"
    if not p.exists():
        return
    c = manifest["counts"]
    m = manifest["maturity"]
    block = (
        "<!-- STATUS:BEGIN -->\n"
        "| 项 | 值 |\n|---|---|\n"
        f"| 库版本 | {manifest['version']} |\n"
        f"| 博主 | {c['creators']} |\n"
        f"| 作品 | {c['works']}（verified {c['works_verified']}） |\n"
        f"| 片段 beats | {c['beats']} / {c.get('beats_expected', 0)} 已登记 |\n"
        f"| 知识卡 | {c['knowledge']}（观察 {m['observation']} / 模式 {m['pattern']} / 规律 {m['rule']} / 定律 {m['law']}） |\n"
        f"| 元素标签 | 已用 {c['elements']} / 词表 {c.get('elements_vocab', 0)} |\n"
        f"| 最近重建 | {manifest['updated']} |\n"
        "<!-- STATUS:END -->"
    )
    text = p.read_text(encoding="utf-8")
    if STATUS_RE.search(text):
        text = STATUS_RE.sub(lambda _: block, text, count=1)
    else:
        text += "\n\n" + block + "\n"
    p.write_text(text, encoding="utf-8")


def strip_time(obj):
    """递归剔除时间戳字段，供内容级比对。"""
    if isinstance(obj, dict):
        return {k: strip_time(v) for k, v in obj.items() if k not in ("updated", "built_at", "generated_at")}
    if isinstance(obj, list):
        return [strip_time(x) for x in obj]
    return obj


def _first_diff(cur, new, path=""):
    """返回第一处差异的可读描述；无差异返回 None。"""
    if type(cur) is not type(new):
        return f"{path or '(root)'} 类型不同"
    if isinstance(new, dict):
        for k in sorted(set(cur) | set(new)):
            if k not in cur:
                return f"{path}/{k} 索引缺失"
            if k not in new:
                return f"{path}/{k} 索引多余（源文件已删）"
            d = _first_diff(cur[k], new[k], f"{path}/{k}")
            if d:
                return d
        return None
    if isinstance(new, list):
        if len(cur) != len(new):
            return f"{path} 条数 {len(cur)} → {len(new)}"
        for i, (a, b) in enumerate(zip(cur, new)):
            d = _first_diff(a, b, f"{path}[{i}]")
            if d:
                return d
        return None
    if cur != new:
        sc, sn = str(cur), str(new)
        if len(sc) > 40:
            sc = sc[:40] + "…"
        if len(sn) > 40:
            sn = sn[:40] + "…"
        return f"{path} 内容不同：索引 {sc!r} vs 源 {sn!r}"
    return None


def stale() -> list[str]:
    """比对磁盘与 catalog，返回过期项。

    2026-10-30 修：原实现只比 count 汇总数字，改标题、篡改条目一律抓不到。
    现改为内容级逐字段比对（剔除时间戳），并给出第一处差异位置。
    """
    problems = []
    built = build()
    for name, payload in built["docs"].items():
        p = CATALOG / name
        if not p.exists():
            problems.append(f"catalog/{name} 缺失")
            continue
        cur = load_json(p)
        if cur is None:
            problems.append(f"catalog/{name} 无法解析")
            continue
        diff = _first_diff(strip_time(cur), strip_time(payload))
        if diff:
            problems.append(f"catalog/{name} 与源文件不一致：{diff}（跑 build_index.py 重建，或撤销手改）")

    mf = load_json(ROOT / "MANIFEST.json")
    if not mf:
        problems.append("MANIFEST.json 缺失")
    else:
        diff = _first_diff(strip_time(mf), strip_time(built["manifest"]))
        if diff:
            problems.append(f"MANIFEST.json 与源文件不一致：{diff}")
    return problems


def sync_creator_counts() -> int:
    """把 works_count / independent_works / series_ids 回写到 creators/*/profile.json。

    这三个字段是从 works/ 算出来的派生值，而 profile.json 是手写源文件，
    所以常规构建不碰它。加/删作品后必须显式跑一次 --sync-creators，
    否则 profile 里的数字会永远停在建档时的 0（这正是 2026-10-30 查出的问题）。
    """
    works = collect_works()
    n = 0
    for p in sorted((ROOT / "creators").glob("c-*/profile.json")):
        d = load_json(p)
        if not isinstance(d, dict):
            continue
        cid = d.get("id")
        mine = [w for w in works if w.get("creator_id") == cid]
        series = sorted({w["series_id"] for w in mine if w.get("series_id")})
        indep = len([w for w in mine if not w.get("series_id")]) + len(series)
        changed = []
        for k, v in (("works_count", len(mine)), ("independent_works", indep),
                     ("series_ids", series)):
            if d.get(k) != v:
                d[k] = v
                changed.append(f"{k}→{v}")
        if changed:
            p.write_text(json.dumps(d, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
            print(f"SYNC {cid}：{'，'.join(changed)}")
            n += 1
    if n == 0:
        print("OK 博主派生计数已是最新")
    return n


def main() -> int:
    if "--sync-creators" in sys.argv:
        sync_creator_counts()
        return 0
    if "--check" in sys.argv:
        probs = stale()
        for p in probs:
            print("STALE", p)
        return 1 if probs else 0
    built = build()
    write(built["docs"], built["manifest"])
    c = built["manifest"]["counts"]
    print(f"OK 重建完成：博主 {c['creators']} / 作品 {c['works']}（verified {c['works_verified']}）"
          f" / beats {c['beats']}/{c.get('beats_expected',0)} / 知识卡 {c['knowledge']} / 元素 {c['elements']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
