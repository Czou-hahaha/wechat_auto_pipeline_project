from __future__ import annotations

from src.utils.headline_zh import (
    is_overlong_zh_headline,
    trim_zh_headline_heuristic,
    zh_visible_len,
)


def test_trim_long_title_at_comma() -> None:
    long = (
        "日本无人机制造商ACSL与加拿大企业Draganfly达成独家经销协议，"
        "计划于2026年6月起在加拿大市场推出其SOTEN无人机"
    )
    assert is_overlong_zh_headline(long)
    short = trim_zh_headline_heuristic(long, max_len=28)
    assert zh_visible_len(short) <= 28
    assert "ACSL" in short or "Draganfly" in short or "日本" in short
