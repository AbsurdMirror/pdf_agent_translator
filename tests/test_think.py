# -*- coding: utf-8 -*-
from pdf_agent_translator.translate.think import strip_think


def test_strip_closed_think() -> None:
    assert strip_think("<think>reason</think>\n\nPONG") == "PONG"


def test_strip_only_think() -> None:
    assert strip_think("<think>reason</think>\n\n") == ""


def test_unclosed_think() -> None:
    assert strip_think("<think>incomplete") == ""
