# -*- coding: utf-8 -*-
import pytest

from pdf_agent_translator.qfaos_path import find_project_root, looks_like_qfaos, resolve_qfaos_root


def test_project_root() -> None:
    root = find_project_root()
    assert (root / "pyproject.toml").is_file()


def test_sibling_qfaos() -> None:
    try:
        qroot = resolve_qfaos_root()
    except FileNotFoundError:
        pytest.skip("本仓库独立发布时不附带 qiufeng-agent-os")
    assert looks_like_qfaos(qroot)
