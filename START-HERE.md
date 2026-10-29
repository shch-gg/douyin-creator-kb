# START-HERE.md · 接手工作台

> 给"下一只手"的一页纸：新会话、新 AI、三个月后的你自己。
> 读完这页 + 跑一条命令，就知道**该做什么、改哪些文件、什么时候算做完**。
>
> 只想查东西？→ `KB.md`。想改规则？→ `AGENTS.md`。想看流程？→ `FLOW.md`。

---

## 1. 先跑这一条（10 秒）

```bash
cd /workspace/抖音博主知识库 && python3 _pipeline/next_task.py
```

它会按优先级打印：投料待建档 → 作品推进 → 知识层 → 博主层，每条带"为什么"。

**不要靠猜状态。** 三处一旦不同步（`profile.json` 的 `coverage`、`beats.jsonl` 的实际行数、`catalog` 的计数），以 `validate.py` 的输出为准，先修一致性再往下做。

```bash
python3 _pipeline/validate.py        # 0 error 才算干净
python3 _pipeline/build_index.py     # 每次改完必须重建
```

---

## 2. 四种任务，四个门（进错门是最常见的时间浪费）

| 你要做的事 | 从这里进 | 不要从这里进 |
|---|---|---|
| 查素材 / 回答"有没有 X" | `KB.md` → `catalog/index.json` | 不要一本一本翻 `works/` |
| 想知道某条结论硬不硬 | `catalog/knowledge.json` 看 `maturity` | 不要凭印象说"我看过很多都这样" |
| **用户丢来一条链接 / 一个视频** | 本页 §3 的投料流程 | 不要直接开始抽帧 |
| **用户丢来一个博主主页** | `methods/20-博主收编.md` | 不要一部一部手动来 |
| 改结构 / 加字段 / 改校验 | `AGENTS.md` → `schemas/` → `validate.py` | 不要只改页面就完事 |

---

## 3. 投料流程（最常发生的事）

```text
用户给链接
   ↓
① 贴进 _inbox/urls.txt（一行一条，可批量）
   ↓
② python3 _pipeline/next_task.py   ← 列出待建档
   ↓
③ 解析 aweme_id → 查重（works/index.jsonl / catalog/works.json）
   ↓
④ 分配 w-NNNN，建 works/w-NNNN/，写 profile.json（status=planned）
   ↓
⑤ 下载原片 → 记 sha256 → status=ingested
   ↓
⑥ 跑前处理（抽帧/拼图/音频/Whisper/OCR/切点/黑场/曲线）→ status=prepped
   ↓
⑦ 逐格精读 → beats.jsonl + dossier/09 → status=read
   ↓
⑧ 十维卷 + assessment → status=decomposed
   ↓
⑨ C5 → 0 error → 上卷（博主三页）→ knowledge_delta → build_index → validate → status=verified
```

**卡在哪一步，就重跑 `next_task.py`，它会告诉你。** 不要凭记忆接着做。

---

## 4. 单部作品的最小闭环（9 步，每步有完成标志）

| # | 动作 | 落在哪 | 完成标志 |
|---|---|---|---|
| 1 | 查重、分配 ID | `works/w-NNNN/` | 无重复；ID 未复用 |
| 2 | 下载原片、记哈希 | `profile.json.source` | sha256 有值；元信息缺项为 null |
| 3 | 前处理 | `data/*.json`、`frames/`、`contact/` | 帧数=⌈时长⌉；拼图覆盖全帧 |
| 4 | 逐格精读 | `beats.jsonl` | 行数=拼图数；秒号无缝；字幕亲读 |
| 5 | 十维拆解 | `dossier/01–08、10` | 每条结论有秒号 |
| 6 | 评估 | `assessment.md` | 十维分齐全，每分有证据 |
| 7 | C5 自校验 | `reports/c5-w-NNNN.md` | 0 error；WARN 逐条说明 |
| 8 | 上卷 | `creators/*/fingerprint|matrix|trajectory` | 指纹每条 ≥2 部支撑 |
| 9 | 知识 + 索引 | `knowledge/*`、`catalog/*` | validate 0 error；`knowledge_delta` 已写 |

**"verified"的定义**：beats 全覆盖 + 十维齐全 + C5 0 error + 结尾已看 + 知识增量已落 + 索引已重建。缺一条只能是 `decomposed`。

---

## 5. 这个库到底拆什么（内容边界）

