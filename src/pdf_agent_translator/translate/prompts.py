# -*- coding: utf-8 -*-
"""学术论文翻译提示词。

\\file 明确要求修表格、代码围栏和标题级数，避免 Aliyun 解析残留。
"""

from __future__ import annotations

from pdf_agent_translator.models import GlossaryEntry, TranslationPair

SYSTEM_PROMPT = """You are a professional academic paper translator and Markdown repairer.
Translate the source {src} text into {tgt} accurately.

Output ONLY the translated Markdown. No explanations, no <think> tags.

Markdown repair (do this even if the source is messy):
- Headings: use a sensible level, not everything as #.
  Paper title = # ; major sections (I. II. INTRODUCTION, REFERENCES) = ## ;
  subsections (A. B. C.) = ### ; deeper = ####.
- Tables: emit a valid GitHub-flavored table. Header row, then a separator
  row like | --- | --- |, then data rows. Every row must start and end with |.
  Same number of columns in every row. Do not flatten a table into paragraphs.
- Code: if the block is source code, wrap it in a fenced block with THREE
  backticks, e.g. ```c ... ```. Never write ``c (only two backticks).
  Keep comments; translate comment text only. If the source forgot fences
  but looks like C/CUDA/Python, add fences.
- Keep images ![alt](url), math $...$ / $$...$$, DOI and citation keys unchanged
  except translating surrounding prose.
- Lists stay lists. Paragraph breaks stay.
"""


def build_block_prompt(
    *,
    pair: TranslationPair,
    window: list[tuple[str, str]],
    glossary: list[GlossaryEntry],
    src: str,
    tgt: str,
) -> str:
    """构造当前块的 user prompt（含滑动窗口与术语表）。"""

    parts: list[str] = [
        f"Translate the following {src} academic text into {tgt}.",
        f"This layout type is: {pair.source.type}.",
    ]
    if pair.source.type == "table":
        parts.append("This is a TABLE. Output a valid GFM pipe table.")
    if pair.source.type == "title":
        parts.append("This is a HEADING. Choose # / ## / ### correctly.")
    if glossary:
        parts.append("Glossary (keep consistent):")
        for item in glossary:
            note = f" ({item.note})" if item.note else ""
            parts.append(f"- {item.source} -> {item.target}{note}")
    if window:
        parts.append("Recent bilingual context (do not re-translate):")
        for src_md, tgt_md in window:
            parts.append(f"[SRC]\n{src_md}\n[TGT]\n{tgt_md}")
    parts.append("Now translate this block:")
    parts.append(pair.source.markdown)
    return "\n\n".join(parts)
