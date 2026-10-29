# AGENTS.md · 写库契约

> 给**要往库里加博主 / 加作品 / 改规则**的 AI 与人的操作手册。
> 想查东西去 `KB.md`；想知道下一步干什么去 `START-HERE.md`；想看流程图去 `FLOW.md`。
>
> 版本 0.1.0 ｜ 更新 2026-10-30

---

## 0. 你是谁

你不是"写观后感的"，你是这个库的**编译者与守门人**：

- 把一条抖音视频拆成**可逐秒回溯的事实**；
- 在事实上做**十维聚合**，再在聚合上做**跨作品提炼**；
- 每条结论都能回到某一秒；
- 每加一个样本，都要回头检查它是否动摇了旧结论。

服务对象：做 AI 短剧 / 短视频的自己与协作者。**覆盖率、可回溯性、可复用性 > 文采。**

---

## 1. 十条硬规则

1. **不跳秒。** 每一秒都要有登记；无内容的秒写"空镜/过渡"，不许留白跳过。拼图 `c_NN` 必须连续覆盖全片。
2. **事实带秒号。** 画面、动作、台词、切点、指标，都必须能指到 `[w-NNNN#t=NNNs]`；综合判断必须列 `based_on`。
3. **字幕逐字。** 对白与画面文字以**亲读画面为准**；Whisper / OCR 只作交叉验证，冲突时一律以放大亲读定字，并记 `correction` 说明谁错了、错在哪。
4. **平台数据不是内容事实。** 点赞、播放、发布时间、话题标签单列 `platform` 字段；不得用它们推断内容质量（"点赞高所以节奏好"是伪因果）。
5. **简介不是正文。** 标题、话题、博主简介、评论只能作"外部资料"，不得当剧情事实。
6. **别名归一。** 同一人物/同一博主只用一个 ID；改名、马甲、系列别名登记在 `aliases`。
7. **关系/弧光要有触发。** "初始 → 触发事件 → 变化结果"，仅同场出现不算关系升级。
8. **先看结尾再下全局结论。** `ending_checked=false` 时禁止写结构结论、作者意图、知识卡升版。
9. **样本不灌水。** `sample_size` 按**独立作品**计：同一系列 N 集只算 1 部；番外、花絮、二创不计入；同一素材多平台分发只算 1 部。
10. **同步六处。** 每次入库必须同时落这六处：① `catalog/*.json` ② `MANIFEST.json` ③ `START-HERE.md` 状态块（三者由 `build_index.py` 生成）④ `creators/<id>/profile.json` 的派生计数（`build_index.py --sync-creators`）⑤ `profile.coverage` 的 C5 结果（`c5.py` 回写）⑥ `_会话记忆/sessions/`。生成物手改无效——`validate.py` 会拿 catalog 与源文件**逐字段**比对，改一个标题都会被抓出来。

**底线**：回答"有没有 X"前先查 `coverage`；没有就写"没有 / 只提及"，**不许用类型常识补写**。

---

## 2. ID 与路径

| 对象 | 规则 | 示例 |
|---|---|---|
| 博主 | `c-0001`，四位递增，永不复用 | `creators/c-0001/` |
| 作品 | `w-0001` | `works/w-0001/` |
| 系列 | `s-0001` | 写在 `works/w-0001/series.json` 或 `creators/*/series/` |
| 片段格 | `c-NN`（4 秒一格，行内唯一） | `[w-0001#c-03]` |
| 秒号 | `t=NNNs` / 区间 `t=012–016s` | `[w-0001#t=012–016s]` |
| 人物 | `p-0001`（作品内唯一） | `[w-0001#p-0001]` |
| 知识卡 | `kc-001` | `knowledge/kc-001-*.md` |
| 元素 | 命名空间 + 短横线 | `[hook.question]` `[turn.reveal]` |

**为什么全英文 ID**：标题会改、会重名、含 emoji 和空格（实测 `江问渔/我的婚礼 你的葬礼` 已被空格拆成两个目录，成了坏账）。ID 一旦分配不改，中文只进 `title` 字段。

**路径纪律**：**ID 层必须 ASCII**（`creators/` `works/` `knowledge/` `catalog/` 下的目录名与文件名只准 `[a-z0-9._-]`）；**文档层允许中文**（`methods/` `reports/` 等），但全库禁止空格。中文标题一律进 `title` 字段。

