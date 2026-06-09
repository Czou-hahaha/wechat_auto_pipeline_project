"""Tests for trafilatura-backed main text extraction."""
from __future__ import annotations

import unittest

from src.utils.article_extract import extract_main_text_trafilatura, main_text_with_trafilatura_fallback


class ArticleExtractTests(unittest.TestCase):
    def test_trafilatura_returns_substantial_text(self) -> None:
        html = """<!DOCTYPE html><html><body><article>
        <h1>Drone rule change</h1>
        <p>""" + ("The FAA published new guidance for commercial operators. " * 20) + """</p>
        </article></body></html>"""
        out = extract_main_text_trafilatura(html, page_url="https://example.com/news/1", min_chars=120)
        self.assertIsNotNone(out)
        assert out is not None
        self.assertGreater(len(out), 120)

    def test_fallback_when_disabled(self) -> None:
        def fb() -> str:
            return "legacy body"

        got = main_text_with_trafilatura_fallback(
            "<html><body></body></html>",
            page_url="https://x.test/",
            min_chars=200,
            trafilatura_enabled=False,
            fallback=fb,
        )
        self.assertEqual(got, "legacy body")


if __name__ == "__main__":
    unittest.main()
