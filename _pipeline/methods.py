#!/usr/bin/env python3
"""methods.py —— 把「创作方法论」七维入册成方法层（methods/）。

为什么要入册：
  库里的知识层原先只有 3 张统计卡（kc-001~003），全是从 beats 计数算出来的。
  但那只是「现象」层。真正可照做的东西在 01_最终交付/创作方法论/ 的七篇里——
  52 条手法，每条都挂在具体作品和秒号上。它一直躺在库外，等于没被知识库管起来。

入册不是搬文件：
  1. 每条手法解析成一行结构化记录（编号/名称/做法要点/证据作品/秒号）；
  2. 作品简称映射到 w-id，证据因此能和 beats 连起来查；
  3. 生成 catalog/methods.json，让 build_index / 导览页能直接消费；
  4. 记源文件 sha256，源变了能发现（--check）。

与 kc 的分工：
  methods = 可照做的手法（A 这么做，证据在 w-XXXX t=NNNs）；
  kc-*    = 数据里反复出现的规律（X 条件下 Y 更可能 Z），必须能被推翻。
  方法层不要求可推翻，但要求「有作品真的这么做了」，不接受凭空归纳。

用法：
  python3 _pipeline/methods.py            # 重建 methods/ 与 catalog/methods.json
  python3 _pipeline/methods.py --check    # 只比对，不写盘
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from kbtext import demd  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SRC = Path("/workspace/01_最终交付/创作方法论")
OUT = ROOT / "methods"

# 维度定义：id / 文件名 / 中文名 / 知识库 type 对应
DIMS = [
    ("m-01", "01_选题法.md", "选题法", "structure",
     "拍什么：把社会情绪接进一个能一句话说清的设定"),
    ("m-02", "02_情绪点设计.md", "情绪点设计", "emotion",
     "让谁、在第几秒、为什么动情"),
    ("m-03", "03_人物关系设计.md", "人物关系设计", "character",
     "靠谁和谁的关系当戏剧发动机"),
    ("m-04", "04_不说教_议题与主题表达.md", "不说教（议题与主题表达）", "theme",
     "怎么把道理讲得让人自己想通；先分类，无议题不硬凑"),
    ("m-05", "05_击中感设计.md", "击中感设计", "hook",
     "怎么让观众一看就觉得自己被击中"),
    ("m-06", "06_二次传播设计.md", "二次传播设计", "spread",
     "怎么让评论区自己长出来"),
    ("m-07", "07_作者自述与创作动机.md", "作者自述与创作动机", "author",
     "作者自己怎么说、我们怎么反推（证据层，非手法）", True),
]

# 作品简称 → w-id。方法论文档写于库建立之前，用的是作品简称，
# 这里显式登记别名，不做模糊匹配（"ENEMY 一集"和"ENEMY 第一集"必须都能命中，
# 但"ENEMY"单独出现时不能猜是哪一集）。
ALIAS = {
    "大英一集": "w-0030", "大英第一集": "w-0030",
    "大英二集": "w-0032", "大英第二集": "w-0032",
    "逃出大英博物馆·第一集": "w-0030",
    "逃出大英博物馆·第二集": "w-0032",
    "山河无恙": "w-0031", "山河无恙，家国永安": "w-0031",
    "不锈的我": "w-0020",
    "绵羊少女": "w-0028",
    "百花": "w-0026", "百花阁拾婴案": "w-0026", "百花（百花阁拾婴案）": "w-0026",
    "ENEMY 一集": "w-0015", "ENEMY·第一集": "w-0015", "ENEMY 第一集": "w-0015",
    "ENEMY 第二集": "w-0016", "ENEMY·第二集": "w-0016",
    "ENEMY 杀意消除篇": "w-0012", "杀意消除篇": "w-0012",
    "ENEMY 民国篇": "w-0013", "民国篇": "w-0013",
    "兄弟一百辈子": "w-0033",
    "暴雪南风": "w-0006",
    "丘比特": "w-0002", "再就业吧！丘比特！": "w-0002", "再就业吧丘比特": "w-0002",
    "庄梦迭": "w-0034",
    "让胸部呼吸": "w-0005", "让胸部呼吸：胸部性化": "w-0005",
    "晒月光": "w-0008",
    # 合写型：源文件一句话指多部，映射成多个 id
    "逃出大英博物馆（一/二/三集）": ["w-0030", "w-0031", "w-0032"],
    "逃出大英博物馆·一集": "w-0030",
    "逃出大英博物馆·二集": "w-0032",
    "ENEMY 一/二集": ["w-0015", "w-0016"],
}

# 手法小节标题的四种形态（各篇体例不同，都是实证格式）
HEADS = [
    re.compile(r"^###\s*手法\s*([A-Z]?\d+)\s*[·・]\s*(.+?)\s*$"),
    re.compile(r"^###\s*模式\s*(\d+)\s*[·・]\s*(.+?)\s*$"),
    re.compile(r"^###\s*路径\s*([A-Z])\s*[·・]\s*(.+?)\s*$"),
    re.compile(r"^###\s*类型\s*(\d+)\s*[·・]\s*(.+?)\s*$"),
    re.compile(r"^###\s*(\d+\.\d+)\s+(.+?)\s*$"),          # 07 卷用 2.1 / 2.2
]
NUM_HINT = re.compile(r"(?:^|\n)\s*\*{0,2}要点\*{0,2}\s*[:：]\s*(.+?)(?=\n\s*\n|\n\s*[-*]\s|\Z)", re.S)
SEC_H2 = re.compile(r"^##\s+(.+?)\s*$", re.M)


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def split_sections(text: str):
    """按 ## / ### 切块，返回 [(level, title, body)]。"""
    lines = text.split("\n")
    out: list[tuple[int, str, str]] = []
    cur_lv, cur_ti, buf = 0, "（文首）", []
    for ln in lines:
        m = re.match(r"^(#{2,3})\s+(.+?)\s*$", ln)
        if m:
            out.append((cur_lv, cur_ti, "\n".join(buf).strip()))
            cur_lv, cur_ti, buf = len(m.group(1)), m.group(2), []
        else:
            buf.append(ln)
    out.append((cur_lv, cur_ti, "\n".join(buf).strip()))
    return out


