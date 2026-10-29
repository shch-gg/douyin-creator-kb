# 10 · 入库 SOP（单条作品，九闸门）

> 这是最常走的一条路：用户丢一条抖音链接，从零到 `verified`。
> 每一步都有**命令**和**完成标志**。卡住就重跑 `next_task.py`。

---

## 闸门 0 · 查重与分配 ID

```bash
cd /workspace/抖音博主知识库
python3 _pipeline/new_work.py --creator "煎饼果仔" --title "晒月光 第三集" \
    --aweme 7427807581223111999 --duration-ms 215340 --series "晒月光" --episode 3
```

脚本做四件事：解析短链 → 查 `catalog/works.json` 有无同 `aweme_id` → 分配下一个 `w-NNNN` → 建目录与 `profile.json` 骨架（`status: planned`）。

手工兜底（脚本挂了才用）：

```bash
# 解析短链（跟随跳转取 aweme_id）
curl -sIL "https://v.douyin.com/XXXX/" | grep -oE 'video/[0-9]{15,}' | head -1
# 查重
grep -c '"aweme_id": "7424789970633657612"' catalog/works.json
```

**完成标志**：`works/w-NNNN/profile.json` 存在，`aweme_id` 已填，查重为 0 命中。

**没有 aweme_id 怎么办**：用「博主名 + 标题 + 时长（±1s）」三元组查重，`aweme_id` 写 `null` 并在 `note` 说明。`validate` 会给 WARN，不阻断。

---

## 闸门 1 · 投料落盘

```bash
W=w-0001
mkdir -p works/$W/{media,data,frames,contact,dossier}

# 1) 原片（不入库，只放 media/ 指针；大文件建议留在库外 D 盘）
# 2) 指纹
sha256sum works/$W/media/raw.mp4 > works/$W/media/raw.sha256

# 3) 元信息
ffprobe -v error -show_entries format=duration,size,bit_rate \
        -show_entries stream=width,height,r_frame_rate,nb_frames,codec_name \
        -of json works/$W/media/raw.mp4 > works/$W/data/meta_raw.json
```

`raw.json`（平台元信息：作者、标题、话题、点赞/评论/转发/收藏、发布时间、音乐）用一个抓取脚本落到 `works/$W/data/raw.json`。

**完成标志**：`profile.json.source.sha256` 有值；`duration_ms` 与 ffprobe 一致（±10ms）；平台字段抓不到的写 `null`，**不许填 0 冒充**。

`status → ingested`

---

## 闸门 2 · 技术前处理

```bash
W=w-0001
DUR=$(python3 -c "import json;print(json.load(open('works/$W/data/meta_raw.json'))['format']['duration'])")

# 1) 1fps 抽帧（帧数 = ⌈时长⌉）
ffmpeg -v error -i works/$W/media/raw.mp4 -vf fps=1 -q:v 2 works/$W/frames/f_%04d.jpg

# 2) 2×2 拼图（一格 4 秒，行优先；末格不满属正常）
#    用 methods/../tools/make_contact.py，或 ffmpeg tile：
ffmpeg -v error -i works/$W/frames/f_%04d.jpg -vf "tile=2x2" -q:v 2 works/$W/contact/c_%02d.jpg

# 3) 音频
ffmpeg -v error -i works/$W/media/raw.mp4 -vn -ac 1 -ar 16000 works/$W/media/audio16k.wav

# 4) 切点（硬切）
ffmpeg -v error -i works/$W/media/raw.mp4 -vf "select='gt(scene,0.35)',showinfo" -f null - 2>&1 \
  | grep -oE 'pts_time:[0-9.]+' | cut -d: -f2 > works/$W/data/cuts.txt

# 5) 黑场
ffmpeg -v error -i works/$W/media/raw.mp4 -vf blackdetect=d=0.1:pix_th=0.10 -f null - 2>&1 \
  | grep blackdetect > works/$W/data/black.txt

# 6) Whisper（turbo）
HF_HUB_CACHE=/root/.cache/huggingface/hub \
python3 -m whisper --model turbo --language zh --output_format json \
  --output_dir works/$W/data works/$W/media/audio16k.wav

# 7) OCR（全帧，双区扫描：中部旁白板 + 底部字幕）
#    用 /workspace/02_在办/晒月光第三集/ocr_par2.py 的成熟实现（4 worker × 单线程 × det_limit_side_len=480）
python3 <库外>/ocr_par2.py --frames works/$W/frames --out works/$W/data/ocr.json

# 8) 四曲线（亮度/饱和/对比/人声，15s 窗）
#    用 /workspace/02_在办/晒月光第三集 的四曲线脚本（four_curves.json 口径）
python3 <库外>/four_curves.py works/$W/media/raw.mp4 works/$W/media/audio16k.wav > works/$W/data/curves.json
```

