# 2026-10-30 · 全库审查与修复

## 起因

用户「先彻底的审查一遍」。不是抽查，是把库里每个脚本真跑一遍、每份文档的引用真核一遍、每条规则看有没有对应实现。

## 审查方法（怎么才算"彻底的"）

不看文档写了什么，看**运行行为**：

1. `find` 全树 + `wc -l` → 有没有空壳文件
2. `grep -r` 交叉引用 → 文档提到的脚本是否真实存在
3. 每个脚本跑一遍，再用**副本**构造违规数据，看能不能被抓到
4. AGENTS 十条硬规则逐条对照 `validate.py` 的实现
5. `jsonschema` 真校验一遍，看 schema 到底约束了什么

关键是第 3 步：**"有检查函数"不等于"检查有效"**。必须造假数据试。

## 查出 17 处缺陷，按性质分五类（A 5 / B 4 / C 4 / D 3 / E 1）

### A 类 · 校验空转（最危险：报错了，但按一下回车就消失）

| # | 问题 | 实证 |
|---|---|---|
| A1 | **元素白名单自我空转** | beats 写 `hook.自造标签` → validate 报未登记 → 跑 `build_index` → 标签被自动写进 `elements.json` → validate 通过。**注册表是自动生成的，又当白名单用，等于谁写谁合法** |
| A2 | **C5 校验器不存在** | `c5_errors` 只有 `new_work.py` 初始化的 0，没有任何脚本能算它 → verified 检查 `c5_errors==0` 永远通过 |
| A3 | **索引过期只看 count** | 改 profile 标题不重建、手改 catalog 条目，`--check` 三次全 exit=0 |
| A4 | **schema 从不被加载** | 242 行 `kb.schema.json`，`grep jsonschema` 零命中，只在 catalog 里当字符串引用挂着 |
| A5 | **C5 报告无产出机制** | AGENTS 要求 WARN 逐条写 `reports/c5-*.md`，`reports/` 是空的 |

### B 类 · 逻辑死锁与错误

| # | 问题 | 实证 |
|---|---|---|
| B1 | **成熟度死锁** | 单博主 3 部作品：`observation` 报"样本超 2"，`pattern` 报"博主不足 2"。**首批试点「煎饼果仔 19 部」必然撞墙** |
| B2 | **状态枚举无白名单** | `status='done'`（拼错）→ 状态机全部静默跳过，且不报"非法状态" |
| B3 | **creator 派生字段双写** | `profile.json` 的 `works_count=0/independent=0/series_ids=[]`，实际 1/1/['s-0001']；`catalog/creators.json` 是对的。同一事实两份数字，一份永远 0 |
| B4 | **prepped 状态谎报** | 判据是"`data/` 目录存在"，而 `new_work.py` 建的就是空 `data/` → 任何新作品生成骨架立刻变 prepped |

### C 类 · 语义与口径

| # | 问题 |
|---|---|
| C1 | `beats` 的 `t0/t1` 前格写"秒点"(`t1=3`)、末格写片长(`t1=215.34`)，同一字段两种含义；且 `[0,3]` 到 `[4,7]` 漏掉 3–4 秒，与 AGENTS「每行 t0/t1 连续无缝」直接矛盾 |
| C2 | 闸门编号漂移：SOP 里闸门 5=C5、闸门 6=上卷；`next_task.py` 说"闸门 6：秒列/回溯/锚点" |
| C3 | 卷目三套清单：AGENTS §10 十一卷；SOP 闸门4 缺 00 与 09；AGENTS §8 又要求 05+09 回溯 |
| C4 | `dup_check` 只在**没有** aweme_id 时才比 title+duration → 同素材换 ID 重发算两部，违反规则 9 |

### D 类 · 悬空引用

`_pipeline/zoom.py`、`_pipeline/status_block.py`、`schemas/work.schema.json` 三处被文档引用但不存在。

### E 类 · 外部依赖

`works/w-0001/frames` 是指向 `/workspace/02_在办/` 的符号链接，库一搬家就断。

## 修了什么

