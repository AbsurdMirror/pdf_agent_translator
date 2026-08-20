# -*- coding: utf-8 -*-
"""Markdown 清洗与表格/代码围栏修补。

\\file 渲染前与翻译后处理共用，避免只在 JS 里修一次。
"""

from __future__ import annotations

import re

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
_ROMAN_RE = re.compile(
    r"^(I{1,3}|IV|V|VI|VII|VIII|IX|X|XI|XII)\.\s+\S",
    re.IGNORECASE,
)
_LETTER_SEC_RE = re.compile(r"^[A-Z]\.\s+\S")
_NUM_SEC_RE = re.compile(r"^(\d+(?:\.\d+)*)\s+\S")
_REF_RE = re.compile(r"^(references|参考文献|acknowledg|致谢)\b", re.IGNORECASE)
_BROKEN_FENCE_RE = re.compile(r"^``([A-Za-z0-9_+-]+)\s*$", re.MULTILINE)
_LATEX_SYM = {
    "times": "×",
    "cdot": "·",
    "ge": "≥",
    "geq": "≥",
    "le": "≤",
    "leq": "≤",
    "neq": "≠",
    "ne": "≠",
    "approx": "≈",
    "infty": "∞",
    "pm": "±",
    "ldots": "…",
    "dots": "…",
    "cdots": "⋯",
    "alpha": "α",
    "beta": "β",
    "gamma": "γ",
    "delta": "δ",
    "mu": "μ",
    "pi": "π",
    "sigma": "σ",
    "omega": "ω",
    "ell": "ℓ",
    "left": "",
    "right": "",
}


def latex_inner_to_html(src: str) -> str:
    """把 $...$ 内部的常见 LaTeX 转成可显示的 HTML。

    \\brief 处理 \\_、\\times、\\text{}、上标下标。cache\\_size 保留下划线，不是下标。
    """

    text = src or ""
    text = text.replace("\\_", "\ue000")
    text = re.sub(r"\\text\{([^}]*)\}", r'<span class="mathrm">\1</span>', text)
    text = re.sub(r"\\mathrm\{([^}]*)\}", r'<span class="mathrm">\1</span>', text)
    text = re.sub(r"\\mathcal\{([^}]*)\}", r'<span class="mathcal">\1</span>', text)
    text = re.sub(r"\\([A-Za-z]+)", lambda m: _LATEX_SYM.get(m.group(1), m.group(0)), text)
    text = text.replace("\\{", "{").replace("\\}", "}")
    text = re.sub(r"\^\{([^}]+)\}", r"<sup>\1</sup>", text)
    text = re.sub(r"\^(\w)", r"<sup>\1</sup>", text)
    text = re.sub(r"_\{([^}]+)\}", r"<sub>\1</sub>", text)
    text = text.replace("\ue000", "_")
    return text


_CODE_HINT = re.compile(
    r"(__global__|__device__|__shared__|__syncthreads|cudaMemcpy|#include\b|"
    r"\bint\s+\*|for\s*\(|while\s*\(|if\s*\([^)]+\)\s*\{)",
    re.IGNORECASE,
)


def strip_heading_marks(text: str) -> str:
    """去掉行首 # 得到纯标题文字。"""

    line = (text or "").strip().splitlines()[0] if (text or "").strip() else ""
    match = _HEADING_RE.match(line)
    return match.group(2).strip() if match else line.strip()


def guess_heading_level(text: str, *, block_type: str, index: int) -> int | None:
    """按论文常见编号猜标题等级。

    \\brief 文题 1；I./II./参考文献 2；A./B. 3；1.2.3 按点数。
    \\return 1-4；不像标题则 None。
    """

    title = strip_heading_marks(text)
    if not title:
        return None
    if index == 0 and block_type == "title":
        return 1
    if _REF_RE.match(title):
        return 2
    if _ROMAN_RE.match(title):
        return 2
    if _LETTER_SEC_RE.match(title):
        return 3
    numbered = _NUM_SEC_RE.match(title)
    if numbered:
        return min(4, 1 + numbered.group(1).count("."))
    if block_type == "title":
        return 2
    return None


