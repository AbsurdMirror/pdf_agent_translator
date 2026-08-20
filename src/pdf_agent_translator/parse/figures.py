# -*- coding: utf-8 -*-
"""把远程图片下到 figures/ 并改写 markdown。

\\file 文件名用 id+url hash，避免空 alt 碰撞。
"""

from __future__ import annotations

import hashlib
import logging
import mimetypes
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests

logger = logging.getLogger(__name__)

# 只匹配 ASCII 括号，不用全角。
MD_IMAGE_RE = re.compile(r"!\[([^\]]*?)\]\((https?://[^)]+)\)")
HTML_IMAGE_RE = re.compile(r'(<img\b[^>]*\bsrc=["\'])(https?://[^"\']+)(["\'])', re.IGNORECASE)


def _ext_from(url: str, content_type: str | None) -> str:
    """从 URL 或 Content-Type 猜扩展名。

    \\return 带点的扩展名，默认 .png。
    """

    path = urlparse(url).path
    suffix = Path(path).suffix.lower()
    if suffix in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}:
        return suffix
    if content_type:
        guessed = mimetypes.guess_extension(content_type.split(";")[0].strip())
        if guessed:
            return guessed
    return ".png"


def _safe_id(unique_id: str | None, index: int) -> str:
    """文件名前缀。"""

    raw = (unique_id or "").strip() or f"b{index:04d}"
    return re.sub(r"[^A-Za-z0-9._-]+", "_", raw)[:80]


def localize_markdown_images(
    markdown: str,
    *,
    unique_id: str | None,
    index: int,
    figures_dir: Path,
    extra: dict[str, Any],
) -> str:
    """下载 markdown 中的 http(s) 图，改成 figures/ 相对路径。

    \\param markdown 原文。
    \\param unique_id Aliyun uniqueId。
    \\param index 文档序。
    \\param figures_dir 输出目录。
    \\param extra 失败时写入 figure_download_error。
    \\return 改写后的 markdown。
    """

    figures_dir.mkdir(parents=True, exist_ok=True)
    errors: list[str] = []

    def replace_url(url: str) -> str:
        digest = hashlib.sha1(url.encode("utf-8")).hexdigest()[:8]
        try:
            session = requests.Session()
            session.trust_env = False
            response = session.get(url, timeout=30)
            response.raise_for_status()
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{url}: {exc}")
            return url
        ext = _ext_from(url, response.headers.get("Content-Type"))
        name = f"{_safe_id(unique_id, index)}_{digest}{ext}"
        dest = figures_dir / name
        dest.write_bytes(response.content)
        return f"figures/{name}"

    def md_sub(match: re.Match[str]) -> str:
        alt, url = match.group(1), match.group(2)
        return f"![{alt}]({replace_url(url)})"

    def html_sub(match: re.Match[str]) -> str:
        return f"{match.group(1)}{replace_url(match.group(2))}{match.group(3)}"

    rewritten = MD_IMAGE_RE.sub(md_sub, markdown or "")
    rewritten = HTML_IMAGE_RE.sub(html_sub, rewritten)
    if errors:
        extra["figure_download_error"] = "; ".join(errors)
        logger.warning("下载图片失败: %s", extra["figure_download_error"])
    return rewritten