> **脚本现状**：`_pipeline/` 已实现 `new_work` / `make_beats_skeleton` / `build_index` / `validate` / `next_task`。
> 抽帧、拼图、OCR、四曲线目前复用 `/workspace/02_在办/晒月光第三集/` 下已验证的实现，迁入 `_pipeline/` 前先别改逻辑。

**完成标志**：`frames/` 帧数 = ⌈时长⌉；`contact/` 张数 = ⌈帧数/4⌉；`cuts.txt`、`black.txt`、`ocr.json`、`curves.json`、whisper json 全部非空。

`status → prepped`

**已知坑**：

- Whisper 的 `_envd.py` 会把 `HF_HUB_CACHE` 指向 D 盘，必须显式覆盖，否则卡在下载
- OCR 单帧双区约 2–6s，215 帧要 10 分钟以上；**别用 8 进程**（实测机器只有 4 核配额），4 worker × 单线程 × `det_limit_side_len=480` 最稳
- 中部旁白板必须**全尺寸**识别，缩一半会把「有靠山」认成「没有靠山」

---

## 闸门 3 · 逐格精读 → beats.jsonl

这是全库地基，**不能自动化**。

```bash
# 先生成骨架（t0/t1/grid 已填，visual 留空）
python3 _pipeline/make_beats_skeleton.py w-0001

# 再逐格亲读补全：打开 contact/c_NN.jpg，4 格一起看，逐格写 visual/sub/speech/func
```

补全规则：

| 字段 | 怎么填 | 不许 |
|---|---|---|
| `visual` | 谁、在哪、做什么、光线/景别 | 不许写"画面很美" |
| `sub` | **画面亲读**的字幕原文 | 不许抄 Whisper；不许补标点 |
| `speech` | 听到的话，可带说话人 | 不许与 `sub` 合并 |
| `sound` | 环境声/配乐/静音 | 不许写"音乐很好听" |
| `func` | 命名空间标签：`hook.*` `turn.*` `beat.*` `end.*` | 不许自造未登记标签 |

**定字流程（冲突时）**：

```bash
# 按秒号放大该秒的底部字幕带（内部换算 f_{sec+1}）
python3 _pipeline/zoom.py w-0001 63 0.80 0.98 0.1 0.9 5 /tmp/x.png
```

放大后逐字读。第三集 63s 实例：Whisper「你不欺负别人啊」→ 实为「怎么他妈就欺负你」；OCR「早态度好点不就不找你茬了」漏一个「早」→ 实为「早态度好点不就早不找你茬了」。

**完成标志**：`beats.jsonl` 行数 = 拼图数；`t0` 从 0 开始逐格无缝；每行 `visual` 非空。

`status → read`

---

## 闸门 4 · 十维拆解

十卷结构（沿用已验证的十一卷体例，映射见 `AGENTS.md` §10）：

| 卷 | 写什么 | 必须带 |
|---|---|---|
| `00` 总览 | 一句话故事、片长/帧数/切点数/拼图数、八条结论速览 | 量化面板与任何结论口径一致 |
| `01` 创作解码 | 故事、人物、主题、命题 | 每段秒号 |
| `02` 视听反解 | 构图/光影/色彩/镜头语言 | 每段秒号 + 景别 |
| `03` 复刻迁移 | 可复制的分镜/Prompt/配乐 | 具体参数 |
| `04` 配乐声音 | 音乐进入点、静默段、音效 | 秒号 |
| `05` 画面文字 | 全片字幕/旁白板/字卡谱 | 逐字 + 秒域（两列：`| 秒域 | 文字 |`） |
| `06` 剪辑全谱 | 切点逐条 + 四曲线共振 | 相关系数 + 口径 |
| `07` 叙事语法 | 信息释放顺序、设问与兑现 | 秒号 |
| `08` 制作还原 | 场景、道具、表演调度 | 秒号 |
| `09` 画面实录 | **逐秒 ground truth**：每格写谁在哪做什么、字幕原文、旁白板全文 | `**c_NN（s0–s1s）**` 行首 + `NNNs 字幕「…」` 登记（F2/F3 全靠这卷） |
| `10` 创作法与作者意图 | E3 判断，必须有 based_on | 置信度 |
| `assessment.md` | 十维 0–10 + 卖点 + 强场面 Top5 | 每分有证据 |

> `09` 是 C5 的 ground truth 来源，不能省。`00` 与 `05` 的量化数字必须能追到 `data/` 下的原始产物（元信息/切点/OCR json），不许另算一套。

**完成标志**：十维每维都有分；`assessment.md` 存在；每条结论能指到秒。

`status → decomposed`

---

## 闸门 5 · C5 自校验

```bash
python3 _pipeline/c5.py w-0001
```

五条（新库实现见 `_pipeline/c5.py`，报告写 `reports/c5-<wid>.md`）：

