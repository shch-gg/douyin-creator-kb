# _inbox · 投料区

## 怎么投

**单条 / 多条链接**：一行一条贴进 `urls.txt`，然后说"跑"。

```text
https://v.douyin.com/xxxxxxx/
https://v.douyin.com/yyyyyyy/
```

**一个博主主页**：贴主页链接，加一行注释说明范围。

```text
# creator:煎饼果仔 全量
https://www.douyin.com/user/MS4wLjABAAAA...
```

**本地视频**：把文件放进 `files/`，文件名用 `博主名-标题.mp4`。

## 状态

`status.json` 记每条链接的处理状态：`pending` / `done` / `skipped` / `failed:<原因>`。
由 `new_work.py` 与人工共同维护；`next_task.py` 只列非 `done/skipped` 的。

## 纪律

- 一次投料不超过 10 条，否则排产会乱
- 同一条链接重复投不会重复建档（`aweme_id` 查重）
- 拿不到 `aweme_id` 的，在链接后加 `| 标题 | 时长秒`，脚本用三元组兜底
