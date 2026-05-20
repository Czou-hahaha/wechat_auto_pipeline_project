"""GDELT 主题检索：英文串行、一词一请求。"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.config import Settings
from src.search import SearchHit, search_gdelt_topics_bilingual


def test_gdelt_english_one_term_per_request_no_chinese(monkeypatch: pytest.MonkeyPatch) -> None:
    asyncio.run(_run_gdelt_english_serial_test(monkeypatch))


async def _run_gdelt_english_serial_test(monkeypatch: pytest.MonkeyPatch) -> None:
    s = Settings()
    monkeypatch.setattr(s, "gdelt_chinese_enabled", False)
    monkeypatch.setattr(s, "gdelt_min_interval_sec", 1.0)
    monkeypatch.setattr(s, "parsed_gdelt_english_keywords", lambda: ["drone", "eVTOL"])
    monkeypatch.setattr(s, "parsed_chinese_keywords", lambda: ["低空经济"])
    calls: list[str] = []

    async def fake_gdelt(client, *, query, max_results, timespan, base_url, **kwargs):
        calls.append(query)
        return [
            SearchHit(
                title="t",
                url="https://example.com/a",
                snippet="",
                published_at="2026-05-17T12:00:00+00:00",
            )
        ]

    with patch("src.search.gdelt_doc_search_with_client", new=AsyncMock(side_effect=fake_gdelt)):
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client_cls.return_value.__aenter__.return_value = MagicMock()
            rows, http_n = await search_gdelt_topics_bilingual(s)

    assert http_n == 2
    assert len(rows) >= 1
    assert len(calls) == 2
    assert "低空" not in " ".join(calls)
    assert all(" OR " not in c for c in calls)
