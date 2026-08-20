# -*- coding: utf-8 -*-
"""剥离 MiniMax 默认塞进 content 的 <think> 块。

\\file 请求已关思考；若模型仍把 <think> 塞进 content，这里剥掉。
"""

from __future__ import annotations

import re

_THINK_RE = re.compile(r"<think\b[^>]*>[\s\S]*?</think>", re.IGNORECASE)
_UNCLOSED_THINK_RE = re.compile(r"<think\b[^>]*>[\s\S]*$", re.IGNORECASE)


def strip_think(text: str | None) -> str:
    """去掉思考标签，只留正文。

    \\param text 模型 content。
    \\return 剥完并 strip 的字符串；只有思考则空串。
    """

    if not text:
        return ""
    cleaned = _THINK_RE.sub("", text)
    # 被 max_tokens 截断时可能没有闭合标签。
    cleaned = _UNCLOSED_THINK_RE.sub("", cleaned)
    return cleaned.strip()
