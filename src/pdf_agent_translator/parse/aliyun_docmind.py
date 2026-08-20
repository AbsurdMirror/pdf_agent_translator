# -*- coding: utf-8 -*-
"""阿里云 DocMind 解析适配器。

\\file 复制 PDFParser 协议，不 import PDF_Translator.server。
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from pdf_agent_translator.models import (
    BlockStatus,
    Document,
    ParseMeta,
    SourceBlock,
    TargetBlock,
    TranslationPair,
    utc_now_iso,
)
from pdf_agent_translator.parse.figures import localize_markdown_images
from pdf_agent_translator.parse.skip_rules import skip_reason_for

logger = logging.getLogger(__name__)

OnUpdate = Callable[[str, str, str, float], None]
OnData = Callable[[str, list[dict[str, Any]]], None]


class AliyunDocMindParser:
    """提交 PDF、轮询状态、增量拉 layouts。

    \\brief SubmitDocParserJobAdvance + Query + Get，VLM 增强。
    """

    def __init__(
        self,
        *,
        file_path: Path,
        output_raw: Path,
        figures_dir: Path,
        access_key_id: str,
        access_key_secret: str,
        endpoint: str = "docmind-api.cn-hangzhou.aliyuncs.com",
        layout_step_size: int = 10,
        poll_interval: float = 5.0,
        cancel_event: threading.Event | None = None,
        on_update: OnUpdate | None = None,
        on_data: OnData | None = None,
    ) -> None:
        self.file_path = file_path
        self.output_raw = output_raw
        self.figures_dir = figures_dir
        self.access_key_id = access_key_id
        self.access_key_secret = access_key_secret
        self.endpoint = endpoint.replace("https://", "").replace("http://", "").rstrip("/")
        self.layout_step_size = layout_step_size
        self.poll_interval = poll_interval
        self.cancel_event = cancel_event or threading.Event()
        self.on_update = on_update
        self.on_data = on_data
        self.task_id: str | None = None
        self.task_status = "idle"
        self.total_layout_num = 0
        self.processed_layout_num = 0
        self.all_layouts: list[dict[str, Any]] = []
        self._client = None

    def _client_or_init(self) -> Any:
        """懒创建 DocMind 客户端。"""

        if self._client is not None:
            return self._client
        from alibabacloud_docmind_api20220711.client import Client as DocmindClient
        from alibabacloud_tea_openapi import models as open_api_models

        config = open_api_models.Config(endpoint=self.endpoint)
        config.access_key_id = self.access_key_id
        config.access_key_secret = self.access_key_secret
        config.type = "access_key"
        self._client = DocmindClient(config)
        return self._client

    def submit(self) -> str:
        """提交解析任务。

        \\return DocMind job id。
        \\throws RuntimeError 提交失败。
        """

        from alibabacloud_docmind_api20220711 import models as docmind_models
        from alibabacloud_tea_util import models as util_models

        file_name = self.file_path.name
        extension = file_name.rsplit(".", 1)[-1] if "." in file_name else None
        request = docmind_models.SubmitDocParserJobAdvanceRequest(
            file_url_object=open(self.file_path, "rb"),
            file_name=file_name,
            file_name_extension=extension,
            llm_enhancement=True,
            enhancement_mode="VLM",
        )
        response = self._client_or_init().submit_doc_parser_job_advance(request, util_models.RuntimeOptions())
        task_id = response.body.data.id
        if not task_id:
            raise RuntimeError("DocMind 提交成功但未返回 id")
        self.task_id = str(task_id)
        self.task_status = "init"
        logger.info("DocMind 已提交: %s", self.task_id)
        return self.task_id

    def _check_status(self) -> tuple[str, int, float]:
        """查询云端状态。"""

        from alibabacloud_docmind_api20220711 import models as docmind_models

        request = docmind_models.QueryDocParserStatusRequest(id=self.task_id)
        response = self._client_or_init().query_doc_parser_status(request)
        data = response.body.data
        status = data.status if data else "fail"
        num = getattr(data, "number_of_successful_parsing", 0) if data else 0
        processing = getattr(data, "processing", 0.0) if data else 0.0
        if status not in {"init", "processing", "success", "fail"}:
            status = "fail"
        return status, int(num or 0), float(processing or 0.0)

    def _get_result(self, start_num: int, step: int) -> list[dict[str, Any]]:
        """增量拉取 layouts。"""

        from alibabacloud_docmind_api20220711 import models as docmind_models

        request = docmind_models.GetDocParserResultRequest(
            id=self.task_id, layout_step_size=step, layout_num=start_num
        )
        response = self._client_or_init().get_doc_parser_result(request)
        data = response.body.data
        if not data:
            return []
        layouts = data["layouts"] if isinstance(data, dict) else getattr(data, "layouts", None)
        return list(layouts or [])

    def _persist_raw(self) -> None:
        """整文件重写 parse_raw.json。"""

        payload = {
            "task_id": self.task_id,
            "status": self.task_status,
            "layouts": self.all_layouts,
        }
        tmp = self.output_raw.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, self.output_raw)

    def poll_until_done(self) -> list[dict[str, Any]]:
        """轮询直到 success/fail/取消。

        \\return 全部 layouts。
        \\throws RuntimeError 云端 fail。
        """

        if not self.task_id:
            self.submit()
        while not self.cancel_event.is_set():
            status, num_ok, processing = self._check_status()
            old = self.task_status
            self.task_status = status
            if num_ok >= self.total_layout_num:
                self.total_layout_num = num_ok
            if self.on_update and (status != old or status == "processing"):
                self.on_update(self.task_id or "", old, status, processing)

            while self.processed_layout_num < self.total_layout_num:
                layouts = self._get_result(self.processed_layout_num, self.layout_step_size)
                if not layouts:
                    break
                self.processed_layout_num += len(layouts)
                self.all_layouts.extend(layouts)
                self._persist_raw()
                if self.on_data:
                    self.on_data(self.task_id or "", layouts)
                if len(layouts) < self.layout_step_size:
                    break

            if status == "success" and self.processed_layout_num >= self.total_layout_num:
                logger.info("DocMind 完成，%s 个 layout", self.processed_layout_num)
                return self.all_layouts
            if status == "fail":
                raise RuntimeError("DocMind 任务失败")
            self.cancel_event.wait(self.poll_interval)

        raise RuntimeError("解析被取消")


def layout_to_pair(layout: dict[str, Any], index: int, figures_dir: Path) -> TranslationPair:
    """把一个 Aliyun layout 映射成 TranslationPair。

    \\param layout 云端 dict。
    \\param index 文档序。
    \\param figures_dir 图片目录。
    \\return 已做确定性 skip 的 pair。
    """

    unique_id = layout.get("uniqueId") or layout.get("unique_id")
    block_id = str(unique_id).strip() if unique_id else f"b{index:04d}"
    markdown = layout.get("markdownContent") or layout.get("markdown_content") or ""
    extra = {
        key: value
        for key, value in layout.items()
        if key
        not in {
            "type",
            "subType",
            "pageNum",
            "index",
            "uniqueId",
            "markdownContent",
            "text",
            "alignment",
        }
    }
    markdown = localize_markdown_images(
        markdown,
        unique_id=str(unique_id) if unique_id else None,
        index=index,
        figures_dir=figures_dir,
        extra=extra,
    )
    source = SourceBlock(
        block_id=block_id,
        index=index,
        aliyun_index=layout.get("index"),
        page_num=layout.get("pageNum"),
        type=str(layout.get("type") or "text"),
        sub_type=layout.get("subType"),
        markdown=markdown,
        text=layout.get("text"),
        alignment=layout.get("alignment"),
        unique_id=str(unique_id) if unique_id else None,
        extra=extra,
    )
    target = TargetBlock()
    reason = skip_reason_for(source.type, source.markdown)
    if reason:
        # 预跳过：译文复制原文，但不算 translated。
        target.markdown = source.markdown
        target.status = BlockStatus.skipped
        target.skip_reason = reason
        target.skip_kind = "deterministic"
    return TranslationPair(source=source, target=target, display_order=index)


def build_document(
    *,
    job_id: str,
    source_pdf_name: str,
    layouts: list[dict[str, Any]],
    figures_dir: Path,
    endpoint: str,
    docmind_job_id: str | None,
    source_lang: str,
    target_lang: str,
) -> Document:
    """layouts → Document，并统计 originally_pending。

    \\return 新 Document。
    """

    pairs = [layout_to_pair(layout, idx, figures_dir) for idx, layout in enumerate(layouts)]
    now = utc_now_iso()
    document = Document(
        job_id=job_id,
        source_pdf_name=source_pdf_name,
        pairs=pairs,
        parse=ParseMeta(
            status="success",
            docmind_job_id=docmind_job_id,
            endpoint=endpoint,
            total_layouts=len(layouts),
            fetched_layouts=len(layouts),
        ),
        created_at=now,
        updated_at=now,
    )
    document.translation.source_lang = source_lang
    document.translation.target_lang = target_lang
    document.translation.originally_pending = sum(
        1 for pair in pairs if pair.target.status == BlockStatus.pending
    )
    return document