```text
抖音博主知识库/
├── KB.md                    ← 读库契约（AI 入口）
├── AGENTS.md                ← 写库契约（本文件）
├── START-HERE.md            ← 接手工作台（先跑 next_task）
├── FLOW.md                  ← 全流程图
├── MANIFEST.json            ← 版本、计数、能力清单（脚本生成）
├── creators/<c-id>/         ← 博主层
│   ├── profile.json
│   ├── index.md             ← 账号画像
│   ├── fingerprint.md       ← 作者指纹（跨作品稳定手法）
│   ├── matrix.md            ← 十维 × 作品 能力矩阵
│   ├── trajectory.md        ← 生长轨迹（按发布时间）
│   └── series/<s-id>.md     ← 系列引擎
├── works/<w-id>/            ← 作品层
│   ├── profile.json
│   ├── assessment.md        ← 十维评估
│   ├── beats.jsonl          ← 逐格事实（L3 地基）
│   ├── dossier/             ← 十一卷产物（00–10 + srt）
│   ├── data/                ← 量化数据（四曲线/切点/OCR/Whisper）
│   └── media/               ← 不存原片，只存指针与哈希
├── knowledge/kc-*.md        ← 知识卡（跨作品结论）
├── vocab/elements.yaml      ← 元素受控词表（手维护，beats.func 的唯一合法来源）
├── catalog/                 ← 机读索引（脚本生成，禁手改）
│   ├── index.json
│   ├── creators.json
│   ├── works.json
│   ├── knowledge.json
│   └── elements.json
├── methods/                 ← 怎么做（SOP / 校验说明）
├── reports/                 ← C5 报告 / 复审记录 / 实战反馈
├── _inbox/                  ← 投料区（urls.txt / 视频文件 / 截图）
├── _pipeline/               ← 脚本
└── _会话记忆/               ← 过程记忆（隔离：不校验、不计数、不当证据）
```

---

## 3. 对象模型

### 3.1 L1 博主 `creators/c-NNNN/`

博主不是"作者简介"，是**可复用的生产参数集**。四个页各有硬指标：

| 页 | 必须回答 | 判据 |
|---|---|---|
| `index.md` 账号画像 | 他是谁、做什么内容、给谁看、凭什么被记住 | 定位一句话 + 内容矩阵 + 更新节奏 + 代表作 3 部 |
| `fingerprint.md` 作者指纹 | 换一部片子，哪些东西**不变** | 每条指纹 ≥2 部作品支撑，写明"变体" |
| `matrix.md` 能力矩阵 | 十维 × 每部作品的强弱 | 每格有分数或"未评"，空缺必须说明 |
| `trajectory.md` 生长轨迹 | 从早期到近期，什么在变好/变差 | 按发布时间排序，标出转折作品 |

**指纹的最小可信度**：单部作品只能写「单部观察」，不得称"风格"。≥2 部可写「倾向」，≥4 部可写「稳定手法」。

### 3.2 L2 作品 `works/w-NNNN/`

`profile.json` 是机器读的唯一真相，字段定义见 `schemas/kb.schema.json` 的 `definitions.work`。关键字段：

```jsonc
{
  "id": "w-0001",
  "creator_id": "c-0001",
  "series_id": null,          // 系列作品必填；sample_size 按系列去重靠它
  "title": "…",               // 中文只在这里
  "aweme_id": "7424…",        // 查重主键
  "duration_ms": 215340,
  "published_at": "2026-08-12T10:46:55Z",
  "platform": {               // 平台数据单列，禁止混进内容结论
    "digg": 421609, "comment": 7607, "share": 93546, "collect": 28241,
    "play": null,             // 抓不到就 null，不许估
    "hashtags": ["#剧情"], "music": null
  },
  "source": {                 // 原片不入库，只留指针 + 哈希
    "type": "pointer", "path": "…", "sha256": "…", "bytes": 22629335
  },
  "spec": { "w": 1280, "h": 720, "fps": 30, "frames": 6460 },
  "status": "verified",       // planned | ingested | prepped | backfilled | read | decomposed | verified
  "coverage": {
    "beats_total": 54, "beats_registered": 54,
    "dims_total": 10, "dims_done": 10,
    "c5_errors": 0, "c5_warns": 1,
    "ending_checked": true
  },
  "assessment": { "hook": 8, "structure": 7, "…": 0 },  // 十维 0–10
  "knowledge_delta": {        // 这部片子让知识层动了什么
    "added": ["kc-012"], "revised": [], "refuted": [], "none_reason": ""
  }
}
```

