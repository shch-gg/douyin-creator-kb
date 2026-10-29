---
# 知识卡模板。复制成 kc-NNN-<英文slug>.md 后逐项填写。
# 填写顺序：先写 claim（一句话、可被推翻），再找证据，最后找反例。
# 缺 evidence / counterexamples / boundary / revisions 中任一项，validate 会给 WARN 或 ERROR。
id: kc-NNN
type: hook            # hook|structure|character|visual|performance|sound|text|edit|emotion|spread|series
title: ""
claim: ""             # 一句话，必须"X 条件下 Y 更可能 Z"，不能是口号
maturity: observation # observation|pattern|rule|law（不许跳级）
sample_size: 1        # 独立作品数，系列只算 1
creator_count: 1
confidence: low       # low|medium|high
version: 0.1
status: active        # active|narrowed|refuted|superseded
works: []             # [w-0001]
coverage: partial     # full_work|partial
evidence: []          # - {work: w-0001, at: "t=000–003s", note: "…"}
counterexamples: []   # - {work: w-0009, at: "t=000–004s", note: "…"}
boundary: ""          # 时长/题材/人群三层边界
revisions:
  - {date: "YYYY-MM-DD", version: 0.1, change: "新增", trigger: "w-0001", evidence: "t=000–003s"}
refuted_by: []
narrowed_to: null
superseded_by: null
review_after: ""      # YYYY-MM-DD（内容类 180 天，平台类 90 天）
updated: ""
---

# <标题>

## 主张

（把 claim 展开成 2–4 句。说清"在什么条件下、什么机制、导致什么"。）

## 证据

| 作品 | 秒号 | 具体表现 |
|---|---|---|
| — | — | — |

## 反例与边界

- 反例：
- 边界（时长 / 题材 / 人群）：
- 未覆盖：

## 可复用方式

（写成能直接照做的动作，不写"注意节奏"这类空话。）

## 饱和风险

（这招被用烂了吗？在哪个赛道已饱和？替代是什么？）
