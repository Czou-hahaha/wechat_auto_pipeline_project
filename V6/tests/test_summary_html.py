"""摘要 HTML 高亮与口径不一致清理。"""
from __future__ import annotations

from src.utils.summary_html import (
    sanitize_summary_text,
    strip_ui_citation_markers,
    summary_plain_for_digest,
    summary_to_wechat_html_body,
    summary_visible_char_count,
)


def test_strong_tag_preserved_in_wechat_html() -> None:
    s = "普通句。<strong>2026年监管框架将落地。</strong>结尾。"
    html = summary_to_wechat_html_body(s)
    assert "<strong>2026年监管框架将落地。</strong>" in html
    assert "**" not in html


def test_removes_inconsistency_phrase() -> None:
    s = "正文开始。报道口径不一致，A媒与B媒说法不同。后续内容。"
    out = sanitize_summary_text(s)
    assert "口径不一致" not in out
    assert "后续内容" in out


def test_strip_ui_citation_markers() -> None:
    s = "第一段正文。〔2〕第二段。【1】结尾。"
    assert strip_ui_citation_markers(s) == "第一段正文。第二段。结尾。"
    assert "〔" not in summary_plain_for_digest(s)


def test_digest_strips_tags() -> None:
    s = "<strong>重点数据句。</strong>"
    assert "重点数据句" in summary_plain_for_digest(s)
    assert "<strong>" not in summary_plain_for_digest(s)


def test_visible_char_count_ignores_tags_and_whitespace() -> None:
    s = "  前段。<strong>后段重点。</strong>\n\n  尾段。  "
    assert summary_visible_char_count(s) == len("前段。后段重点。尾段。")


def test_pipeline_summary_too_short_gate() -> None:
    from src.pipeline import PipelineRunner

    short = "短摘要。" * 50  # <800 visible chars
    assert PipelineRunner._is_summary_too_short(short, min_chars=800)
    long = "长摘要。" * 200
    assert not PipelineRunner._is_summary_too_short(long, min_chars=800)
