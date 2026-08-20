# -*- coding: utf-8 -*-
"""翻译入口：优先 qfaos，失败则 OpenAI 兼容兜底。

\\file 不修改 qiufeng-agent-os。
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

from pdf_agent_translator.config import Settings
from pdf_agent_translator.translate.openai_backend import translate_with_openai
from pdf_agent_translator.translate.qfaos_backend import QfaosUnavailable, translate_with_qfaos
from pdf_agent_translator.translate.store import BlockStore

logger = logging.getLogger(__name__)


def run_translation(
    store: BlockStore,
    settings: Settings,
    *,
    log_dir: Path,
    on_progress: Callable[[int, int, str], None] | None = None,
) -> str:
    """执行整篇未完成块的翻译。

    \\param store 已加载的文档。
    \\param settings 运行配置。
    \\param log_dir qfaos jsonl 目录。
    \\param on_progress (index, total, status)。
    \\return 实际 backend 名。
    """

    kwargs = dict(
        window_k=settings.translate.context_window_blocks,
        source_lang=settings.translate.source_lang,
        target_lang=settings.translate.target_lang,
        stop_on_error=settings.translate.stop_on_block_error,
        on_progress=on_progress,
    )
    try:
        name = translate_with_qfaos(
            store,
            settings.llm,
            settings.qfaos,
            log_dir=log_dir,
            **kwargs,
        )
        logger.info("翻译后端: qfaos")
        return name
    except QfaosUnavailable as exc:
        logger.warning("qfaos 不可用，改走 OpenAI 兼容接口: %s", exc)
        return translate_with_openai(store, settings.llm, **kwargs)