**状态推进条件**（不许跳级）：

| 状态 | 进入条件 |
|---|---|
| `planned` | 已分配 ID，未拿到原片 |
| `ingested` | 原片落盘 + sha256 + 元信息完整（缺项已记 null） |
| `prepped` | 抽帧/拼图/音频/Whisper/OCR/切点/黑场/曲线全部产出 |
| `backfilled` | **旁路**：beats 由既有 11 卷档案（09 卷 c_NN 块）解析而来，库内闸门 2 未重跑。`note` 必须写明原始档案路径，`coverage.beats_registered` 必须等于 `beats_total`（解析不出的格要写进 `gaps`） |
| `read` | `beats.jsonl` 覆盖 100% 格，09 卷登记完成（本库亲自亲读，非解析） |
| `decomposed` | 十维卷 + 05 卷 + srt + 评估全部产出 |
| `verified` | C5 0 error、索引已重建、`knowledge_delta` 已写、上卷已重算 |

> `backfilled` 的存在理由是诚实：36 部旧档案已经在别处拆完 11 卷，重拆一遍是浪费，但把它们直接标 `decomposed` 又是谎报（本库没有它们的 frames/contact/ocr）。所以单开一个状态，让「beats 可用、闸门没过」这件事在数据里可见。

**`backfilled` 是合法终态**（Q-011 定论）。它**不能**直接升 `verified`：要走
`backfilled → read`（需九卷进库）→ `decomposed`（需十维全填）。两条都不满足就停在 `backfilled`，
**不许为了让状态好看而跳级**。05 卷画面文字已由 `text05.py` 回填（不再是把柄），剩下的是十维。

### 3.3 L3 片段 `beats.jsonl`

一行一个 4 秒格（与拼图 `c_NN` 一一对应）。这是全库地基。

```jsonc
{"wid":"w-0001","grid":"c-03","t0":8,"t1":12,"shot":"中景","move":"固定",
 "visual":"许颂低头站在教室后门，暖光从右侧窗打入",
 "sub":"我讨厌童枳","sub_src":"05","screen":"第二印象／第三印象",
 "speech":[{"who":"p-0001","text":"我讨厌童枳","t":9}],
 "sound":"环境声＋钢琴单音","func":["hook.character"],"note":"首句台词落在第 9 秒"}
```

字段纪律：

- `t0/t1` 是**连续区间** `[t0, t1)`，按 `4×(N−1)` 到 `4×N` 取，末格 `t1` 截到片长。
  c-01=[0,4) c-02=[4,8) … c-54=[212,215.34)。相邻格必须首尾相接，**不留空洞**。
  （2026-10-30 修正：此前前格写"秒点"`t1=3`、末格写片长，同一字段两种含义，且 3–4 秒无人覆盖。）
- **`sub` 与 `screen` 必须分列**（2026-10-30 起）：
  - `sub` = **对白字幕**，人物说话时打出来的字；无字幕写 `null`
  - `screen` = **画面文字**，系统 UI／片名卡／署名卡／招牌／道具字／常驻免责声明
  混在一起的后果不是不精确，是**结论会错**：ENEMY 前五部零对白，05 卷表里 8 条全是系统红字，
  混进 `sub` 就被判成"有台词"，`kc-002`（系列中途换对白形态）直接塌。
- `sub_src` 标来源卷：`05`=05 卷权威表重建，`09`=09 卷行文解析，`null`=未登记。
  看到 `09` 要意识到它可能是下界（09 卷只记了亲读时注意到的字幕）。
- `speech` 与 `sub` 也分开：`sub` 是屏幕上的字，`speech` 是听到的话，两者经常不一致（第三集 63s「怎么他妈就欺负你」vs 音频无「他妈」）
- `speech[].t` 必须落在本格 `[t0, t1]` 内，否则算登记错格
- `func` 只能取 `vocab/elements.yaml` 里已登记的标签；**词表是手维护的，`build_index` 只统计不授权**——写个新标签跑一次构建就在 `catalog/elements.json` 的 `unregistered` 里露出来，validate 直接报 ERROR
- 不确定的字段写 `null` + `note` 说明，**不许猜**

