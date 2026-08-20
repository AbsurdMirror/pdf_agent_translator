# -*- coding: utf-8 -*-
"""定位只读依赖 qiufeng-agent-os。

\\file 不以 cwd、不以模块相对 ../../ 为准。
"""

from __future__ import annotations

import os
from pathlib import Path


def find_project_root(start: Path | None = None) -> Path:
    """从某文件向上找到本项目根（含 name=pdf_agent_translator 的 pyproject）。

    \\param start 起点，默认本文件。
    \\return project_root。
    \\throws FileNotFoundError 找不到。
    """

    cursor = (start or Path(__file__)).resolve()
    if cursor.is_file():
        cursor = cursor.parent
    for folder in [cursor, *cursor.parents]:
        pyproject = folder / "pyproject.toml"
        if not pyproject.is_file():
            continue
        text = pyproject.read_text(encoding="utf-8")
        if 'name = "pdf_agent_translator"' in text:
            return folder
    raise FileNotFoundError("找不到 pdf_agent_translator 的 pyproject.toml")


def looks_like_qfaos(root: Path) -> bool:
    """目录是否像 qfaos 仓库根。

    \\param root 候选路径。
    \\return 存在 src/qfaos/qfaos.py。
    """

    return (root / "src" / "qfaos" / "qfaos.py").is_file()


def resolve_qfaos_root(*, configured: str = "", cwd: Path | None = None) -> Path:
    """按设计顺序解析 qfaos 根目录。

    \\brief QFAOS_ROOT → settings.qfaos.root（相对 cwd）→ <project_root>/../qiufeng-agent-os
    \\param configured toml 里的 root。
    \\param cwd 解析相对路径的基准，默认进程 cwd。
    \\return 绝对路径。
    \\throws FileNotFoundError 列出全部尝试过的路径。
    """

    tried: list[str] = []
    env_root = os.environ.get("QFAOS_ROOT", "").strip()
    if env_root:
        path = Path(env_root).expanduser().resolve()
        tried.append(f"QFAOS_ROOT={path}")
        if looks_like_qfaos(path):
            return path

    if configured.strip():
        raw = Path(configured.strip()).expanduser()
        path = raw.resolve() if raw.is_absolute() else ((cwd or Path.cwd()) / raw).resolve()
        tried.append(f"settings.qfaos.root={path}")
        if looks_like_qfaos(path):
            return path

    sibling = (find_project_root() / ".." / "qiufeng-agent-os").resolve()
    tried.append(f"sibling={sibling}")
    if looks_like_qfaos(sibling):
        return sibling

    raise FileNotFoundError("找不到 qiufeng-agent-os，已尝试: " + " | ".join(tried))