def hit_works(body: str) -> list[str]:
    """正文里出现的作品简称 → w-id（保序去重）。值可以是单 id 或 id 列表。"""
    ids: list[str] = []
    for name, wid in sorted(ALIAS.items(), key=lambda x: -len(x[0])):
        if name not in body:
            continue
        for one in ([wid] if isinstance(wid, str) else wid):
            if one not in ids:
                ids.append(one)
    return ids


def hit_times(body: str) -> list[str]:
    """按出现顺序抽秒号（区间与单点混排）。

    不能"区间优先"——那会把首条证据的单点秒号挤掉，
    出现「做法要点写 055s、秒号列却给 080–087s」的错位。
    """
    out: list[str] = []
    for m in re.finditer(r"(\d{1,4}(?:\.\d+)?)\s*(?:[–\-~]\s*(\d{1,4}(?:\.\d+)?))?\s*s(?![\w])", body):
        v = f"{m.group(1)}–{m.group(2)}s" if m.group(2) else f"{m.group(1)}s"
        if v not in out:
            out.append(v)
        if len(out) >= 3:
            break
    return out


def key_point(body: str, allow_quote: bool = False) -> str:
    """取「要点」句，压成一行。没有要点就取正文首句（去掉项目符号）。"""
    m = NUM_HINT.search(body)
    raw = m.group(1) if m else ""
    if not raw:
        for ln in body.split("\n"):
            s = ln.strip().lstrip("-*").strip()
            # 跳过表格、标题、分隔线、以及 `> 引语`——引语是证据原文，不是"做法"
            if not s or s.startswith(("|", "#", "---", "**来源", "来源")) or "要点" in s:
                continue
            if s.startswith(">"):
                # 07 卷的材料就是「> 作者原话」，对它是内容不是引用
                if not allow_quote:
                    continue
                s = s.lstrip("> ").strip()
                if len(demd(s)) < 12:
                    continue
            if len(demd(s)) < 8:
                continue
            raw = s
            break
    if not raw:
        # 表格型小节（07 卷的「原话 | 出处」表）：取首个数据行的第一格
        for ln in body.split("\n"):
            s = ln.strip()
            if not s.startswith("|") or re.match(r"^\|[\s:|-]+\|$", s):
                continue
            cells = [c.strip() for c in s.strip("|").split("|")]
            if cells and len(demd(cells[0])) >= 8 and "原话" not in cells[0]:
                raw = cells[0]
                break
    s = demd(re.sub(r"\s*\n\s*", " ", raw)).strip()
    s = re.sub(r"^[：:，,。\s]+", "", s)
    return s[:220]


