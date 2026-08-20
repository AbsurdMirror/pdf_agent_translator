# -*- coding: utf-8 -*-
"""解析 → 翻译 → 渲染 流水线。

\\file CLI 与 GUI 共用；一把 cancel_event。
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import yaml

from pdf_agent_translator.config import Settings, load_settings
from pdf_agent_translator.models import BlockStatus, Document, JobPhase, refresh_translation_counts
from pdf_agent_translator.parse.aliyun_docmind import AliyunDocMindParser, build_document
from pdf_agent_translator.persist.job import (
    Job,
    dump_job_toml,
    load_document,
    load_job_toml,
    prepare_out_dir,
    save_document,
)
from pdf_agent_translator.render.html import html_newer_than_json, render_html
from pdf_agent_translator.translate.agent import run_translation
from pdf_agent_translator.translate.store import BlockStore

logger = logging.getLogger(__name__)


@dataclass
class Progress:
    """进度回调载荷。"""

    stage: str
    percent: int
    message: str
    counts: dict[str, int]


@dataclass
class RunRequest:
    """一次 pipeline 调用。"""

    pdf_path: Path | None
    out_dir: Path
    source_lang: str = "en"
    target_lang: str = "zh"
    resume: bool = False
    retranslate: bool = False
    retranslate_failed: bool = False
    write_yaml: bool = False
    strict: bool = False
    force_render: bool = False
    config_path: Path | None = None
    cancel_event: threading.Event | None = None
    parse_only: bool = False
    translate_only: bool = False
    render_only: bool = False
    polish: bool = False


class Pipeline:
    """端到端编排。"""

    def __init__(
        self,
        settings: Settings,
        on_progress: Callable[[Progress], None] | None = None,
    ) -> None:
        self.settings = settings
        self.on_progress = on_progress

    def _emit(self, stage: str, percent: int, message: str, document: Document | None = None) -> None:
        counts = {"translated": 0, "skipped": 0, "failed": 0, "pending": 0, "edited": 0}
        if document is not None:
            refresh_translation_counts(document)
            counts = {
                "translated": document.translation.translated,
                "skipped": document.translation.skipped,
                "failed": document.translation.failed,
                "pending": document.translation.pending,
                "edited": document.translation.edited,
            }
        if self.on_progress:
            self.on_progress(Progress(stage, percent, message, counts))
        logger.info("[%s %s%%] %s", stage, percent, message)

    def run(self, req: RunRequest) -> Job:
        """跑完整或分段流水线。

        \\param req 请求。
        \\return 结束后的 Job。
        """

        cancel = req.cancel_event or threading.Event()
        if req.pdf_path is None and not (req.translate_only or req.render_only or req.polish):
            raise ValueError("需要 pdf_path")
        if req.pdf_path is not None:
            job = prepare_out_dir(req.pdf_path, req.out_dir, resume=req.resume)
        else:
            job = load_job_toml(req.out_dir)

        if req.polish and not req.translate_only:
            self._polish(job, req)
            self._render(job, req)
            return job

        if not req.translate_only and not req.render_only:
            self._parse(job, req, cancel)
        if req.parse_only:
            return job
        if not req.render_only:
            self._translate(job, req, cancel)
            self._polish(job, req)
        self._render(job, req)
        return job

    def _parse(self, job: Job, req: RunRequest, cancel: threading.Event) -> None:
        if req.resume and job.document_json.is_file():
            document = load_document(job.document_json)
            if document.parse.status == "success" and document.pairs:
                self._emit("parse", 100, "解析已完成，跳过", document)
                return

        if not self.settings.aliyun.access_key_id or not self.settings.aliyun.access_key_secret:
            raise RuntimeError("缺少阿里云 AK/SK")

        job.phase = JobPhase.parsing
        dump_job_toml(job)
        self._emit("parse", 1, "提交 DocMind")

        parser = AliyunDocMindParser(
            file_path=job.source_pdf,
            output_raw=job.parse_raw_json,
            figures_dir=job.figures_dir,
            access_key_id=self.settings.aliyun.access_key_id,
            access_key_secret=self.settings.aliyun.access_key_secret,
            endpoint=self.settings.aliyun.endpoint,
            cancel_event=cancel,
            on_update=lambda *_args: self._emit("parse", 30, f"DocMind {_args[2]}"),
        )
        layouts = parser.poll_until_done()
        document = build_document(
            job_id=job.job_id,
            source_pdf_name=job.source_pdf_name,
            layouts=layouts,
            figures_dir=job.figures_dir,
            endpoint=self.settings.aliyun.endpoint,
            docmind_job_id=parser.task_id,
            source_lang=req.source_lang,
            target_lang=req.target_lang,
        )
        refresh_translation_counts(document)
        save_document(job.document_json, document)
        if req.write_yaml or self.settings.translate.write_yaml:
            yaml_path = job.out_dir / "document.yaml"
            yaml_path.write_text(
                yaml.safe_dump(document.model_dump(mode="json"), allow_unicode=True, sort_keys=False),
                encoding="utf-8",
            )
        job.phase = JobPhase.parsed
        dump_job_toml(job)
        self._emit("parse", 100, f"解析完成 {len(layouts)} 块", document)

    def _reset_for_retranslate(self, document: Document, req: RunRequest) -> None:
        for pair in document.pairs:
            if pair.target.skip_kind == "deterministic":
                continue
            if req.retranslate:
                pair.target.status = BlockStatus.pending
                pair.target.markdown = ""
                pair.target.error = None
            elif req.retranslate_failed and pair.target.status == BlockStatus.failed:
                pair.target.status = BlockStatus.pending
                pair.target.error = None

    def _translate(self, job: Job, req: RunRequest, cancel: threading.Event) -> None:
        if not job.document_json.is_file():
            raise FileNotFoundError("没有 document.json，先解析")
        document = load_document(job.document_json)
        if req.retranslate or req.retranslate_failed:
            self._reset_for_retranslate(document, req)
            save_document(job.document_json, document)

        unfinished = any(p.target.status in {BlockStatus.pending, BlockStatus.failed} for p in document.pairs)
        if not unfinished:
            job.phase = JobPhase.translated
            dump_job_toml(job)
            self._emit("translate", 100, "没有未完成块", document)
            return

        if not self.settings.llm.api_key:
            raise RuntimeError("缺少 LLM api_key")

        job.phase = JobPhase.translating
        dump_job_toml(job)
        store = BlockStore(job.document_json, cancel, strict=req.strict)
        total = max(1, len(store.document.pairs))

        def on_item(idx: int, _total: int, status: str) -> None:
            self._emit("translate", int((idx + 1) / total * 100), f"{idx + 1}/{total} {status}", store.document)

        backend = run_translation(store, self.settings, on_progress=on_item)
        refresh_translation_counts(store.document)
        save_document(job.document_json, store.document)
        leftover = store.first_unfinished_index() is not None
        if req.strict and leftover:
            job.phase = JobPhase.failed
            job.error = "strict: 仍有 pending/failed"
            dump_job_toml(job)
            self._emit("translate", 100, job.error, store.document)
            return
        job.phase = JobPhase.translated
        job.error = ""
        dump_job_toml(job)
        self._emit("translate", 100, f"翻译结束 backend={backend}", store.document)

    def _polish(self, job: Job, req: RunRequest) -> None:
        """修补围栏/表格，并让模型整理标题目录。"""

        from pdf_agent_translator.translate.polish import polish_document

        if not job.document_json.is_file():
            raise FileNotFoundError("没有 document.json，无法整理")
        self._emit("polish", 10, "整理标题目录与 Markdown")
        document = load_document(job.document_json)
        polish_document(document, self.settings)
        save_document(job.document_json, document)
        req.force_render = True
        self._emit("polish", 100, f"目录 {len(document.outline)} 项", document)

    def _render(self, job: Job, req: RunRequest) -> None:
        if not job.document_json.is_file():
            raise FileNotFoundError("没有 document.json")
        if html_newer_than_json(job.html_path, job.document_json) and not req.force_render:
            raise RuntimeError("document.html 比 JSON 新，拒绝覆盖。加 --force 或先下载 JSON")
        document = load_document(job.document_json)
        render_html(document, job.html_path)
        job.phase = JobPhase.rendered
        dump_job_toml(job)
        self._emit("render", 100, str(job.html_path), document)


def build_pipeline(config_path: Path | None, on_progress=None) -> Pipeline:
    """从磁盘配置构造 Pipeline。"""

    return Pipeline(load_settings(config_path), on_progress=on_progress)
