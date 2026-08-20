# -*- coding: utf-8 -*-
"""经 qfaos Python 渠道按序 model_ask。

\\file 不改 qfaos；关不了思考，调用后剥 <think>。
"""

from __future__ import annotations

import logging
import sys
import threading
import time
from collections.abc import Callable
from pathlib import Path

from pdf_agent_translator.config import LlmSettings, QfaosSettings, lang_display
from pdf_agent_translator.models import BlockStatus
from pdf_agent_translator.qfaos_path import resolve_qfaos_root
from pdf_agent_translator.translate.prompts import SYSTEM_PROMPT, build_block_prompt
from pdf_agent_translator.translate.store import BlockStore
from pdf_agent_translator.translate.think import strip_think
from pdf_agent_translator.translate.window import trim_window_to_budget

logger = logging.getLogger(__name__)


class QfaosUnavailable(RuntimeError):
    """qfaos 无法启动或握手失败，应改走 OpenAI 兜底。"""


def _wait_channel(agent: object, timeout_s: float = 5.0) -> None:
    """轮询 DirectChannel._on_event，禁止 sleep(1)。"""

    from src.channel_gateway.channels.python.direct import DirectChannel

    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        channel = agent.channel_gateway.channel  # type: ignore[attr-defined]
        if isinstance(channel, DirectChannel) and channel._on_event is not None:
            return
        time.sleep(0.02)
    raise QfaosUnavailable("DirectChannel 握手超时")


def translate_with_qfaos(
    store: BlockStore,
    settings: LlmSettings,
    qfaos_settings: QfaosSettings,
    *,
    window_k: int,
    source_lang: str,
    target_lang: str,
    stop_on_error: bool,
    log_dir: Path,
    on_progress: Callable[[int, int, str], None] | None = None,
) -> str:
    """启动 QFAOS，send_req 触发按序循环。

    \\return ``qfaos``。
    \\throws QfaosUnavailable 导入/握手/零推进失败。
    """

    try:
        root = resolve_qfaos_root(configured=qfaos_settings.root)
    except FileNotFoundError as exc:
        raise QfaosUnavailable(str(exc)) from exc
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    try:
        from src.qfaos import QFAOS
        import src.qfaos.config as Config
        from src.channel_gateway.channels.python.direct import DirectChannel
        from src.domain.orchestration import ExecutionEvent
        from src.orchestration_engine.context.execution_context import ExecutionContext
    except Exception as exc:  # noqa: BLE001
        # 常见：Python<3.12 没有 typing.override，qfaos 直接 import 失败。
        raise QfaosUnavailable(f"导入 qfaos 失败 (py={sys.version.split()[0]}): {exc}") from exc

    src = lang_display(source_lang)
    tgt = lang_display(target_lang)
    model_name = settings.model_name
    progressed_before = store.document.translation.translated

    client_cfg = Config.model.litellm.Custom(
        model_name=model_name,
        api_key=settings.api_key,
        base_url=settings.base_url,
        max_tokens=settings.context_tokens,
        cfg=Config.model.litellm.LitellmCustomConfig(
            max_tokens=settings.max_output_tokens,
            max_retries=0,
            temperature=0.0,
        ),
    )
    log_dir.mkdir(parents=True, exist_ok=True)
    agent = QFAOS(
        Config.QFAConfig(
            channel=Config.channel.Python(
                default_user_id="pdf-translate",
                default_conversation_id=store.document.job_id,
            ),
            model=Config.model.LitellmProvider(clients=[client_cfg]),
            memory=Config.memory.Memory(backend=Config.memory.Backend.InMemory),
            observability=Config.observability.Jsonl(log_dir=str(log_dir)),
            tools=Config.tools.Pytool(enable=True),
        )
    )

    @agent.custom_execute
    async def _execute(event: ExecutionEvent, ctx: ExecutionContext) -> None:
        # 必须与 SimpleOrchestrator.initialize_context 用同一对 logic_id/session_id。
        session = ctx.get_session_ctx(event.logic_id, event.session_id)
        try:
            await session.set_system_prompt(SYSTEM_PROMPT.format(src=src, tgt=tgt))
        except Exception:
            # 部分版本 set_system_prompt 签名不同，退化为每块 prompt 自带规则。
            logger.debug("set_system_prompt 不可用，规则写在 user prompt 里")

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
                result = await session.model_ask(
                    model_name=model_name,
                    prompt=prompt,
                    all_tools=False,
                    max_iterations=1,
                )
                raw = ""
                if result.success:
                    raw = result.response_text or result.content or ""
                text = strip_think(raw)
                if not result.success or not text:
                    raise RuntimeError(result.error_message or "empty/think-only content")
                store.submit_translation(pair.source.block_id, text, model_name=model_name)
                window.append((pair.source.markdown, text))
                window[:] = window[-window_k:]
            except Exception as exc:  # noqa: BLE001
                store.mark_failed(pair.source.block_id, str(exc))
                if stop_on_error or store.strict:
                    break
            finally:
                # 丢掉 message 历史，保留 system。禁止 clear_history()。
                try:
                    mem = session.runtime_context.memory
                    mem.history_blocks.clear()
                    mem.new_blocks.clear()
                except Exception:
                    pass
            if on_progress:
                on_progress(idx, total, pair.target.status.value)

        _ = await session.send_message(Config.channel.Channel.Python, store.summary_text())

    _ = _execute
    worker = threading.Thread(target=agent.run, name="qfaos-translate", daemon=True)
    worker.start()
    try:
        _wait_channel(agent)
        replies = agent.send_req(f"Translate job {store.document.job_id}")
        logger.info("qfaos send_req replies=%s", replies)
    except QfaosUnavailable:
        raise
    except Exception as exc:  # noqa: BLE001
        raise QfaosUnavailable(f"send_req 失败: {exc}") from exc
    finally:
        channel = agent.channel_gateway.channel
        if isinstance(channel, DirectChannel):
            channel.stop()
        worker.join(timeout=3)

    store.persist()
    advanced = store.document.translation.translated > progressed_before
    if not advanced and store.first_unfinished_index() is not None:
        raise QfaosUnavailable("qfaos 未推进任何块")
    store.document.translation.backend = "qfaos"
    store.document.translation.model_name = model_name
    store.persist()
    return "qfaos"
