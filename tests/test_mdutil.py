# -*- coding: utf-8 -*-
from pdf_agent_translator.render.mdutil import (
    apply_heading_level,
    fix_broken_fences,
    gfm_table_to_html,
    guess_heading_level,
    looks_like_code,
    polish_block_markdown,
    wrap_as_code,
)


def test_table_renders_html() -> None:
    md = "| a | b |\n| --- | --- |\n| 1 | 2 |\n"
    html = gfm_table_to_html(md)
    assert html is not None
    assert "<table>" in html
    assert "<th>a</th>" in html
    assert "<td>1</td>" in html


def test_aliyun_tight_table() -> None:
    md = "| SM Resources|SM Resources|\n| ---|---|\n| SPs|8 per SM|\n"
    html = gfm_table_to_html(md)
    assert html is not None
    assert "<table>" in html


def test_heading_levels() -> None:
    assert guess_heading_level("# Paper Title", block_type="title", index=0) == 1
    assert guess_heading_level("# I. INTRODUCTION", block_type="title", index=3) == 2
    assert guess_heading_level("# A. GPU Architecture", block_type="title", index=20) == 3
    assert guess_heading_level("# REFERENCES", block_type="title", index=200) == 2
    assert apply_heading_level("# A. GPU", 3).startswith("### A. GPU")


def test_latex_cache_size_formula() -> None:
    from pdf_agent_translator.render.mdutil import latex_inner_to_html

    html = latex_inner_to_html(r"cache\_size = cache\_sets \times line\_size \times associativity")
    assert "cache_size" in html
    assert "×" in html
    assert "\\times" not in html
    assert "\\_" not in html


def test_broken_fence_and_bare_code() -> None:
    assert "```c" in fix_broken_fences("``c\nint x;\n```")
    raw = "for (i = 0; i < n; i++) {\n  int t = i;\n}\n"
    assert looks_like_code(raw)
    assert polish_block_markdown(raw).startswith("```c")
    assert wrap_as_code("int x;", "c").startswith("```c")
