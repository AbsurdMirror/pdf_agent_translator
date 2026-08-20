# -*- coding: utf-8 -*-
"""OpenAI 兼容 Chat Completions。

\\file 用 requests 直连，避免本机 SOCKS 代理把 openai/httpx 卡死。
"""

from __future__ import annotations

import logging
from collections.abc import Callable

import requests

from pdf_agent_translator.config import LlmSettings, lang_display
from pdf_agent_translator.models import BlockStatus
from pdf_agent_translator.translate.prompts import SYSTEM_PROMPT, build_block_prompt
from pdf_agent_translator.translate.store import BlockStore
from pdf_agent_translator.translate.think import strip_think
from pdf_agent_translator.translate.window import trim_window_to_budget

logger = logging.getLogger(__name__)


def _chat_url(base_url: str) -> str:
    """拼出 /chat/completions。"""

    root = base_url.rstrip("/")
    if root.endswith("/chat/completions"):
        return root
    if root.endswith("/v1"):
        return f"{root}/chat/completions"
    return f"{root}/v1/chat/completions"


def complete_chat(settings: LlmSettings, system: str, user: str) -> str:
    """一次 Chat Completions，默认关掉 MiniMax 思考。

    \\param settings 含 key / url / model。
    \\param system 系统提示。
    \\param user 用户提示。
    \\return 剥 think 后的正文。
    \\throws RuntimeError HTTP 或空正文。
    """

    url = _chat_url(settings.base_url)
    payload = {
        "model": settings.model_name,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "max_tokens": settings.max_output_tokens,
        "temperature": 0,
        "thinking": {"type": "disabled"},
    }
    headers = {
        "Authorization": f"Bearer {settings.api_key}",
        "Content-Type": "application/json",
    }
    # 本机若配了 SOCKS 代理，requests 会去找 socksio 然后炸。
    # trust_env=False 忽略 HTTP(S)_PROXY / ALL_PROXY，直连 MiniMax。
    session = requests.Session()
    session.trust_env = False
    response = session.post(
        url,
        headers=headers,
        json=payload,
        timeout=settings.request_timeout_seconds,
    )
    if response.status_code >= 400:
        raise RuntimeError(f"HTTP {response.status_code}: {response.text[:300]}")
    body = response.json()
    choices = body.get("choices") or []
    raw = ""
    if choices:
        raw = (choices[0].get("message") or {}).get("content") or ""
    text = strip_think(raw)
    if not text:
        raise RuntimeError("模型返回空正文（可能只有思考）")
    return text


def translate_with_openai(
    store: BlockStore,
    settings: LlmSettings,
    *,
    window_k: int,
    source_lang: str,
    target_lang: str,
    stop_on_error: bool,
    on_progress: Callable[[int, int, str], None] | None = None,
) -> str:
    """按序逐块翻译。

    \\return ``openai``。
    """

    src = lang_display(source_lang)
    tgt = lang_display(target_lang)
    system = SYSTEM_PROMPT.format(src=src, tgt=tgt)
    window: list[tuple[str, str]] = []
    total = len(store.document.pairs)

    for idx, pair in enumerate(store.document.pairs):
        if store.is_cancelled():
            break
        if pair.target.status in {BlockStatus.translated, BlockStatus.skipped, BlockStatus.edited}:
            if pair.target.status == BlockStatus.translated:
                window.append((pair.source.markdown, pair.target.markdown))
                window[:] = window[-window_k:]
            if on_progress:
                on_progress(idx, total, pair.target.status.value)
            continue

        prompt = build_block_prompt(
            pair=pair,
            window=window,
            glossary=store.document.glossary,
            src=src,
            tgt=tgt,
        )
        trim_window_to_budget(window, prompt, settings.context_tokens)
        try:
            text = complete_chat(settings, system, prompt)
            store.submit_translation(pair.source.block_id, text, model_name=settings.model_name)
            window.append((pair.source.markdown, text))
            window[:] = window[-window_k:]
        except Exception as exc:  # noqa: BLE001
            store.mark_failed(pair.source.block_id, str(exc))
            if stop_on_error or store.strict:
                break
        if on_progress:
            on_progress(idx, total, pair.target.status.value)

    store.document.translation.backend = "openai"
    store.document.translation.model_name = settings.model_name
    store.document.translation.status = "success"
    store.persist()
    return "openai"
