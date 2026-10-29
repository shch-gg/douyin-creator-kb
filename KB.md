# KB.md · 读库契约

> AI 与人的检索入口。读完这页你就知道：库里有什么、先读什么、不同问题去哪找、哪些结论不能当事实。
>
> 要往库里加东西？先读 `AGENTS.md`。要知道下一步干什么？跑 `python3 _pipeline/next_task.py`。

---

## 0. 60 秒认知

这是一个**按需求找的抖音创作者知识库**，不是视频链接收藏夹。

- **存储按来源**：`creators/` 存博主，`works/` 存作品，保证证据可回溯到秒；
- **原子是 4 秒**：`beats.jsonl` 一行 = 一格 = 一个动作/一句话，全库地基；
- **检索按需求**：`catalog/index.json` 是紧凑索引，先读它，不读正文；
- **知识按结论**：`knowledge/kc-*.md` 存可复用的单条结论，带样本数、反例、版本；
- **方法分开**：`methods/` 教怎么拆怎么验，不是作品事实。

三条质量承诺：**逐秒可回溯、样本不灌水、结论可被推翻**。底线：**没有证据不写**。

只读三个文件的话：本页 → `MANIFEST.json` → `catalog/index.json`。

---

## 1. 加载顺序

### 任何任务先读

1. `KB.md`（本页）
2. `MANIFEST.json`（版本、计数、能力清单）
3. `catalog/index.json`（紧凑条目，不读正文）

### 按任务追加

| 你要干什么 | 读这些 | 不要这样做 |
|---|---|---|
| 找"这个手法有没有人用过" | `catalog/elements.json` → 关联 work 的 beats | 不要全库 grep 台词 |
| 看某个博主什么路子 | `creators/<id>/index.md` → `fingerprint.md` | 不要先翻他的作品 |
| 对标一部片子 | `works/<id>/assessment.md` → `01`/`07` 卷 | 不要一上来读 09 卷 |
| 查某句台词/某个画面 | `works/<id>/beats.jsonl` 按 `sub`（对白）/`screen`（画面文字）/`visual` 过滤 | 不要读整部 09 卷 |
| 要复刻某个效果 | `knowledge/` 按 `type` 筛 → 证据秒号 | 不要凭印象套模板 |
| 判断一条结论硬不硬 | 卡的 `maturity` / `sample_size` / `creator_count` / `counterexamples` | 不要只看 claim |
| 学怎么拆 | `methods/` → `AGENTS.md` §3 | 不要边拆边发明格式 |
| 改规则/加字段 | `AGENTS.md` → `schemas/` → `_pipeline/validate.py` | 不要只改文档不跑校验 |

### 不要这样读

- 不要按博主名逐个翻 `works/`，先走 `catalog/index.json`；
- 不要因为标题像某类型就归类；
- 不要用 `assessment.md` 的分数代替 beats 证据；
- 不要把 `observation` 级的知识卡当规律引用；
- 不要在 `status != verified` 时引用该作品的结论；
- 不要为了回答一个问题加载整部作品的十卷。

---

## 2. 查询路由

### 2.1 找博主

1. `catalog/creators.json` 按 `tags` / `format` / `avg_duration` / `works_count` 过滤
2. 候选读 `creators/<id>/index.md` 的「定位 / 内容矩阵 / 代表作」
3. 需要判断"他强在哪"读 `matrix.md`
4. 输出必须带：ID、定位一句话、代表作 3 部、样本量（几部作品支撑）

**禁止**：只看粉丝数/点赞量推结论；用 1 部作品代表一个博主。

### 2.2 找作品

1. `catalog/works.json` 按 `creator_id` / `series_id` / `duration` / `tags` / `status` 过滤
2. 读 `works/<id>/assessment.md` 的十维速览
3. 需要细节才开 `01`–`08` 卷
4. 输出带：ID、时长、十维最高/最低维、一句"值得看的地方"

### 2.3 查一个具体秒

1. `works/<id>/beats.jsonl` 按 `t0 <= T <= t1` 找格
2. 该行给 `visual` / `sub` / `speech` / `func`
3. 要更细才开 `dossier/09.md` 对应秒
4. 输出带秒号与拼图格号 `[w-0001#c-03]`

### 2.4 查一条方法/结论

1. `catalog/knowledge.json` 按 `type` / `maturity` / `confidence` / `sample_size` 筛
2. 打开卡读五节：主张 / 证据 / 反例与边界 / 可复用 / 饱和风险
3. **必须同时报**：样本数、博主数、成熟度、反例、复审日期
4. `maturity: observation` 的卡只能说"目前只见于…"，不能说"应该这样做"

**禁止**：把 `n<3` 写成规律；忽略 `narrowed/refuted` 状态；把知识卡当作品事实。

### 2.5 问"这个博主能不能给我抄"

按顺序答：