def apply_heading_level(markdown: str, level: int) -> str:
    """把一块标题 markdown 改成指定级数。"""

    level = max(1, min(6, int(level)))
    body = strip_heading_marks(markdown)
    rest = ""
    lines = (markdown or "").splitlines()
    if len(lines) > 1:
        rest = "\n" + "\n".join(lines[1:])
    return f"{'#' * level} {body}{rest}".rstrip() + "\n"


def fix_broken_fences(markdown: str) -> str:
    """把 ``c 修成 ```c，并补上缺失的闭合围栏。"""

    text = _BROKEN_FENCE_RE.sub(r"```\1", markdown or "")
    # 奇数个围栏行：在末尾补闭合。
    fence_lines = [ln for ln in text.splitlines() if ln.strip().startswith("```")]
    if len(fence_lines) % 2 == 1:
        text = text.rstrip() + "\n```\n"
    return text


def looks_like_code(markdown: str) -> bool:
    """启发式：像代码且还没包围栏。"""

    text = (markdown or "").strip()
    if not text or text.startswith("```"):
        return False
    if _CODE_HINT.search(text) and ("{" in text or ";" in text):
        return True
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if len(lines) >= 3:
        punct = sum(1 for ln in lines if any(ch in ln for ch in "{};="))
        return punct >= max(2, len(lines) // 2)
    return False


def wrap_as_code(markdown: str, lang: str = "c") -> str:
    """给裸代码包上 fenced block。"""

    body = (markdown or "").rstrip() + "\n"
    return f"```{lang}\n{body}```\n"


def normalize_pipe_table(markdown: str) -> str:
    """整理 GFM 表格：补两侧 |，分隔行统一成 ---。

    \\brief 不改单元格内容。渲染器也能吃不规范表，这里只是让模型输出更稳。
    """

    lines = (markdown or "").splitlines()
    if not any("|" in ln for ln in lines):
        return markdown or ""
    out: list[str] = []
    for raw in lines:
        line = raw.strip()
        if "|" not in line:
            out.append(raw)
            continue
        if not line.startswith("|"):
            line = "| " + line
        if not line.endswith("|"):
            line = line + " |"
        cells = [c.strip() for c in line.strip("|").split("|")]
        if cells and all(re.fullmatch(r":?-{2,}:?", c or "") for c in cells):
            line = "| " + " | ".join("---" for _ in cells) + " |"
        else:
            line = "| " + " | ".join(cells) + " |"
        out.append(line)
    return "\n".join(out) + ("\n" if markdown.endswith("\n") else "")


def gfm_table_to_html(markdown: str) -> str | None:
    """若整段是 GFM 表，转成 <table> HTML；否则 None。

    \\brief 给单测验证「表格能画出来」，与前端 tableHtml 规则对齐。
    """

    lines = [ln.strip() for ln in (markdown or "").splitlines() if ln.strip()]
    if len(lines) < 2 or not all("|" in ln for ln in lines[:2]):
        return None
    def cells(line: str) -> list[str]:
        return [c.strip() for c in line.strip().strip("|").split("|")]
    sep = cells(lines[1])
    if not all(re.fullmatch(r":?-{2,}:?", c or "") for c in sep):
        return None
    head = cells(lines[0])
    body = [cells(ln) for ln in lines[2:] if not all(re.fullmatch(r":?-{2,}:?", c or "") for c in cells(ln))]
    html = ["<table><thead><tr>"]
    html.extend(f"<th>{c}</th>" for c in head)
    html.append("</tr></thead><tbody>")
    for row in body:
        html.append("<tr>" + "".join(f"<td>{c}</td>" for c in row) + "</tr>")
    html.append("</tbody></table>")
    return "".join(html)


def polish_block_markdown(markdown: str) -> str:
    """本地可做的修补：围栏、裸代码、表格对齐。"""

    text = fix_broken_fences(markdown or "")
    if looks_like_code(text):
        text = wrap_as_code(text)
    if "|" in text and "---" in text:
        text = normalize_pipe_table(text)
    return text