def build_dim(mid: str, fn: str, name: str, typ: str, one_line: str, allow_quote: bool = False):
    p = SRC / fn
    if not p.exists():
        return None, []
    text = p.read_text(encoding="utf-8")
    secs = split_sections(text)

    rows: list[dict] = []
    for lv, title, body in secs:
        if lv != 3:
            continue
        num = nm = None
        for rx in HEADS:
            m = rx.match(f"### {title}")
            if m:
                num, nm = m.group(1), m.group(2)
                break
        if not num:
            continue
        rows.append({
            "no": num,
            "name": re.sub(r"\s*（\s*★[^）]*）|\s*★[^\s）]*", "", nm).strip(),
            "is_new": "★" in nm,
            "key": key_point(body, allow_quote),
            "works": hit_works(body),
            "at": hit_times(body),
        })

    # 该维度的「核心公式 / 核心原则」：取第一个 ## 的正文首段
    core = ""
    for lv, title, body in secs:
        if lv == 2 and ("核心" in title or "原则" in title or "公式" in title):
            core = demd(re.sub(r"\s*\n\s*", " ", body)).strip()[:400]
            break

    dim = {
        "id": mid,
        "type": typ,
        "title": name,
        "one_line": one_line,
        "source": str(p),
        "source_sha256": sha256(p),
        "core": core,
        "methods": rows,
        "works": sorted({w for r in rows for w in r["works"]}),
        "updated": date.today().isoformat(),
    }
    return dim, rows


