# -*- coding: utf-8 -*-
from pdf_agent_translator.translate.window import trim_window_to_budget


def test_trim_drops_oldest() -> None:
    window = [("src" * 200, "tgt" * 200), ("short", "短")]
    trim_window_to_budget(window, "p" * 20, context_tokens=80, ratio=0.7)
    assert window
    assert window[0] == ("short", "短") or len(window) == 1
