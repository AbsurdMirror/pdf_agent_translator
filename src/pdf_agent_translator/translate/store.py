# -*- coding: utf-8 -*-
"""BlockStore：按块落盘，不是 PyTool。

\\file 一把 cancel_event；禁止 store.cancel bool。
"""

from __future__ import annotations

import logging
import re
import threading
from pathlib import Path

from pdf_agent_translator.models import (
    BlockStatus,
    Document,
    refresh_translation_counts,
)
from pdf_agent_translator.persist.job import load_document, save_document

logger = logging.getLogger(__name__)
_MD_IMAGE = re.compile(r"!\[[^\]]*?\]\([^\)]*?\)")


class BlockStore:
    """读写 document.json 上的翻译对。"""

    def __init__(self, document_path: Path, cancel_event: threading.Event, *, strict: bool = False) -> None:
        self.document_path = document_path
        self.cancel_event = cancel_event
        self.strict = strict
        self.document: Document = load_document(document_path)

    def is_cancelled(self) -> bool:
        """是否已取消。只读 Event。"""

        return self.cancel_event.is_set()

    def persist(self) -> None:
        """重算计数并原子写盘。"""

        refresh_translation_counts(self.document)
        save_document(self.document_path, self.document)

    def first_unfinished_index(self) -> int | None:
        """文档序第一个 pending/failed 下标。"""

        for idx, pair in enumerate(self.document.pairs):
            if pair.target.status in {BlockStatus.pending, BlockStatus.failed}:
                return idx
        return None

    def submit_translation(self, block_id: str, markdown: str, *, model_name: str | None = None) -> None:
        """写入一块译文。

        \\param block_id 主键。
        \\param markdown 已剥 think 的正文。
        \\param model_name 使用的模型。
        \\throws KeyError / ValueError。
        """

        pair = self._require(block_id)
        text = (markdown or "").strip()
        if not text:
            raise ValueError("译文为空")
        # 源文有图而译文一张不剩：视为模型吞图。
        if _MD_IMAGE.search(pair.source.markdown or "") and not _MD_IMAGE.search(text):
            raise ValueError("译文丢失了源文中的图片语法")
        pair.target.markdown = text
        pair.target.status = BlockStatus.translated
        pair.target.error = None
        pair.target.model_name = model_name
        self.persist()

    def mark_failed(self, block_id: str, error: str) -> None:
        """本块失败，立即落盘。"""

        pair = self._require(block_id)
        pair.target.status = BlockStatus.failed
        pair.target.error = error
        self.persist()
        logger.warning("块失败 %s: %s", block_id, error)

    def summary_text(self) -> str:
        """给 send_message 用的一句摘要。"""

        meta = self.document.translation
        return (
            f"done translated={meta.translated} skipped={meta.skipped} "
            f"failed={meta.failed} pending={meta.pending}"
        )

    def _require(self, block_id: str):
        for pair in self.document.pairs:
            if pair.source.block_id == block_id:
                return pair
        raise KeyError(block_id)