| 修复 | 做法 | 验证 |
|---|---|---|
| A1 元素词表 | 新建 `vocab/elements.yaml`（27 条，手维护）；`catalog/elements.json` 改为**统计**+ `unregistered` 单列 | 写自造标签跑 build_index 后再 validate，**仍报 ERROR** |
| A2 C5 校验器 | 新写 `_pipeline/c5.py`，F0–F5 六项，回写 `coverage.c5_errors`，产出 `reports/c5-<wid>.md` | w-0001 跑出 1 error（54 格 visual 空）+ 2 SKIP，报告落盘 |
| A3 索引比对 | `stale()` 改为内容级逐字段比对（剔时间戳），报第一处差异位置 | 改标题→报 `/items[0]/title 内容不同`；手改 catalog→同样抓到 |
| A4 schema 接入 | `validate.schema_req()` 从 schema 读 required，`check_schema()` 执行 | 删 `coverage`/`paths` → `缺 schema 必填字段 coverage` |
| A5 报告机制 | 由 `c5.py` 自动生成，含 ERROR/WARN/SKIP/PASS 四段与「WARN 说明」空位 | `reports/c5-w-0001.md` 已产出 |
| B1 死锁 | 成熟度改为按 `creator_count` 定档：observation = 单博主（样本不限） | 单博主 3 部走 observation **通过**；硬升 pattern **仍被拦** |
| B2 值域 | 加 `STATUS_WORK/STATUS_CREATOR/STATUS_KNOWLEDGE/CONFIDENCE` 白名单 | `status='done'` → 报"不在值域"，并列出非法后果 |
| B3 计数 | 新增 `build_index.py --sync-creators` 回写；validate 逐项比对 | 回写 `works_count→1, independent→1, series_ids→['s-0001']` |
| B4 prepped | 判据改为查产物（meta/cuts/帧/拼图/ocr/whisper 六项） | 只有帧 → `status=ingested` + note 列缺失项 |
| C1 区间语义 | `t0/t1` 统一为 `[4(N-1), 4N)`，末格截片长 | 54 格断裂数 0；c-01=0→4，c-54=212→215.34 |
| C2 编号 | `next_task` 闸门 6→5，补 c5 命令；SOP 闸门4 补 00/09 卷 | 状态块与排产一致 |
| C3 卷目 | SOP 闸门4 表补 `00` 与 `09`，并注明 09 是 C5 ground truth | — |
| C4 查重 | 分两级：aweme 命中 block；标题+时长吻合 warn（`--force` 放行） | 三种情形均正确 |
| D 悬空引用 | 新建库内 `_pipeline/zoom.py`（按秒号，内部换算 f_{sec+1}）；修 FLOW 的 status_block 与 AGENTS 的 work.schema | 94s → f_0095 → 放图确认是「早态度好点不就早不找你茬了」 |

## 固化：把这次的实证变成回归测试

上面 8 个"造假数据看它会不会红"的动作，全部写进了 `_pipeline/selftest.py`：

| 用例 | 造什么违法数据 | 期望哪道闸门红 |
|---|---|---|
| 索引内容篡改 | 手改 `catalog/works.json` 的 title | `build_index --check` 报「内容不同」 |
| 词表外标签 | beats 写 `hook.自造标签` 并跑过 build_index | validate 仍报「未登记」 |
| status 拼错 | `status: done` | 报「不在值域」 |
| 博主计数漂移 | `works_count: 99` | 报与磁盘不符 |
| schema 必填缺失 | 删 `coverage`/`paths` | 报「schema 必填字段」 |
| 成熟度越级 | 单博主 3 部标 pattern | 报「creator_count=1 < 2」 |
| beats 区间断裂 | 把 c-02 的 t0 改成 9 | 报「不衔接」 |
| correction 三要素 | 只写 source+was | c5 报「缺 is」 |

当前 **8/8 通过**。以后改任何脚本先跑这个——它红，说明某道闸门被改坏了。

这是本轮最重要的产物：**库从此能证明自己的检查是活的**，而不是靠谁口头说"校验过了"。

## 还剩什么（没修，要用户定）

1. **w-0001 的数据在库外**：frames 是符号链接，contact/data 都在 `/workspace/02_在办/晒月光第三集/`。要不要搬进库？
2. **SOP 闸门2 的六件套仍依赖库外脚本**（抽帧/拼图/OCR/四曲线）。诚实标注了"复用已验证实现"，但没迁进 `_pipeline/`。
3. **旧 35 部 09 卷 → beats.jsonl 的转换器不存在**（Q-004）。不做迁移的决策下，这个不急。

## 一句话结论

建库那轮我把「流程」立起来了，但**校验层有一半是纸面的**——规则写在 AGENTS 里，检查器要么没有、要么在空转。这轮把每条规则都钉到了会真正失败的脚本上。

判断标准很简单：**造一个违法数据，看它会不会红。不会红的规则等于没写。**
