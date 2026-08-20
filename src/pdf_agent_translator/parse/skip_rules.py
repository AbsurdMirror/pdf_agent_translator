# -*- coding: utf-8 -*-
"""确定性跳过规则。

\\file 原样移植 PDF_Translator LayoutTranslator._should_skip_layout。
"""

from __future__ import annotations

import re

# 来源：layout_translator.py SKIP 类型与正则（ASCII 括号）。
SKIP_TYPES = {"figure", "formula", "equation", "math", "latex"}
IMAGE_MARKDOWN_PATTERN = re.compile(r"!\[[^\]]*?\]\([^\)]*?\)")
IMAGE_HTML_PATTERN = re.compile(r"<img\b[^>]*>", re.IGNORECASE)
FORMULA_BLOCK_PATTERN = re.compile(
    r"\$\$[\s\S]*?\$\$|\\\[[\s\S]*?\\\]|"
    r"\\begin\{(?:equation|align|aligned|eqnarray|math)\}[\s\S]*?"
    r"\\end\{(?:equation|align|aligned|eqnarray|math)\}",
    re.IGNORECASE,
)


def is_image_only(content: str) -> bool:
    """去掉图片语法后是否为空。

    \\param content markdown。
    \\return 只剩空白则为 True。
    """

    stripped = IMAGE_MARKDOWN_PATTERN.sub("", content)
    stripped = IMAGE_HTML_PATTERN.sub("", stripped)
    return stripped.strip() == ""


def is_formula_only(content: str) -> bool:
    """去掉公式块后是否为空。

    \\param content markdown。
    \\return 只剩公式则为 True。
    """

    return FORMULA_BLOCK_PATTERN.sub("", content).strip() == ""


def skip_reason_for(layout_type: str, markdown: str) -> str | None:
    """判断一块是否应确定性跳过。

    \\param layout_type Aliyun type。
    \\param markdown markdownContent。
    \\return 原因字符串；不跳过则 None。
    """

    kind = (layout_type or "").strip().lower()
    if kind in SKIP_TYPES:
        return f"deterministic:type:{kind}"
    content = (markdown or "").strip()
    if content == "":
        return "deterministic:empty"
    if is_image_only(content):
        return "deterministic:image_only"
    if is_formula_only(content):
        return "deterministic:formula_only"
    return None
