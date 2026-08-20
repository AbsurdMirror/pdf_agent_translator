# -*- coding: utf-8 -*-
"""翻译入口：OpenAI 兼容接口按序逐块翻译。"""

from __future__ import annotations

from collections.abc import Callable

from pdf_agent_translator.config import Settings
from pdf_agent_translator.translate.openai_backend import translate_with_openai
from pdf_agent_translator.translate.store import BlockStore


def run_translation(
    store: BlockStore,
    settings: Settings,
    *,
    on_progress: Callable[[int, int, str], None] | None = None,
) -> str:
    """执行整篇未完成块的翻译。

    \\param store 已加载的文档。
    \\param settings 运行配置。
    \\param on_progress (index, total, status)。
    \\return 实际 backend 名。
    """

    return translate_with_openai(
        store,
        settings.llm,
        window_k=settings.translate.context_window_blocks,
        source_lang=settings.translate.source_lang,
        target_lang=settings.translate.target_lang,
        stop_on_error=settings.translate.stop_on_block_error,
        on_progress=on_progress,
    )
