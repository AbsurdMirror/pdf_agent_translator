# -*- coding: utf-8 -*-
"""文档与任务的权威数据模型。

\\file 源文/译文是独立字段；outline 供侧栏目录跳转。
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field

SCHEMA_VERSION = "1.0.0"


class BlockStatus(str, Enum):
    """一块译文的生命周期状态。"""

    pending = "pending"
    skipped = "skipped"
    translated = "translated"
    failed = "failed"
    edited = "edited"


class JobPhase(str, Enum):
    """job.toml 里的流水线阶段，权威来源。"""

    created = "created"
    parsing = "parsing"
    parsed = "parsed"
    translating = "translating"
    translated = "translated"
    rendered = "rendered"
    failed = "failed"


class Comment(BaseModel):
    """段落评论。v1 UI 不实现，字段 reserved。"""

    id: str
    text: str
    created_at: str


class SourceBlock(BaseModel):
    """解析得到的原文块。"""

    block_id: str = Field(description="主键：优先 uniqueId，否则 b{index:04d}")
    index: int = Field(description="文档序，0-based")
    aliyun_index: int | None = None
    page_num: int | None = Field(default=None, description="Aliyun 0-based 页码")
    type: str = "text"
    sub_type: str | None = None
    markdown: str = ""
    text: str | None = None
    alignment: str | None = None
    unique_id: str | None = None
    edited: bool = False
    extra: dict[str, Any] = Field(default_factory=dict)


class TargetBlock(BaseModel):
    """与原文配对的译文块。"""

    markdown: str = ""
    status: BlockStatus = BlockStatus.pending
    skip_reason: str | None = None
    skip_kind: Literal["deterministic", "agent"] | None = None
    model_name: str | None = None
    error: str | None = None
    edited: bool = False


class TranslationPair(BaseModel):
    """一对原文+译文。"""

    source: SourceBlock
    target: TargetBlock
    comments: list[Comment] = Field(default_factory=list)
    display_order: int = 0


class GlossaryEntry(BaseModel):
    """术语表条目，注入翻译 prompt。"""

    source: str
    target: str
    note: str | None = None


class OutlineEntry(BaseModel):
    """目录项：对应某一标题块，供侧栏跳转。"""

    block_id: str
    level: int = Field(description="1-4，对应 # 到 ####")
    title: str = Field(description="展示用标题（通常取译文）")
    source_title: str = ""
    pair_index: int = 0


class ParseMeta(BaseModel):
    """解析阶段元数据。"""

    status: str = "idle"
    docmind_job_id: str | None = None
    endpoint: str | None = None
    total_layouts: int = 0
    fetched_layouts: int = 0
    resume_resubmit_reason: str | None = None


class TranslationMeta(BaseModel):
    """翻译阶段计数。skipped 与 translated 分开。"""

    status: str = "idle"
    model_name: str | None = None
    backend: str | None = Field(default=None, description="openai")
    source_lang: str = "en"
    target_lang: str = "zh"
    domain: str = "academic_paper"
    originally_pending: int = 0
    translated: int = 0
    skipped: int = 0
    agent_skipped: int = 0
    failed: int = 0
    pending: int = 0
    edited: int = 0


class Document(BaseModel):
    """一篇论文的结构化文档。pairs 顺序即翻译游标。"""

    schema_version: str = SCHEMA_VERSION
    job_id: str
    source_pdf_name: str
    pairs: list[TranslationPair] = Field(default_factory=list)
    glossary: list[GlossaryEntry] = Field(default_factory=list)
    outline: list[OutlineEntry] = Field(default_factory=list)
    parse: ParseMeta = Field(default_factory=ParseMeta)
    translation: TranslationMeta = Field(default_factory=TranslationMeta)
    created_at: str = ""
    updated_at: str = ""


def utc_now_iso() -> str:
    """返回 UTC ISO8601 时间戳。"""

    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def refresh_translation_counts(document: Document) -> None:
    """按 pairs 重算 TranslationMeta 五态计数。"""

    meta = document.translation
    meta.translated = 0
    meta.skipped = 0
    meta.failed = 0
    meta.pending = 0
    meta.edited = 0
    for pair in document.pairs:
        status = pair.target.status
        if status == BlockStatus.translated:
            meta.translated += 1
        elif status == BlockStatus.skipped:
            meta.skipped += 1
        elif status == BlockStatus.failed:
            meta.failed += 1
        elif status == BlockStatus.edited:
            meta.edited += 1
        else:
            meta.pending += 1
    document.updated_at = utc_now_iso()
