# -*- coding: utf-8 -*-
from pathlib import Path

from pdf_agent_translator.config import (
    find_project_root,
    iter_config_files,
    lang_display,
    parse_simple_toml,
)


def test_parse_simple_toml(tmp_path: Path) -> None:
    path = tmp_path / "cfg.toml"
    path.write_text(
        """
# comment
[llm]
api_key = "sk-test"
model_name = MiniMax-M3  # trailing
empty = ""

[aliyun]
access_key_id = 'LTAI-demo'
""",
        encoding="utf-8",
    )
    parsed = parse_simple_toml(path)
    assert parsed["llm"]["api_key"] == "sk-test"
    assert parsed["llm"]["model_name"] == "MiniMax-M3"
    assert parsed["llm"]["empty"] == ""
    assert parsed["aliyun"]["access_key_id"] == "LTAI-demo"


def test_config_candidates_exclude_workspace_probe(tmp_path: Path) -> None:
    home = tmp_path / "home"
    project = tmp_path / "proj"
    cwd = tmp_path / "cwd"
    extra = tmp_path / "explicit.toml"
    paths = iter_config_files(project_root=project, cwd=cwd, home=home, extra=extra)
    joined = "\n".join(p.as_posix() for p in paths)
    assert "key_probe" not in joined
    assert "secrets.toml" not in joined
    assert paths[0] == home / ".pdf_agent_translator" / "config.toml"
    assert paths[1] == project / "config.toml"
    assert paths[2] == cwd / "pdf_agent_translator.toml"
    assert paths[-1] == extra


def test_lang_display() -> None:
    assert lang_display("zh") == "Chinese"
    assert lang_display("en") == "English"
    assert lang_display("xx") == "xx"


def test_project_root() -> None:
    root = find_project_root()
    assert (root / "pyproject.toml").is_file()
    assert 'name = "pdf_agent_translator"' in (root / "pyproject.toml").read_text(encoding="utf-8")
