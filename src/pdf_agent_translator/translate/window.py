# -*- coding: utf-8 -*-
"""翻译滑动窗口。

\\file 只保留最近 K 个成功译文，按 token 预算裁旧块。
"""

from __future__ import annotations


def estimate_tokens(text: str) -> int:
    """粗估 token：字符数 / 4。

    \\param text 任意文本。
    \\return 至少 1（非空时）。
    """

    if not text:
        return 0
    return max(1, len(text) // 4)


def trim_window_to_budget(
    window: list[tuple[str, str]],
    prompt: str,
    context_tokens: int,
    *,
    ratio: float = 0.7,
) -> None:
    """若 system+窗口+当前 prompt 超过预算，丢掉最旧窗口条目。

    \\param window 就地修改。
    \\param prompt 当前 user prompt。
    \\param context_tokens 模型窗口。
    \\param ratio 可用比例。
    """

    budget = int(context_tokens * ratio)
    while window:
        used = estimate_tokens(prompt) + sum(estimate_tokens(a) + estimate_tokens(b) for a, b in window)
        if used <= budget:
            return
        window.pop(0)
