#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""selftest.py · 校验器自身的回归测试

用法：
    python3 _pipeline/selftest.py          # 跑全部用例
    python3 _pipeline/selftest.py -v       # 显示每步细节

为什么需要它：
    "有检查函数"不等于"检查有效"。2026-10-30 的审查发现，库里有一半规则
    写在 AGENTS 里、检查器却在空转（元素白名单自动合法化、C5 校验器不存在、
    索引只比数字）。这类问题跑一次正常流程是看不出来的——必须**造违法数据，
    看它会不会红**。

    本脚本把当时的 8 个实证用例固化下来。以后改脚本先跑这个，红了就说明
    改坏了某道闸门。

每个用例都在临时副本上做，不碰真库。
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable
VERBOSE = "-v" in sys.argv

results: list[tuple[str, bool, str]] = []


def run(cwd: Path, script: str, *args: str) -> str:
    r = subprocess.run([PY, str(cwd / "_pipeline" / script), *args],
                       capture_output=True, text=True, cwd=str(cwd))
    return (r.stdout or "") + (r.stderr or "")


def fresh() -> Path:
    """复制一份干净库到临时目录（frames 是符号链接，复制链接本身）。"""
    d = Path(tempfile.mkdtemp(prefix="kbtest_")) / "kb"
    shutil.copytree(ROOT, d, symlinks=True,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    return d


def case(name: str, mutate, script: str, *args: str, expect: str) -> None:
    """expect 以 ! 开头 = 反向用例：输出里**不许**出现该模式。

    反向用例是给"宁可漏报也不误报"的规则用的：
    比如真星号「4*」（聊天截图遮罩）不能被当成 markdown 加粗，
    否则人会去改数据，而不是改代码。
    """
    negate = expect.startswith("!")
    pat = expect[1:] if negate else expect
    d = fresh()
    try:
        mutate(d)
        out = run(d, script, *args)
        found = re.search(pat, out) is not None
        hit = (not found) if negate else found
        detail = ""
        if not hit:
            if negate:
                detail = "被误判成违规：" + next(
                    (l for l in out.splitlines() if re.search(pat, l)), "")
            else:
                detail = out.strip().splitlines()[-1] if out.strip() else "（无输出）"
        results.append((name, hit, detail))
    finally:
        shutil.rmtree(d.parent, ignore_errors=True)


def edit_json(p: Path, fn) -> None:
    d = json.loads(p.read_text(encoding="utf-8"))
    fn(d)
    p.write_text(json.dumps(d, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def first_beat(p: Path, fn) -> None:
    lines = p.read_text(encoding="utf-8").splitlines()
    b = json.loads(lines[0])
    fn(b)
    lines[0] = json.dumps(b, ensure_ascii=False)
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ---------- 用例 ----------

def t1_index_tamper(d: Path) -> None:
    """手改 catalog 条目 → 索引比对必须抓到具体字段。"""
    edit_json(d / "catalog" / "works.json", lambda x: x["items"][0].update({"title": "篡改标题"}))


def t2_vocab_escape(d: Path) -> None:
    """自造元素标签，且跑过 build_index（旧版这一步会把非法标签洗白）。"""
    first_beat(d / "works" / "w-0001" / "beats.jsonl",
               lambda b: (b.update({"visual": "测试"}), b.update({"func": ["hook.自造标签"]})))
    subprocess.run([PY, str(d / "_pipeline" / "build_index.py")], capture_output=True)


def t3_status_typo(d: Path) -> None:
    """status 拼错 → 必须报非法值，而不是静默跳过全部状态机。"""
    edit_json(d / "works" / "w-0001" / "profile.json", lambda x: x.update({"status": "done"}))


def t4_count_drift(d: Path) -> None:
    """博主派生计数与磁盘不符 → 必须报。"""
    edit_json(d / "creators" / "c-0001" / "profile.json",
              lambda x: x.update({"works_count": 99}))


def t5_schema_required(d: Path) -> None:
    """删掉 schema 必填字段 → 必须报。"""
    edit_json(d / "works" / "w-0001" / "profile.json",
              lambda x: (x.pop("coverage", None), x.pop("paths", None)))


def t6_maturity_jump(d: Path) -> None:
    """单博主 3 部硬标 pattern → 必须拦住（跨博主才叫模式）。"""
    base = json.loads((d / "works" / "w-0001" / "profile.json").read_text(encoding="utf-8"))
    for n in (2, 3):
        w = dict(base)
        w.update({"id": f"w-000{n}", "title": f"测试{n}", "series_id": f"s-000{n}",
                  "aweme_id": f"70000000000000{n}", "status": "planned",
                  "knowledge_delta": {"added": ["kc-001"]}})
        p = d / "works" / f"w-000{n}"
        p.mkdir(exist_ok=True)
        (p / "profile.json").write_text(json.dumps(w, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    edit_json(d / "works" / "w-0001" / "profile.json",
              lambda x: x.update({"knowledge_delta": {"added": ["kc-001"]}}))
    (d / "knowledge" / "kc-001-test.md").write_text("""---
id: kc-001
type: hook
title: 测试
claim: 测试
maturity: pattern
sample_size: 3
creator_count: 1
confidence: medium
status: active
works: [w-0001, w-0002, w-0003]
evidence:
  - at: t=005s
    quote: x
counterexamples: []
boundary: x
revisions:
  - date: 2026-10-30
    note: init
review_after: 2027-04-30
---
x
""", encoding="utf-8")


def t7_beats_gap(d: Path) -> None:
    """区间断裂（老格式 t1=3 那套）→ 必须报不衔接。"""
    lines = (d / "works" / "w-0001" / "beats.jsonl").read_text(encoding="utf-8").splitlines()
    b = json.loads(lines[1])
    b["t0"] = 9  # c-02 本应 4
    lines[1] = json.dumps(b, ensure_ascii=False)
    (d / "works" / "w-0001" / "beats.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")


def t8_correction_incomplete(d: Path) -> None:
    """定字修订缺 is → c5 必须报三要素不全。"""
    first_beat(d / "works" / "w-0001" / "beats.jsonl",
               lambda b: (b.update({"visual": "测试"}),
                          b.update({"correction": [{"source": "whisper", "was": "你不欺负别人啊"}]})))


def t9_enum_escape(d: Path) -> None:
    """sub_src 写枚举外的值 → 必须报（旧版 validate 只查字段名不查值域）。"""
    first_beat(d / "works" / "w-0001" / "beats.jsonl",
               lambda b: (b.update({"visual": "测试"}), b.update({"sub_src": "ocr"})))


def t10_type_wrong(d: Path) -> None:
    """screen 写成数字 → 必须报类型不合（画面文字是文本，不是长度）。"""
    first_beat(d / "works" / "w-0001" / "beats.jsonl",
               lambda b: (b.update({"visual": "测试"}), b.update({"screen": 123})))


def t11_grid_pattern(d: Path) -> None:
    """grid 少写一位（c-1）→ 必须报 pattern 不符。"""
    first_beat(d / "works" / "w-0001" / "beats.jsonl",
               lambda b: (b.update({"visual": "测试"}), b.update({"grid": "c-1"})))


def t12_md_dirty(d: Path) -> None:
    """字幕带 markdown 加粗 → 必须报。

    这条规则来自真实事故：09 卷正文用 `**加粗**` 排版，backfill 直接搬进 sub，
    全库 567 格字幕变成 `**山茶**` 这种形状，搜「山茶」搜不到。
    同时要确认反例不被误伤——聊天截图里的未读数「4*」是画面事实，不能报错。
    """
    lines = (d / "works" / "w-0001" / "beats.jsonl").read_text(encoding="utf-8").splitlines()
    b = json.loads(lines[0])
    b.update({"visual": "测试画面", "sub": "**山茶** ／ 都怪你"})
    lines[0] = json.dumps(b, ensure_ascii=False)
    (d / "works" / "w-0001" / "beats.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")


def t13_star_not_md(d: Path) -> None:
    """真星号（未读遮罩「4*」）不许被判成 markdown → 期望 validate 不报这条。"""
    lines = (d / "works" / "w-0001" / "beats.jsonl").read_text(encoding="utf-8").splitlines()
    b = json.loads(lines[0])
    b.update({"visual": "花店头像对话，消息「4*」「5*」，多条红色未读标记", "sub": "在吗"})
    lines[0] = json.dumps(b, ensure_ascii=False)
    (d / "works" / "w-0001" / "beats.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")


CASES = [
    ("索引内容篡改", t1_index_tamper, "build_index.py", "--check", "内容不同"),
    ("词表外标签（build 后仍拦）", t2_vocab_escape, "validate.py", "未登记"),
    ("status 拼错", t3_status_typo, "validate.py", "不在值域"),
    ("博主计数漂移", t4_count_drift, "validate.py", "works_count=99"),
    ("schema 必填缺失", t5_schema_required, "validate.py", "schema 必填字段"),
    ("成熟度越级", t6_maturity_jump, "validate.py", "creator_count=1 < 2"),
    ("beats 区间断裂", t7_beats_gap, "validate.py", "不衔接"),
    ("correction 三要素", t8_correction_incomplete, "c5.py", "w-0001", r"correction 缺"),
    ("字段枚举越界", t9_enum_escape, "validate.py", "不在值域"),
    ("字段类型错", t10_type_wrong, "validate.py", "字段类型不合"),
    ("grid 位数不符", t11_grid_pattern, "validate.py", "不符 pattern"),
    ("字幕带 markdown 标记", t12_md_dirty, "validate.py", "含 markdown 标记"),
    ("真星号不误判（反向）", t13_star_not_md, "validate.py", "!含 markdown 标记"),
]


def main() -> int:
    print(f"自测 {len(CASES)} 个用例（每个都在临时副本上跑）\n")
    for name, fn, script, *rest in CASES:
        expect = rest[-1]
        args = rest[:-1]
        case(name, fn, script, *args, expect=expect)
    wid = max(len(n) for n, _, _ in results)
    for name, passed, detail in results:
        print(f"  {'PASS' if passed else 'FAIL'}  {name.ljust(wid)}"
              + ("" if passed else f"  ← 没抓到：{detail}"))
    bad = [r for r in results if not r[1]]
    print(f"\n{len(results) - len(bad)}/{len(results)} 通过")
    if bad:
        print("有闸门失效——这正是这个脚本存在的意义。")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
