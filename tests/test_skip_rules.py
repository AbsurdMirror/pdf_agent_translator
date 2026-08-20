# -*- coding: utf-8 -*-
from pdf_agent_translator.parse.skip_rules import skip_reason_for


def test_skip_figure_type() -> None:
    assert skip_reason_for("figure", "hello") == "deterministic:type:figure"


def test_skip_empty() -> None:
    assert skip_reason_for("text", "   ") == "deterministic:empty"


def test_skip_image_only() -> None:
    assert skip_reason_for("text", "![x](http://a/b.png)") == "deterministic:image_only"


def test_keep_paragraph() -> None:
    assert skip_reason_for("text", "This is a real paragraph.") is None


def test_keep_table() -> None:
    assert skip_reason_for("table", "| a | b |\n| 1 | 2 |") is None