---

## 4. 证据与引用

### 4.1 四级证据

| 级 | 名称 | 形态 | 要求 |
|---|---|---|---|
| **E1** | 逐字直引 | 字幕/对白原句 + 秒号 + 说话人 | 必须亲读确认；`verified: true`；不得改写、不得补标点 |
| **E2** | 秒级事实 | 画面、动作、景别、切点、时长、指标 | 能在 `beats.jsonl` 或 `data/*.json` 找到 |
| **E3** | 综合判断 | 结构功能、情绪设计、作者意图 | 必须列 `based_on` 秒号 + `confidence` |
| **G** | 跨作品规律 | 知识卡结论 | 必须给 `sample_size` / `creator_count` / 反例 / 边界 |

任何页面上的事实都要能回答：**哪一秒？画面上是什么？**

### 4.2 引用语法

| 对象 | 格式 | 示例 |
|---|---|---|
| 作品 | `[w-NNNN]` | `[w-0001]` |
| 作品某秒 | `[w-NNNN#t=NNNs]` | `[w-0007#t=063s]` |
| 秒区间 | `[w-NNNN#t=NN–NNs]` | `[w-0007#t=062–069s]` |
| 片段格 | `[w-NNNN#c-NN]` | `[w-0007#c-16]` |
| 人物 | `[w-NNNN#p-NNNN]` | `[w-0007#p-0001]` |
| 博主 | `[c-NNNN]` | `[c-0003]` |
| 系列 | `[s-NNNN]` | `[s-0002]` |
| 知识卡 | `[kc-NNN]` | `[kc-004]` |
| 元素 | `[ns.name]` | `[hook.question]` |

### 4.3 引用纪律

- 直引加引号，转述不加；二者不得混在一句里
- 秒号必须精确到实际出现的那一秒，不许"大概在 60 多秒"
- 结论涉及多段时列 `based_on: ["w-0001#t=012–016s", "w-0001#t=180–186s"]`
- 没有证据的句子删掉，或标 `【待核】` 并进 `_会话记忆/open-questions.md`

---

## 5. 知识卡规范

`knowledge/kc-NNN-<slug>.md`，frontmatter 必须完整：

```yaml
---
id: kc-004
type: hook            # hook | structure | character | visual | sound | text | edit | emotion | spread | series
title: 前 3 秒用"结论前置"句式比"悬念提问"完播更高
claim: 一句话主张，必须可被反例推翻
maturity: pattern     # observation | pattern | rule | law
sample_size: 7        # 独立作品数（系列只算 1）
creator_count: 3
confidence: medium    # low | medium | high
version: 0.3
status: active        # active | narrowed | refuted | superseded
works: [w-0001, w-0003, w-0007]
coverage: partial     # full_work | partial
evidence:
  - {work: w-0001, at: "t=000–003s", note: "开门见山报结论"}
counterexamples:
  - {work: w-0009, at: "t=000–004s", note: "同句式但完播低，因人群不匹配"}
boundary: "仅适用于 15–60s 单条，不适用于连续剧集"
revisions:
  - {date: 2026-10-30, version: 0.1, change: 新增, trigger: w-0001, evidence: "t=000–003s"}
refuted_by: []
narrowed_to: null
superseded_by: null
review_after: 2027-04-30
---
```

正文五节，缺一节不算完成：

1. **主张** — 用可验证的语言，不用"更好看""更抓人"
2. **证据** — 表格：作品 / 秒号 / 具体表现
3. **反例与边界** — 至少写一条反例；没有反例要写清"为什么找不到"
4. **可复用方式** — 怎么用到自己片子里，给可执行动作
5. **饱和风险** — 这个手法被用烂了吗，同质化在哪

**配额**：每 10 部作品产 3–6 张卡。少于 3 张说明没提炼；多于 6 张说明在凑数（同一机制拆成多张）。

**孤儿卡禁止**：每张卡必须被至少一个 `work.profile.knowledge_delta` 或 `creator.profile` 引用。没人认领的卡 = 没触发它的样本 = 造假。

---

## 6. 跨作品更新义务

每完成一部作品，必须检查并更新：