| 条 | 查什么 |
|---|---|
| **F0** | 内容完整性：每格 `visual` 非空；`func` 命中 `vocab/elements.yaml`；`speech[].t` 落在本格区间 |
| F1 | 时间轴单调递增（beats 的 t0；srt 条目按时间升序） |
| F2 | `beats.sub` 非空 → 09 卷有对应「字幕「…」」登记；反向孤儿字幕也报 WARN |
| F3 | 跨卷锚点一致：beats 末格 = 片长；05 卷最大登记秒 ≤ 片长 |
| F4 | `c-NN` 连续无重号 + 区间 `[4(N−1), 4N)` 首尾相接（末格豁免到片长） |
| F5 | srt ↔ 05 双向：条数相等、起始秒命中 05 秒集合、止秒不越界 |

**完成标志**：`c5.py` 输出 0 error；WARN 逐条写进 `reports/c5-w-NNNN.md` 的「WARN 说明」段落，说明为什么可接受。
SKIP 表示对应卷宗还没产出——**SKIP 不是通过**，卷宗补完后必须重跑。

脚本会把结果回写到 `profile.coverage.c5_errors / c5_warns / c5_checked_at`，`validate.py` 在 `verified` 时读这里。

---

## 闸门 6 · 上卷（博主层）

```bash
# 上卷目前是手工重算三页（脚本待建：要先有 ≥2 部作品才谈得上"指纹"）
# 打开 creators/c-0001/{fingerprint,matrix,trajectory}.md，按 AGENTS.md §3.1 的判据逐条重写
```

三页各自的硬指标见 `AGENTS.md` §3.1。**关键：指纹每条要 ≥2 部作品支撑，只有 1 部时只能写"单部观察"。**

## 闸门 7 · 知识提炼

见 `methods/30-知识提炼.md`。**完成标志**：`knowledge_delta` 已写（新增/修订/推翻/`none_reason` 四选一）。

## 闸门 8 · 索引与发布

```bash
python3 _pipeline/build_index.py
python3 _pipeline/validate.py
```

**完成标志**：`validate` 输出 0 error；`MANIFEST` 计数与磁盘一致；`START-HERE` 状态块已刷新。

`status → verified`

---

## 旁路 · 既有档案回收（backfill）

适用于**已经在别处拆完 11 卷**的作品（本库现为 `01_最终交付/` 下 36 部）。不重拆，只把可机读的部分搬进来。

```bash
cd /workspace/抖音博主知识库

# 1) 先干跑，看解析率与档案缺陷
python3 _pipeline/backfill.py --dry-run

# 2) 正式回填（新建）
python3 _pipeline/backfill.py --apply

# 3) 重写已存在的（改了解析规则后）
python3 _pipeline/backfill.py --apply --rewrite

# 4) 必定要跟着做的两步
python3 _pipeline/build_index.py --sync-creators
python3 _pipeline/build_index.py
```

**搬什么、不搬什么**（这条界线决定了回填数据能用来做什么）：

| 字段 | 来源 | 可靠性 |
|---|---|---|
| `grid / t0 / t1` | 09 卷 `**c_NN（a–bs）**` 标题，按 `[4(N−1), 4N)` 转连续区间 | 高（末格按 00 卷片长裁齐） |
| `visual` | 同块正文去秒标后前 600 字 | 高（档案原文，非本次亲读） |
| `sub` | 行文里 `字幕「…」`；通篇不用该词的（如《山鸟》）回退到 `「…」` | 中（05 卷表格型画面文字**未**搬，故是下界） |
| `shot / move / speech / sound / music / func` | — | **一律留空**，档案没有逐格结构化字段，不许猜 |
| `assessment` 十维 | — | **留 null**，既有档案的评分表格式不统一，不能硬凑 |

**三类已知档案缺陷**（`backfill.py` 会自动检测并打印 `[档案缺陷:…]`）：

1. **合并标题** `**c_20（76–79s）–c_21（80–83s）**` — 一行登记两格，解析时展开。
2. **范围标题** `**c_81–c_82（320–327s）**` — 用连字符表示范围，解析成两格。实证：《山河无恙》展开后 145 格，与档案自述「145 张拼图」吻合。
3. **格号乱序** — c_96/c_97 写到文档中段、c_90–c_95 在文末，解析后按格号重排。

**状态记 `backfilled`，不是 `decomposed`。** 前者意思是「beats 来自档案解析，本库闸门 2 没跑」；后者会被 `validate.py` 要求有 `frames/`、`contact/`、`data/ocr.json`，一查就露。想升 `verified` 必须补 05 卷画面文字与十维评估。

---

## 收工清单

- [ ] `_会话记忆/sessions/YYYY-MM-DD-<slug>.md` 写了一篇，`index.md` 加一行
- [ ] 用户拍板的规则进了 `decisions.md`
- [ ] 待核项进了 `open-questions.md`
- [ ] `next_task.py` 跑一遍，确认没有新露出的待办
- [ ] 动过 `_pipeline/` 任何脚本 → `selftest.py` 必须 8/8
