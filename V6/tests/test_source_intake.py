"""Source intake probe (unit smoke)."""
from __future__ import annotations

import pytest

from src.services.source_intake import _guess_browser_search_url, _host


def test_guess_browser_search_url_cls() -> None:
    url = _guess_browser_search_url("https://www.cls.cn/telegraph", "cls.cn")
    assert url and "{query}" in url


def test_host_normalizes_www() -> None:
    assert _host("https://www.36kr.com/news") == "36kr.com"
