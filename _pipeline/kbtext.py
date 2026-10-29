#!/usr/bin/env python3
"""kbtext.py —— beats 文本字段的清洗规则（唯一实现，供 backfill/text05/fix 共用）。

为什么单独抽出来：档案源是 markdown，正文里大量 `**加粗**`、`` `code` ``、`[x](url)`。
这些标记在 09 卷里是排版强调，搬进 beats 就变成脏数据——
搜「生日礼物」搜不到实际存的 `**生日礼物**`；知识卡引用字幕原文会带星号；
跨作品做词频/共现统计时标记符会污染分词。

规则只有一条：beats 的文本字段只装**内容**，不装渲染标记。
清洗是幂等的，重复跑不会二次损伤。
"""

import re

# 行内链接 [文本](url) → 文本
_LINK = re.compile(r"\[([^\]\n]{0,80})\]\((?:[^()\s]{1,200})\)")
# 图片 ![alt](url) 直接丢
_IMG = re.compile(r"!\[[^\]\n]{0,80}\]\((?:[^()\s]{1,200})\)")
# 行内代码 `x` → x
_CODE = re.compile(r"`{1,3}([^`\n]{0,200})`{1,3}")
# 强调 **x** / __x__ / *x* / _x_（下划线要防 snake_case 误伤）
_STRONG = re.compile(r"\*{2,3}([^*\n]{0,300}?)\*{2,3}")
_EM_STAR = re.compile(r"(?<![*\w])\*(?!\s)([^*\n]{1,120}?)(?<!\s)\*(?![*\w])")
_EM_UND = re.compile(r"(?<![A-Za-z0-9_])_{1,2}(?!\s)([^_\n]{1,120}?)(?<!\s)_{1,2}(?![A-Za-z0-9_])")
# 残留的裸标记与转义
_STRAY = re.compile(r"(?<!\\)\*{2,}|\\(?=[*_`\[\]#])")
# HTML 注释 <!-- x -->
_HTML_C = re.compile(r"<!--.*?-->", re.S)


def demd(s: str) -> str:
    """去掉 markdown 渲染标记，保留可见文本。"""
    if not s:
        return ""
    t = _HTML_C.sub("", s)
    t = _IMG.sub("", t)
    t = _LINK.sub(r"\1", t)
    t = _STRONG.sub(r"\1", t)
    t = _EM_STAR.sub(r"\1", t)
    t = _EM_UND.sub(r"\1", t)
    t = _CODE.sub(r"\1", t)
    t = _STRAY.sub("", t)
    # 清理多余空白（全角空格保留一个，因为档案用它做视觉分隔）
    t = re.sub(r"[ \t]{2,}", " ", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


def has_md(s: str) -> bool:
    """是否含未被清洗的 markdown 渲染标记（validate 用）。

    只认「标记」，不认「内容里的星号」。这条边界踩过坑：
    聊天截图里的未读数「4*」「5*」（遮罩真数字）、字幕残字「*\」都是画面事实，
    如果 `"*" in s` 一律判脏，validate 会把真内容报成错误，人就会去改数据而不是改代码。
    """
    if not isinstance(s, str) or not s:
        return False
    if "**" in s or "`" in s:          # 加粗/分隔/行内代码：出现即成对，无歧义
        return True
    if re.search(r"\[[^\]\n]{1,60}\]\([^)\n]{1,200}\)", s):   # 行内链接
        return True
    if re.search(r"(?<![A-Za-z0-9_])__[^_\n]{1,60}__(?![A-Za-z0-9_])", s):
        return True
    return False