def render(dim: dict) -> str:
    fm = [
        "---",
        f"id: {dim['id']}",
        "kind: method",
        f"type: {dim['type']}",
        f"title: {dim['title']}",
        f"one_line: {dim['one_line']}",
        f"source: {dim['source']}",
        f"source_sha256: {dim['source_sha256']}",
        f"methods_count: {len(dim['methods'])}",
        f"works: [{', '.join(dim['works'])}]",
        f"updated: {dim['updated']}",
        "---",
        "",
        f"# {dim['title']}",
        "",
        f"> {dim['one_line']}",
        ">",
        f"> 源：`{dim['source']}`（sha256 `{dim['source_sha256'][:12]}`）。本页由 `_pipeline/methods.py` 生成，"
        "改内容改源文件后重跑，不要手改。",
        "",
    ]
    if dim["core"]:
        fm += ["## 核心公式／原则（源文件原文）", "", f"> {dim['core']}", ""]
    if dim["id"] == "m-07":
        # 07 卷不是手法库，是「作者怎么说」的材料汇编：
        # 2.x 是本人第一方材料，3.x 是其他作者的检索结果。分表，别混成"手法"。
        own = [r for r in dim["methods"] if r["no"].startswith("2.")]
        oth = [r for r in dim["methods"] if not r["no"].startswith("2.")]
        for title, rows, note in (
            ("作者本人材料（第一方）", own,
             "标「★」的是最能回答「创作动机」的条目。引用时必须带出处，无出处的当推断。"),
            ("其他作者（检索结果）", oth,
             "有就是有、没有就是没有。这一节的作用是标出**哪里还是空的**，不要让推断冒充作者原话。"),
        ):
            if not rows:
                continue
            fm += [f"## {title}", "", f"> {note}", "",
                   "| # | 条目 | 内容摘要 | 相关作品 |", "|---|---|---|---|"]
            for r in rows:
                nm = r["name"] + (" ★" if r["is_new"] else "")
                ws = "、".join(r["works"]) or "—"
                fm.append(f"| {r['no']} | {nm} | {r['key'] or '—'} | {ws} |")
            fm.append("")
    else:
        fm += [
            "## 手法清单",
            "",
            "| # | 手法 | 做法要点 | 证据作品 | 秒号 |",
            "|---|---|---|---|---|",
        ]
        for r in dim["methods"]:
            nm = r["name"] + (" ★新" if r["is_new"] else "")
            ws = "、".join(r["works"]) or "—"
            at = "、".join(r["at"]) or "—"
            fm.append(f"| {r['no']} | {nm} | {r['key'] or '—'} | {ws} | {at} |")
    fm += ["", "## 用法", "",
           "- 要做这个维度的事，先按表里的「做法要点」执行，再回 `works/<w-id>/beats.jsonl` 核对证据秒号。",
           "- 「证据作品」为空的行＝源文件只给了原则没给片例，属于**弱证据条目**，引用时要说明这一点。",
           "- 本层不判断对错，只登记「有人这么做过，且效果在片子里看得见」。",
           ""]
    return "\n".join(fm)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()

    OUT.mkdir(exist_ok=True)
    items, wrote, stale = [], 0, []
    for spec in DIMS:
        mid, fn, name, typ, one = spec[:5]
        allow_quote = bool(spec[5]) if len(spec) > 5 else False
        dim, rows = build_dim(mid, fn, name, typ, one, allow_quote)
        if not dim:
            print(f"MISS 源文件不存在：{fn}")
            continue
        out = OUT / f"{mid}-{fn.split('_', 1)[1].replace('.md', '')}.md"
        md = render(dim)
        old = out.read_text(encoding="utf-8") if out.exists() else None
        if a.check:
            if old != md:
                stale.append(out.name)
        else:
            if old != md:
                out.write_text(md, encoding="utf-8")
                wrote += 1
        items.append({
            "id": mid, "type": typ, "kind": "method", "title": name,
            "one_line": one,
            "methods_count": len(dim["methods"]),
            "works": dim["works"],
            "source": dim["source"],
            "source_sha256": dim["source_sha256"],
            "path": f"methods/{out.name}",
        })

    cat = {
        "schema": "../schemas/kb.schema.json#/definitions/method_dim",
        "updated": date.today().isoformat(),
        "count": len(items),
        "methods_total": sum(i["methods_count"] for i in items),
        "items": items,
    }
    cp = ROOT / "catalog" / "methods.json"
    newcat = json.dumps(cat, ensure_ascii=False, indent=1) + "\n"
    oldcat = cp.read_text(encoding="utf-8") if cp.exists() else None
    if a.check:
        if oldcat != newcat:
            stale.append("catalog/methods.json")
        print(("索引不一致：" + "、".join(stale)) if stale else "OK 方法层与源文件一致")
        return 1 if stale else 0
    if oldcat != newcat:
        cp.write_text(newcat, encoding="utf-8")

    print(f"OK 方法层：{len(items)} 维 / {cat['methods_total']} 条手法 / 写出 {wrote} 个文件")
    for i in items:
        print(f"  {i['id']} {i['title']:22} {i['methods_count']:2} 条  证据作品 {len(i['works'])} 部")
    weak = [f"{i['id']}-{r['no']}" for i, d in
            [(i, None) for i in items] for r in []]
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
