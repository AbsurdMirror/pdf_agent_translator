# -*- coding: utf-8 -*-
"""对已有 document.json 做本地修补 + 目录优化，不必重跑全文翻译。

\\file 表格/代码先规则修；标题等级交给 MiniMax。
"""

from __future__ import annotations

import logging

from pdf_agent_translator.config import Settings
from pdf_agent_translator.models import Document, refresh_translation_counts
from pdf_agent_translator.render.mdutil import polish_block_markdown
from pdf_agent_translator.translate.outline import apply_outline, refine_outline_with_llm

logger = logging.getLogger(__name__)


def polish_document(document: Document, settings: Settings) -> Document:
    """原地修补 markdown，生成 outline。

    \\param document 已翻译文档。
    \\param settings 含 LLM，用于目录优化。
    \\return 同一 document。
    """

    for pair in document.pairs:
        pair.source.markdown = polish_block_markdown(pair.source.markdown)
        if pair.target.markdown:
            pair.target.markdown = polish_block_markdown(pair.target.markdown)

    entries = refine_outline_with_llm(document, settings.llm)
    apply_outline(document, entries)
    refresh_translation_counts(document)
    logger.info("已整理目录 %s 项，并修补表格/代码围栏", len(document.outline))
    return document
