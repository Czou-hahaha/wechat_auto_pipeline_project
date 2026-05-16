"""Tests for ``google_news_url`` (no network for passthrough)."""
from __future__ import annotations

from event_enhancement.google_news_url import decode_google_news_url


def test_decode_passthrough_non_google() -> None:
    u = "https://www.reuters.com/article/123"
    assert decode_google_news_url(u) == u


def test_decode_empty() -> None:
    assert decode_google_news_url("") == ""
    assert decode_google_news_url("   ") == ""


def test_strip_google_news_article_query() -> None:
    from event_enhancement.google_news_url import _strip_google_news_article_tracking

    u = "https://news.google.com/rss/articles/CBMiX?oc=5&hl=en-SG&ceid=SG:en"
    assert _strip_google_news_article_tracking(u) == "https://news.google.com/rss/articles/CBMiX"
