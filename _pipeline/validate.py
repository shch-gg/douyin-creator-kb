#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""validate.py · 全库一致性校验

用法：
    python3 _pipeline/validate.py           # 全量校验
    python3 _pipeline/validate.py --quiet   # 只输出错误

分级：ERROR 阻断（不得标 verified / 不得发布）；WARN 需逐条说明。
纪律：ERROR 未清零前，任何"已完成"的声明都不成立。
"""
from __future__ import annotations

import json
import re
import sys
from datetime import date, datetime
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from kbtext import has_md  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DIMS = ["hook", "structure", "character", "visual", "performance",
        "sound", "text", "edit", "emotion", "spread"]
MATURITY_MIN = {"observation": (1, 999, 1, 1), "pattern": (3, 999, 2, 999),
                "rule": (6, 999, 3, 999), "law": (15, 999, 5, 999)}
# 成熟度的本质是**跨博主验证**，不是样本量。
# 2026-10-30 修：原 observation 限 sample_size≤2，导致「单博主 3 部作品」
# 既超 observation 上限、又够不上 pattern 的 creator_count≥2，无路可走。
# 现改为 observation = creator_count 恰为 1（单博主，样本量不限），
# 措辞上再分「单部观察」(n=1) 与「单博主观察」(n≥2)。
REQUIRED_TOP = ["KB.md", "AGENTS.md", "START-HERE.md", "FLOW.md", "MANIFEST.json"]
REQUIRED_CATALOG = ["index.json", "creators.json", "works.json", "knowledge.json", "elements.json"]
BAD_PATH = re.compile(r"[^\x00-\x7f]|\s")

# 值域白名单。拼错的枚举值会让所有状态机检查静默跳过——这是最危险的失效模式，
# 所以非法值必须当 ERROR，不能当"不认识就放行"。
STATUS_WORK = {"planned", "ingested", "prepped", "backfilled", "read",
               "decomposed", "verified", "blocked"}
STATUS_CREATOR = {"stub", "profiled", "verified", "blocked"}
STATUS_KNOWLEDGE = {"active", "narrowed", "refuted", "superseded"}
CONFIDENCE = {"none", "single_work", "tendency", "stable"}
EVIDENCE_GRADE = {"E1", "E2", "E3", "G"}

errors: list[str] = []
warns: list[str] = []


def err(msg: str) -> None:
    errors.append(msg)


def warn(msg: str) -> None:
    warns.append(msg)


def load(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        err(f"{p.relative_to(ROOT)} 无法解析：{e}")
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
    except Exception as e:
        err(f"{p.relative_to(ROOT)} frontmatter 解析失败：{e}")
        return {}


# ---------- schema 驱动检查 ----------

SCHEMA_CACHE: dict = {}


def schema_req(kind: str) -> list[str]:
    """从 schemas/kb.schema.json 读某类的 required 列表。

    2026-10-30 补：这个 schema 文件写了 242 行，却没有任何脚本加载过它，
    validate 里的字段检查是另抄一份的，两边会悄悄走形。现在必填字段以
    schema 为单一来源，validate 只负责执行。
    """
    if not SCHEMA_CACHE:
        p = ROOT / "schemas" / "kb.schema.json"
        if not p.exists():
            err("缺 schemas/kb.schema.json（字段定义的单一来源）")
            SCHEMA_CACHE["_missing"] = True
            return []
        d = load(p) or {}
        SCHEMA_CACHE.update(d.get("definitions") or {})
    if SCHEMA_CACHE.get("_missing"):
        return []
    return list((SCHEMA_CACHE.get(kind) or {}).get("required") or [])


def check_schema(obj: dict, kind: str, label: str) -> None:
    for k in schema_req(kind):
        if k not in obj or obj[k] in (None, "", []):
            err(f"{label} 缺 schema 必填字段 {k}（schemas/kb.schema.json → definitions.{kind}）")


def schema_props(kind: str) -> set[str]:
    if not SCHEMA_CACHE:
        schema_req(kind)
    return set(((SCHEMA_CACHE.get(kind) or {}).get("properties") or {}).keys())


def _type_ok(v, t) -> bool:
    """JSON Schema type 的最小子集。bool 不算 number——Python 里 True==1，会漏判。"""
    if t == "string":
        return isinstance(v, str)
    if t == "number":
        return isinstance(v, (int, float)) and not isinstance(v, bool)
    if t == "integer":
        return isinstance(v, int) and not isinstance(v, bool)
    if t == "array":
        return isinstance(v, list)
    if t == "object":
        return isinstance(v, dict)
    if t == "boolean":
        return isinstance(v, bool)
    if t == "null":
        return v is None
    return True


def check_field_value(v, spec: dict, where: str) -> None:
    """字段级校验：type / enum / pattern。

    2026-10-30 加。此前 validate 只读 schema 的 required 与 properties 名单，
    枚举与类型一律不管——`sub_src: "abc"`、`screen: 123` 都能过。
    规则不生效等于没写（selftest 用例 9/10 就是拿这两种违规来钉它）。
    """
    t = spec.get("type")
    if t:
        ts = t if isinstance(t, list) else [t]
        if not any(_type_ok(v, x) for x in ts):
            err(f"{where} 字段类型不合 schema（值 {v!r}，允许 {'/'.join(ts)}）")
            return
    en = spec.get("enum")
    if en is not None and v not in en:
        err(f"{where} 不在值域 {en}（当前 {v!r}）")
    pat = spec.get("pattern")
    if pat and isinstance(v, str) and not re.fullmatch(pat, v):
        err(f"{where} 不符 pattern {pat}（当前 {v!r}）")


# ---------- 1. 必需文件 ----------

def check_files() -> None:
    for f in REQUIRED_TOP:
        if not (ROOT / f).exists():
            err(f"缺必需文件 {f}")
    for f in REQUIRED_CATALOG:
        if not (ROOT / "catalog" / f).exists():
            err(f"缺索引 catalog/{f}（跑 build_index.py）")


# ---------- 2. 路径合规 ----------

def check_paths() -> None:
    """ID 层（creators/works/knowledge/catalog）必须 ASCII；文档层允许中文；全库禁止空格。"""
    skip = {"_会话记忆", "_inbox"}
    ascii_dirs = {"creators", "works", "knowledge", "catalog", "schemas"}
    for p in ROOT.rglob("*"):
        if not p.is_file():
            continue
        rel = p.relative_to(ROOT)
        if rel.parts[0] in skip:
            continue
        if re.search(r"\s", p.name):
            err(f"文件名含空格：{rel}")
            continue
        if rel.parts[0] in ascii_dirs and BAD_PATH.search(p.name):
            err(f"ID 层路径含非 ASCII：{rel}（ID 目录只准 [a-z0-9._-]）")


# ---------- 3. 博主 ----------

def check_creators() -> tuple[list, dict]:
    items = []
    by_id = {}
    for p in sorted((ROOT / "creators").glob("c-*/profile.json")):
        d = load(p)
        if not isinstance(d, dict):
            continue
        cid = d.get("id")
        if not cid or not re.fullmatch(r"c-\d{4}", cid):
            err(f"{p.parent.name}/profile.json id 不合规：{cid}")
            continue
        if cid in by_id:
            err(f"博主 ID 重复：{cid}")
        if p.parent.name != cid:
            err(f"目录名 {p.parent.name} 与 id {cid} 不一致")
        check_schema(d, "creator", cid)
        st = d.get("status")
        if st and st not in STATUS_CREATOR:
            err(f"{cid} status='{st}' 不在值域 {sorted(STATUS_CREATOR)}（拼错会让状态检查静默跳过）")
        fc = d.get("fingerprint_confidence")
        if fc not in CONFIDENCE:
            err(f"{cid} fingerprint_confidence='{fc}' 不在值域 {sorted(CONFIDENCE)}")
        if d.get("status") == "verified":
            for f in ("index", "fingerprint", "matrix", "trajectory"):
                rel = d.get("paths", {}).get(f)
                if not rel or not (ROOT / rel).exists():
                    err(f"{cid} 状态 verified 但缺 {f} 页")
            fc = d.get("fingerprint_confidence")
            if fc in (None, "none", "single_work"):
                warn(f"{cid} verified 但指纹置信度仅 {fc}：作者指纹需 ≥2 部支撑")
        by_id[cid] = d
        items.append(d)
    return items, by_id


# ---------- 4. 作品 ----------

def gate2_missing(wd: Path) -> list[str]:
    """闸门2「技术前处理」产物自检（与 make_beats_skeleton.py 口径一致）。"""
    miss = [f for f in ("data/meta_raw.json", "data/cuts.txt") if not (wd / f).exists()]
    if not (wd / "frames").exists() or not list((wd / "frames").glob("f_*.jpg")):
        miss.append("frames/ 抽帧")
    if not (wd / "contact").exists() or not list((wd / "contact").glob("c_*.jpg")):
        miss.append("contact/ 拼图")
    data = wd / "data"
    jsons = [p.name for p in data.glob("*.json")] if data.exists() else []
    if not any(n.startswith("ocr") for n in jsons):
        miss.append("data/ocr.json")
    if not [n for n in jsons if not n.startswith("ocr") and n != "meta_raw.json"]:
        miss.append("Whisper json")
    return miss


def check_works(creator_by_id: dict) -> tuple[list, dict]:
    items = []
    by_id = {}
    seen_aweme = {}
    for p in sorted((ROOT / "works").glob("w-*/profile.json")):
        d = load(p)
        if not isinstance(d, dict):
            continue
        wid = d.get("id")
        if not wid or not re.fullmatch(r"w-\d{4}", wid):
            err(f"{p.parent.name} id 不合规：{wid}")
            continue
        if wid in by_id:
            err(f"作品 ID 重复：{wid}")
        if p.parent.name != wid:
            err(f"目录名 {p.parent.name} 与 id {wid} 不一致")
        by_id[wid] = d
        items.append(d)

        cid = d.get("creator_id")
        if cid not in creator_by_id:
            err(f"{wid} 的 creator_id {cid} 不存在")
        check_schema(d, "work", wid)
        if not isinstance(d.get("duration_ms"), int) or d["duration_ms"] <= 0:
            err(f"{wid} duration_ms 非法：{d.get('duration_ms')}")

        aw = d.get("aweme_id")
        if aw:
            if aw in seen_aweme:
                err(f"aweme_id 重复：{aw}（{seen_aweme[aw]} 与 {wid}）")
            seen_aweme[aw] = wid
        else:
            warn(f"{wid} 无 aweme_id，查重只能靠 title+duration")

        # 平台数据不许用 0 冒充 null
        plat = d.get("platform") or {}
        for k, v in plat.items():
            if isinstance(v, int) and v == 0 and k != "play":
                warn(f"{wid} platform.{k}=0，确认是真实 0 还是抓取失败")

        cov = d.get("coverage") or {}
        st = d.get("status")
        if st and st not in STATUS_WORK:
            err(f"{wid} status='{st}' 不在值域 {sorted(STATUS_WORK)}"
                f"（拼错会让 beats/十维/C5/ending 检查全部静默跳过）")

        # 状态推进条件
        if st in ("prepped", "read", "decomposed", "verified"):
            miss = gate2_missing(ROOT / "works" / wid)
            if miss:
                err(f"{wid} 状态 {st} 但闸门2 产物缺失：{'、'.join(miss)}"
                    f"（status 谎报；要么补产物，要么退回 ingested）")
        if st in ("read", "decomposed", "verified"):
            bt, br = cov.get("beats_total"), cov.get("beats_registered")
            if not bt or br != bt:
                err(f"{wid} 状态 {st} 但 beats 未全覆盖（{br}/{bt}）")
        # backfilled：从既有档案回收。库内闸门2 没重跑，所以不查 frames/，但必须
        # ① beats 全覆盖（解析不出来的格是档案缺口，要写进 profile.gaps）
        # ② note 说清来源，避免后人当成「本库亲自拆过」
        if st == "backfilled":
            bt, br = cov.get("beats_total"), cov.get("beats_registered")
            gaps = d.get("gaps") or []
            if not bt:
                err(f"{wid} backfilled 但 beats_total={bt}")
            elif br != bt and len(gaps) == 0:
                err(f"{wid} backfilled 但 beats 只登记 {br}/{bt}，且未在 gaps 声明缺口")
            if "backfill" not in (d.get("note") or ""):
                err(f"{wid} backfilled 但 note 未标注来源（原始档案路径）")
        if st in ("decomposed", "verified"):
            done = cov.get("dims_done", 0)
            if done < 10:
                err(f"{wid} 状态 {st} 但十维只完成 {done}/10")
            if not (ROOT / "works" / wid / "assessment.md").exists():
                err(f"{wid} 状态 {st} 但缺 assessment.md")
        if st == "verified":
            if cov.get("c5_errors") != 0:
                err(f"{wid} verified 但 c5_errors={cov.get('c5_errors')}")
            if not cov.get("ending_checked"):
                err(f"{wid} verified 但 ending_checked=false（未看结尾不得下结论）")
            a = d.get("assessment") or {}
            missing = [k for k in DIMS if not isinstance(a.get(k), (int, float))]
            if missing:
                err(f"{wid} verified 但十维缺分：{missing}")
            kd = d.get("knowledge_delta") or {}
            if not (kd.get("added") or kd.get("revised") or kd.get("refuted") or kd.get("none_reason")):
                err(f"{wid} verified 但 knowledge_delta 为空（必须写动了什么，或写 none_reason）")
        a = d.get("assessment") or {}
        for k in a:
            if k not in DIMS:
                err(f"{wid} assessment 出现非标准维名 {k}（会静默漏统计）")
    return items, by_id


# ---------- 5. 博主派生计数 ----------

def check_creator_counts(creators: list[dict], works: list[dict]) -> None:
    """博主 profile 的派生计数必须与磁盘一致。

    这是 AGENTS 规则 10「同步六处」里最容易被忽略的一处：build_index 算对了
    写进 catalog/creators.json，但 profile.json 里那三个字段没人回写，于是
    同一事实存在两份数字，一份永远停在建档时的 0。
    """
    for c in creators:
        cid = c["id"]
        mine = [w for w in works if w.get("creator_id") == cid]
        series = sorted({w["series_id"] for w in mine if w.get("series_id")})
        indep = len([w for w in mine if not w.get("series_id")]) + len(series)
        if c.get("works_count") != len(mine):
            err(f"{cid} works_count={c.get('works_count')} 与实际 {len(mine)} 部不符"
                f"（跑 build_index.py --sync-creators）")
        if c.get("independent_works") != indep:
            err(f"{cid} independent_works={c.get('independent_works')} 与去重后 {indep} 部不符"
                f"（同系列只算 1 部；跑 build_index.py --sync-creators）")
        if sorted(c.get("series_ids") or []) != series:
            err(f"{cid} series_ids={c.get('series_ids')} 与实际 {series} 不符"
                f"（跑 build_index.py --sync-creators）")


# ---------- 6. beats ----------

def check_beats(works: list[dict], elements: set[str]) -> int:
    total = 0
    allowed_beat_fields = schema_props("beat")
    for w in works:
        wid = w["id"]
        p = ROOT / "works" / wid / "beats.jsonl"
        if not p.exists():
            if w.get("status") in ("read", "decomposed", "verified"):
                err(f"{wid} 缺 beats.jsonl")
            continue
        prev_t1 = None
        prev_grid = 0
        n = 0
        for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            line = line.strip()
            if not line:
                continue
            try:
                b = json.loads(line)
            except Exception as e:
                err(f"{wid} beats.jsonl 第 {i} 行解析失败：{e}")
                continue
            n += 1
            g = b.get("grid", "")
            m = re.fullmatch(r"c-(\d{2,3})", g)
            if not m:
                err(f"{wid} beats.jsonl 第 {i} 行 grid 不合规：{g}")
            else:
                gi = int(m.group(1))
                if gi != prev_grid + 1:
                    err(f"{wid} grid 不连续：第 {i} 行 {g}，上一格 c-{prev_grid:02d}")
                prev_grid = gi
            t0, t1 = b.get("t0"), b.get("t1")
            if not isinstance(t0, (int, float)) or not isinstance(t1, (int, float)):
                err(f"{wid} beats.jsonl 第 {i} 行 t0/t1 非法")
            else:
                if t1 <= t0:
                    err(f"{wid} {g} t1({t1}) <= t0({t0})")
                if prev_t1 is None:
                    if abs(t0) > 0.001:
                        err(f"{wid} 首格 t0={t0}，应从 0 开始")
                else:
                    # t0/t1 是连续区间 [4(N-1), 4N)，相邻格必须严丝合缝。
                    # 2026-10-30 修：原实现允许 0–1s 间隔，理由是"4 秒格按秒点记"，
                    # 结果 [0,3] 与 [4,7] 之间的 3–4 秒无人覆盖，
                    # AGENTS「每行 t0/t1 连续无缝」形同虚设。
                    gap = t0 - prev_t1
                    if abs(gap) > 0.001:
                        err(f"{wid} {g} 与上一格不衔接：t0={t0}，上格 t1={prev_t1}"
                            f"（差 {gap:+.3f}s，区间必须首尾相接）")
                prev_t1 = t1
            if not (b.get("visual") or "").strip():
                err(f"{wid} {g} visual 为空（画面亲读必填）")
            # 文本字段只装内容，不装 markdown 渲染标记。
            # 09/05 卷正文用 `**加粗**` 排版，搬进 beats 会让检索失效
            # （搜「山茶」搜不到存成 `**山茶**` 的那条）。清洗规则见 _pipeline/kbtext.py。
            for _f in ("visual", "sub", "screen"):
                if has_md(b.get(_f) or ""):
                    err(f"{wid} {g} {_f} 含 markdown 标记，须用 kbtext.demd 清洗")
            extra = set(b) - allowed_beat_fields
            if extra:
                err(f"{wid} {g} beats 出现 schema 未声明字段 {sorted(extra)}（会静默漏统计）")
            # 字段级：type / enum / pattern。schema 写在文件里没人读，等于没写。
            for _k, _spec in (SCHEMA_CACHE.get("beat") or {}).get("properties", {}).items():
                if _k in b:
                    check_field_value(b[_k], _spec, f"{wid} {g} 字段 {_k}")
            for f in b.get("func") or []:
                if f not in elements:
                    err(f"{wid} {g} 元素标签 {f} 未登记")
        # 末格应贴近片长
        dur = w["duration_ms"] / 1000
        if prev_t1 is not None and abs(prev_t1 - dur) > 2:
            warn(f"{wid} beats 末格 t1={prev_t1}s 与片长 {dur:.3f}s 相差 >2s")
        cov = w.get("coverage") or {}
        if cov.get("beats_registered") and cov["beats_registered"] != n:
            err(f"{wid} coverage.beats_registered={cov['beats_registered']} 与实际 {n} 行不符")
        total += n
    return total


# ---------- 6. 知识卡 ----------

def check_knowledge(works_by_id: dict, creator_by_id: dict) -> None:
    claimed: set[str] = set()
    for w in works_by_id.values():
        kd = w.get("knowledge_delta") or {}
        for k in (kd.get("added") or []) + (kd.get("revised") or []) + (kd.get("refuted") or []):
            claimed.add(k)

    for p in sorted((ROOT / "knowledge").glob("kc-*.md")):
        d = fm(p)
        if not d:
            err(f"{p.name} 无 frontmatter")
            continue
        kid = d.get("id")
        if not kid or not re.fullmatch(r"kc-\d{3}", kid):
            err(f"{p.name} id 不合规：{kid}")
            continue
        for k in ("type", "title", "claim", "maturity", "sample_size", "creator_count",
                  "confidence", "status", "works"):
            if d.get(k) in (None, "", []):
                err(f"{kid} 缺字段 {k}")
        if d.get("type") not in DIMS and d.get("type") not in ("series",):
            err(f"{kid} type 非标准：{d.get('type')}")
        if d.get("maturity") not in MATURITY_MIN:
            err(f"{kid} maturity='{d.get('maturity')}' 不在值域 {sorted(MATURITY_MIN)}")
        if d.get("confidence") not in ("low", "medium", "high"):
            err(f"{kid} confidence='{d.get('confidence')}' 不在值域 low|medium|high")
        if d.get("status") not in STATUS_KNOWLEDGE:
            err(f"{kid} status='{d.get('status')}' 不在值域 {sorted(STATUS_KNOWLEDGE)}")

        # 成熟度门槛
        m = d.get("maturity")
        ss = d.get("sample_size") or 0
        cc = d.get("creator_count") or 0
        if m in MATURITY_MIN:
            lo_s, hi_s, lo_c, hi_c = MATURITY_MIN[m]
            if not (lo_s <= ss <= hi_s):
                err(f"{kid} maturity={m} 但 sample_size={ss}（应 {lo_s}–{hi_s}）")
            if cc < lo_c:
                err(f"{kid} maturity={m} 但 creator_count={cc} < {lo_c}")

        # 样本与 works 一致（按系列去重）
        ws = d.get("works") or []
        series = set()
        indep = 0
        for wid in ws:
            w = works_by_id.get(wid)
            if not w:
                err(f"{kid} 引用了不存在的作品 {wid}")
                continue
            if w.get("series_id"):
                series.add(w["series_id"])
            else:
                indep += 1
        eff = indep + len(series)
        if eff != ss:
            err(f"{kid} sample_size={ss} 与 works 去重后 {eff} 不符（系列算 1 部）")

        # 证据必须带秒号
        for e in d.get("evidence") or []:
            if not isinstance(e, dict) or not e.get("at"):
                err(f"{kid} evidence 缺 at（秒号）")
            elif not re.match(r"t=\d", str(e["at"])):
                warn(f"{kid} evidence.at 格式不像 t=NNNs：{e['at']}")

        # 反例与边界
        if not isinstance(d.get("counterexamples"), list):
            warn(f"{kid} 未写 counterexamples 字段（找不到反例也要写清为什么）")
        if not d.get("boundary"):
            warn(f"{kid} 未写 boundary（适用边界）")

        # 版本与复审
        if not isinstance(d.get("revisions"), list) or not d["revisions"]:
            err(f"{kid} 缺 revisions（每次升版必须留痕）")
        ra = d.get("review_after")
        if ra:
            try:
                if datetime.strptime(str(ra), "%Y-%m-%d").date() < date.today() and d.get("status") == "active":
                    warn(f"{kid} 已过复审期 {ra}，需复核")
            except ValueError:
                warn(f"{kid} review_after 格式非 YYYY-MM-DD：{ra}")
        else:
            warn(f"{kid} 缺 review_after（到期复审是生长机制的一部分）")

        # 状态字段自洽
        st = d.get("status")
        if st == "refuted" and not d.get("refuted_by"):
            err(f"{kid} status=refuted 但 refuted_by 为空")
        if st == "superseded" and not d.get("superseded_by"):
            err(f"{kid} status=superseded 但 superseded_by 为空")
        if st == "narrowed" and not d.get("narrowed_to"):
            err(f"{kid} status=narrowed 但 narrowed_to 为空")

        # 孤儿卡
        if kid not in claimed:
            err(f"{kid} 是孤儿卡：没有任何作品 knowledge_delta 引用它（说明没触发它的样本）")


# ---------- 7. 索引与状态块 ----------

def check_index() -> None:
    import subprocess
    r = subprocess.run([sys.executable, str(ROOT / "_pipeline" / "build_index.py"), "--check"],
                       capture_output=True, text=True)
    for line in (r.stdout or "").splitlines():
        if line.startswith("STALE"):
            err(line.replace("STALE ", "索引过期："))

    sp = ROOT / "START-HERE.md"
    if sp.exists():
        t = sp.read_text(encoding="utf-8")
        if "<!-- STATUS:BEGIN -->" not in t:
            warn("START-HERE.md 缺 STATUS 块（跑 build_index.py 生成）")
        else:
            mf = load(ROOT / "MANIFEST.json") or {}
            c = mf.get("counts", {})
            seg = t.split("<!-- STATUS:BEGIN -->")[1].split("<!-- STATUS:END -->")[0]
            for label, val in (("博主", c.get("creators")), ("作品", c.get("works")),
                               ("知识卡", c.get("knowledge"))):
                if val is not None and f"| {label} | {val}" not in seg:
                    warn(f"START-HERE 状态块 {label} 计数与 MANIFEST 不一致（重跑 build_index）")


# ---------- 元素词表 ----------

def load_vocab() -> set[str]:
    """元素白名单来自 vocab/elements.yaml（手维护的受控词表）。

    2026-10-30 修：原实现拿 catalog/elements.json 当白名单，而那个文件本身
    由 beats 的 func 聚合生成——写任何标签跑一次 build_index 就被"自动登记"，
    AGENTS「不许自造未登记标签」完全空转。现在词表是手维护的，生成物只统计。
    """
    p = ROOT / "vocab" / "elements.yaml"
    if not p.exists():
        err("缺 vocab/elements.yaml（元素受控词表，beats.func 的唯一合法来源）")
        return set()
    try:
        d = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    except Exception as e:
        err(f"vocab/elements.yaml 解析失败：{e}")
        return set()
    ns = set((d.get("namespaces") or {}).keys())
    ids = set()
    for e in d.get("elements") or []:
        if not isinstance(e, dict):
            err(f"vocab/elements.yaml 有条目不是对象：{e!r}")
            continue
        eid = e.get("id")
        if not eid:
            err("vocab/elements.yaml 有条目缺 id")
            continue
        if not re.fullmatch(r"[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*", eid):
            err(f"vocab 元素 id 不合规：{eid}（应为 ns.snake_case）")
        if eid.split(".")[0] not in ns:
            err(f"vocab 元素 {eid} 的命名空间未在 namespaces 里声明")
        for k in ("name", "desc"):
            if not e.get(k):
                err(f"vocab 元素 {eid} 缺 {k}")
        if eid in ids:
            err(f"vocab 元素 id 重复：{eid}")
        ids.add(eid)
    return ids


def main() -> int:
    quiet = "--quiet" in sys.argv
    check_files()
    check_paths()
    creators, cbyid = check_creators()
    works, wbyid = check_works(cbyid)
    check_creator_counts(creators, works)

    elems = load_vocab()

    beats = check_beats(works, elems)
    check_knowledge(wbyid, cbyid)
    check_index()

    if not quiet:
        print(f"扫描：博主 {len(creators)} / 作品 {len(works)} / beats {beats} / 元素 {len(elems)}")
    for w in warns:
        print(f"WARN  {w}")
    for e in errors:
        print(f"ERROR {e}")
    print(f"\n结果：{len(errors)} error / {len(warns)} warn")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
