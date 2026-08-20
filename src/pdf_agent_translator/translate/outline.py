# -*- coding: utf-8 -*-
"""标题等级整理：先启发式，再用 MiniMax 优化目录。

\\file 只改 title 块的 # 级数和 Document.outline，不重译正文。
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from pdf_agent_translator.config import LlmSettings
from pdf_agent_translator.models import Document, OutlineEntry
from pdf_agent_translator.render.mdutil import (
    apply_heading_level,
    guess_heading_level,
    strip_heading_marks,
)
from pdf_agent_translator.translate.openai_backend import complete_chat
from pdf_agent_translator.translate.think import strip_think

logger = logging.getLogger(__name__)

_OUTLINE_PROMPT = """You organize academic paper headings into a hierarchy.
Given a JSON list of headings in document order, assign heading level 1-4:
- 1 = paper title (usually only the first item)
- 2 = major section (I. II. III. INTRODUCTION, RELATED WORK, REFERENCES, 参考文献)
- 3 = subsection (A. B. C. or 1.1)
- 4 = sub-subsection
Keep Roman I/II and letter A/B numbering in the title text.
Return ONLY a JSON array: [{{"block_id":"...","level":2,"title":"译文标题"}}]
Do not invent headings. Use every input block_id exactly once.
Input:
{payload}
"""


def collect_title_candidates(document: Document) -> list[dict[str, Any]]:
    """挑出需要进目录的块。"""

    items: list[dict[str, Any]] = []
    for idx, pair in enumerate(document.pairs):
        if pair.source.type != "title":
            continue
        src = strip_heading_marks(pair.source.markdown)
        tgt = strip_heading_marks(pair.target.markdown or pair.source.markdown)
        guessed = guess_heading_level(pair.source.markdown, block_type=pair.source.type, index=idx) or 2
        items.append(
            {
                "block_id": pair.source.block_id,
                "index": idx,
                "type": pair.source.type,
                "source_title": src,
                "title": tgt or src,
                "guessed_level": guessed,
            }
        )
    return items


def apply_outline(document: Document, entries: list[OutlineEntry]) -> None:
    """按目录回写 pairs 的标题 markdown，并挂到 document.outline。"""

    by_id = {e.block_id: e for e in entries}
    outline: list[OutlineEntry] = []
    for idx, pair in enumerate(document.pairs):
        entry = by_id.get(pair.source.block_id)
        if entry is None:
            continue
        pair.source.markdown = apply_heading_level(pair.source.markdown, entry.level)
        if pair.target.markdown.strip():
            pair.target.markdown = apply_heading_level(pair.target.markdown, entry.level)
        entry.pair_index = idx
        entry.source_title = strip_heading_marks(pair.source.markdown)
        entry.title = strip_heading_marks(pair.target.markdown or pair.source.markdown)
        outline.append(entry)
    document.outline = outline


def heuristic_outline(document: Document) -> list[OutlineEntry]:
    """不联网时的目录。"""

    items = collect_title_candidates(document)
    return [
        OutlineEntry(
            block_id=item["block_id"],
            level=int(item["guessed_level"]),
            title=item["title"],
            source_title=item["source_title"],
            pair_index=int(item["index"]),
        )
        for item in items
    ]


def _parse_model_outline(text: str, fallback: list[OutlineEntry]) -> list[OutlineEntry]:
    """解析模型 JSON，缺项用启发式补。"""

    raw = strip_think(text)
    match = re.search(r"\[.*\]", raw, re.S)
    if not match:
        logger.warning("目录模型未返回 JSON 数组，用启发式")
        return fallback
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        logger.warning("目录 JSON 解析失败，用启发式")
        return fallback
    fb_map = {e.block_id: e for e in fallback}
    out: list[OutlineEntry] = []
    seen: set[str] = set()
    if not isinstance(data, list):
        return fallback
    for row in data:
        if not isinstance(row, dict):
            continue
        bid = str(row.get("block_id") or "")
        if bid not in fb_map or bid in seen:
            continue
        level = int(row.get("level") or fb_map[bid].level)
        level = max(1, min(4, level))
        title = str(row.get("title") or fb_map[bid].title)
        base = fb_map[bid]
        out.append(
            OutlineEntry(
                block_id=bid,
                level=level,
                title=title,
                source_title=base.source_title,
                pair_index=base.pair_index,
            )
        )
        seen.add(bid)
    for extra in fallback:
        if extra.block_id not in seen:
            out.append(extra)
    out.sort(key=lambda e: e.pair_index)
    return out


def refine_outline_with_llm(document: Document, settings: LlmSettings) -> list[OutlineEntry]:
    """启发式打底，再请模型校正等级。"""

    fallback = heuristic_outline(document)
    if not fallback:
        return []
    payload = json.dumps(
        [
            {
                "block_id": e.block_id,
                "source_title": e.source_title,
                "title": e.title,
                "guessed_level": e.level,
            }
            for e in fallback
        ],
        ensure_ascii=False,
    )
    try:
        reply = complete_chat(
            settings,
            "You only output JSON.",
            _OUTLINE_PROMPT.format(payload=payload),
        )
        return _parse_model_outline(reply, fallback)
    except Exception as exc:  # noqa: BLE001
        logger.warning("目录模型调用失败，用启发式: %s", exc)
        return fallback