| 层 | 动作 | 不做的后果 |
|---|---|---|
| 博主 `fingerprint.md` | 新样本是否支持/改变已有指纹 | 指纹停在第一部的印象 |
| 博主 `matrix.md` | 补这一部的十维分 | 能力矩阵缺格，无法横向比 |
| 博主 `trajectory.md` | 按发布时间插进去，标转折 | 看不出成长，作者页变成静态简介 |
| 系列（如有） | 系列引擎卡的 `sample_size` 仍算 1，但写"第 N 集已验证" | 系列被当独立样本灌水 |
| 知识层 | 跑受影响卡清单，逐张判断 | 库存了 50 部但结论还停在 3 部 |

---

## 7. 版本、日志、事件

- `MANIFEST.json`：版本号、计数、能力清单。**脚本生成**
- `catalog/*.json`：机读索引。**脚本生成**
- `START-HERE.md` 状态块：**脚本生成**
- `_会话记忆/sessions/YYYY-MM-DD-<slug>.md`：一次会话一篇，`index.md` 加一行，一行对应一篇
- `_会话记忆/decisions.md`：用户拍板的规则（比如"字幕以亲读为准"）
- `_会话记忆/open-questions.md`：待核项，解决了划掉不删

版本语义：`0.x` = 结构可能变；`1.0` = 接口冻结（路径、ID、引用格式不再变）。**改结构的同一次操作里必须改版本号**。

---

## 8. 交付验收清单

一部作品标 `verified` 前逐项打勾：

- [ ] `aweme_id` 查重通过，`w-NNNN` 未复用
- [ ] 原片 sha256 记录；平台字段缺项为 `null` 不是猜值
- [ ] 帧数 = ⌈时长⌉；拼图覆盖全部帧；末格不满 4 秒已按实际写 `t1`
- [ ] `beats.jsonl` 行数 = 拼图数；每行 `t0/t1` 连续无缝
- [ ] 每格 `visual` 非空；`sub` 为亲读结果，与 `speech` 分列
- [ ] 十维卷齐全；每条结论有秒号
- [ ] 05 卷 + srt 与 09 卷可双向回溯（C5 F2/F5）
- [ ] C5 五条 0 error，WARN 逐条说明
- [ ] 十维分齐全（0–10），每分有证据
- [ ] `ending_checked: true`（看完全片才能下结构结论）
- [ ] `knowledge_delta` 已写：新增/修订/推翻哪些卡，或 `none_reason`
- [ ] 博主三页已重算（fingerprint / matrix / trajectory）
- [ ] `build_index.py` + `validate.py` 跑过，0 error
- [ ] `selftest.py` 8/8 通过（校验器本身没被改坏）
- [ ] 会话记忆写了一篇

---

## 9. 禁止事项

- 禁止跳过任何秒段、只详写开头和结尾
- 禁止把标题/话题/评论/博主简介当剧情事实
- 禁止用点赞播放推断内容质量
- 禁止仿写"台词"，拿不准就标「不可确认」
- 禁止同系列 N 集算 N 个样本
- 禁止删除被推翻的知识卡（只能标 `refuted_by` / `superseded_by`）
- 禁止手改 `catalog/`、`MANIFEST.json`、`START-HERE.md` 状态块
- 禁止在库内放原片、完整逐字稿、他人解说全文（只放指针 + 哈希 + 必要短引）
- 禁止用单一博主代表整个赛道

---

## 10. 与旧十一卷产物的关系

现有 `01_最终交付` 的 35 部十一卷成品**不搬迁、不改写**，作为"档案原文"接进新库：

| 旧卷 | 新库位置 | 转换方式 |
|---|---|---|
| `00_总览.md` | `works/w-NNNN/dossier/00.md` | 指针引用；关键字段抽进 `profile.json` |
| `09_画面实录.md` | `dossier/09.md` + `beats.jsonl` | **必须转 jsonl**，否则不可检索 |
| `05_画面文字.md` + `subtitles.srt` | `dossier/05.md` | 指针 |
| `06_剪辑全谱…` | `dossier/06.md` + `data/curves.json` | 指标抽进 profile |
| `01–04,07,08,10` | `dossier/*.md` | 指针，内容不动 |
| — | `assessment.md` | **新写**（旧卷没有十维评分） |

转换只做三件事：**登记指针、抽 profile 字段、把 09 卷转成 beats.jsonl**。旧卷正文一个字不改，避免破坏已验证的证据链。