1. `fingerprint.md` — 能抄的是**手法**（开场句式、字幕板节奏、转场习惯、镜头偏好）
2. `matrix.md` — 他的强维是不是你的弱维
3. 具体到 `beats` — 给 3–5 个可复制的秒级样本
4. 最后给"抄了会怎样"：同质化风险 + 需要改哪一层才不撞

**禁止**：给"风格很像"这种没有秒号支撑的话。

---

## 3. 证据等级

| 级 | 名称 | 形态 | 引用要求 |
|---|---|---|---|
| **E1** | 逐字直引 | 字幕/对白原句 | 秒号 + 说话人；亲读确认 |
| **E2** | 秒级事实 | 画面、动作、景别、切点、指标 | 秒号或 `data/*.json` 字段 |
| **E3** | 综合判断 | 结构功能、情绪设计、作者意图 | `based_on` 秒号 + 置信度 |
| **G** | 跨作品规律 | 知识卡 | `sample_size` + `creator_count` + 反例 |

引用语法：`[w-0001#t=063s]`、`[w-0001#c-16]`、`[c-0003]`、`[kc-004]`、`[hook.question]`

---

## 4. 置信度与措辞

| maturity | 样本 | 允许措辞 |
|---|---|---|
| `observation` | 1–2 部 | 「目前只见于…，样本不足，不能当规律」 |
| `pattern` | ≥3 部且 ≥2 博主 | 「较可能…，基于 N 部样本」 |
| `rule` | ≥6 部且 ≥3 博主 | 「可以确认…（N 部 / M 位博主）」 |
| `law` | ≥15 部、≥5 博主、≥3 题材、实战复现 | 「稳定成立，边界为…」 |

**样本口径**：同一系列 8 集算 1 部；番外/花絮/二创不计；同一素材多平台分发算 1 部。

---

## 5. 检索预算

```text
catalog/index.json（紧凑条目）
  → 1 个入口页（博主 / 作品 / 知识卡）
  → 1–3 个具体页或 beats 查询
  → 需要引用时才开 dossier 卷
```

| 项 | 上限 |
|---|---|
| 页面 | 5 页 / 次 |
| beats 查询 | 3 次 |
| dossier 卷 | 2 卷 |
| 整部作品十卷 | 不加载 |
| 全库扫描 | 禁止 |

**停止条件**：已能回答且证据够 → 停；索引里没有 → 直接说没有；到预算仍不确定 → 说明缺什么，不许继续翻。

---

## 6. 能力清单

见 `MANIFEST.json` 的 `capabilities`。语义摘要：

| 能力 | 能回答 | 入口 | 限制 |
|---|---|---|---|
| `creator.profile` | 这博主什么路子 | `creators/*/index.md` | 1 部作品不下风格结论 |
| `creator.fingerprint` | 他哪几件事每部都做 | `fingerprint.md` | 每条要 ≥2 部支撑 |
| `creator.matrix` | 他强在哪弱在哪 | `matrix.md` | 缺格必须可见 |
| `work.assess` | 这片好在哪 | `assessment.md` | 分数不等于证据 |
| `work.beat` | 第 N 秒发生什么 | `beats.jsonl` | 未 verified 不可引 |
| `work.text` | 全片字幕/画面文字谱 | `dossier/05.md` | 以亲读为准 |
| `work.edit` | 切点与节奏 | `dossier/06.md` | 口径要一起报 |
| `knowledge.query` | 有没有这条规律 | `catalog/knowledge.json` | 必须报成熟度 |
| `element.search` | 这个手法还有谁用 | `catalog/elements.json` | 看变体不看同名 |
| `coverage.check` | 有没有覆盖某维度 | `profile.coverage` | 没有就说没有 |
| `kb.stats` | 库多大 | `MANIFEST.json` | 为 0 就说尚未入库 |

---

## 7. 边界

- 本库不是数据平台：没有播放/完播/涨粉曲线时，不编造传播结论。
- 本库不是全文转录库：只留必要短引 + 秒级事实。
- 本库不是影评：观众评价与作品事实分栏。
- 本库不是一次性项目：结论会随样本变化被收窄或推翻。
- "没有"与"未建"不同：文件不存在 = 还没建，不等于作品里没有。
- **没有证据就不写**：回答"有没有 X"前先查 `coverage` 与 `catalog`。

---

## 8. 回答前自检

- [ ] 我先读了 `catalog/index.json` 吗？
- [ ] 我引的是 `verified` 作品吗？
- [ ] 每个事实有秒号吗？
- [ ] 直引逐字吗？和 `speech` 分开了吗？
- [ ] 这是 E2 事实还是 E3 判断？有没有把判断写成事实？
- [ ] 知识卡的 `maturity` / `sample_size` 够吗？报了吗？
- [ ] 我有没有把标题、话题、评论当剧情？
- [ ] 我有没有用点赞推断内容质量？
- [ ] 我有没有把"候选/待核"说成"已有"？
- [ ] 库缺页时我如实说明了吗？