- **允许入库**：秒级事实、必要短引（逐字）、十维结论、跨作品规律、覆盖声明
- **不允许入库**：原片、完整逐字稿、他人解说全文、平台简介当剧情、评论当事实
- **没有的维度写"无"**，不许用类型常识补
- **每部作品必须留知识增量**：新增/修订/推翻/收窄哪张卡，或写 `none_reason`。只堆档案不产知识，算没交付

---

## 6. 八个最容易走错的地方（都是真踩过的）

1. **字幕拿 Whisper 当真相**。第三集 63s 音频听成「你不欺负别人啊」，画面亲读是「怎么他妈就欺负你」——**永远以画面为准**。
2. **帧号当秒号**。`f_0095` 是第 95 帧 = **94 秒**，不是 95 秒。差一秒，全卷引用全错。
3. **同系列 N 集算 N 个样本**。8 集连续剧只算 1 部，否则知识卡样本瞬间虚高 8 倍。
4. **只加样本不复查旧结论**。新片进来必须跑"受影响卡"清单，无影响也要留 `no_change` 记录。
5. **改了页面不重建索引**。索引过期比没有索引更危险——下一个 AI 会读到旧结论。
6. **标了 verified 但 coverage 没落账**。真实事故：B 站某作品标了 verified，`dims_done` 还是 0，机器筛"十维齐全"时静默漏掉。
7. **把点赞当质量证据**。「421 万赞所以节奏好」是伪因果，平台数据只能单列。
8. **中文路径**。`江问渔/我的婚礼 你的葬礼` 已被空格拆成两个目录，成了坏账。全库路径只准 `[a-z0-9-_/]`。

---

## 7. 交接清单（复制到任务里）

```text
任务：入库 <链接 / 博主主页>
第一步：python3 _pipeline/next_task.py，按输出做，不要跳步
规则：AGENTS.md（十条硬规则）、FLOW.md（九闸门）、methods/（SOP）
禁令：不跳秒；不拿 Whisper 当真相；不灌样本；不用点赞推质量；未跑 validate 不得标 verified
交付：beats.jsonl + 十维卷 + assessment + C5 0 error + 上卷 + knowledge_delta + validate 0 error
```

---

## 8. 开工前先看"人的记忆"

> 知识库记"片子里有什么"，会话记忆记"我们说过什么、定了什么"。两者分开，别混。
> `_会话记忆/` **不参与 validate、不进 catalog、不算证据**。

| 项 | 路径 |
|---|---|
| 目录 | `_会话记忆/`（库内、隔离） |
| 先读 | `project/project-tiktok-kb.md`（长期状态）→ `decisions.md` → `open-questions.md` → 最近一篇 `sessions/` |
| 检索 | `python3 _会话记忆/search.py 关键词`（可选） |
| 收工必写 | 新增一篇 session + 在 `index.md` 加一行（行与文件一一对应）；用户拍板了写进 `decisions.md` |

**顺序**：先看人（约定与进度）→ 再跑 `next_task.py` 看库 → 最后才读片子。

---

## 9. 当前状态（自动生成，不要手改）

> 改这里等于改 `creators/*/profile.json`、`works/*/profile.json`、`knowledge/*.md`；
> 然后跑 `python3 _pipeline/build_index.py`。`validate.py` 会检查这块是否过期。

<!-- STATUS:BEGIN -->
| 项 | 值 |
|---|---|
| 库版本 | 0.1.0 |
| 博主 | 10 |
| 作品 | 37（verified 0） |
| 片段 beats | 3903 / 3957 已登记 |
| 知识卡 | 3（观察 2 / 模式 0 / 规律 1 / 定律 0） |
| 元素标签 | 已用 0 / 词表 27 |
| 最近重建 | 2026-10-29T19:18:52Z |
<!-- STATUS:END -->

---

## 10. 相关文件（按需加载，不要一次全读）

| 文件 | 什么时候读 |
|---|---|
| `_pipeline/next_task.py` | 每次开工先跑 |
| `_pipeline/validate.py` | 每次改完 |
| `FLOW.md` | 忘了流程 / 要给别人讲这个库怎么运转 |
| `methods/10-入库SOP.md` | 第一次投料 |
| `methods/20-博主收编.md` | 用户给的是博主主页而不是单条 |
| `methods/30-知识提炼.md` | 要写或改知识卡 |
| `AGENTS.md` §5 | 改知识卡字段 |
| `schemas/kb.schema.json` | 加字段 |
