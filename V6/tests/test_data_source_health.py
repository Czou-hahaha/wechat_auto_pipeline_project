"""数据源健康探测单测。"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from src.bff import data_source_health_store
from src.services.data_source_health import (
    STATUS_FAILED,
    STATUS_OK,
    probe_data_source,
    source_health_key,
    validate_row_shape,
)


def test_source_health_key_distinguishes_urls() -> None:
    a = {"id": "x", "ingest_mode": "html_list", "list_monitor_url": "https://a.com/1"}
    b = {"id": "x", "ingest_mode": "html_list", "list_monitor_url": "https://a.com/2"}
    assert source_health_key(a) != source_health_key(b)


def test_validate_row_shape_requires_url() -> None:
    err = validate_row_shape({"id": "a", "name": "n", "value": "example.com"})
    assert err is not None


def test_probe_html_list_ok(tmp_path, monkeypatch) -> None:
    row = {
        "id": "t1",
        "name": "测试源",
        "value": "example.com",
        "ingest_mode": "html_list",
        "list_monitor_url": "https://example.com/news/",
    }

    async def fake_fetch(*_a, **_k):
        from src.search import SearchHit

        return [SearchHit(title="标题一", url="https://example.com/a.html", snippet="", published_at="")]

    with patch("src.services.data_source_health.fetch_html_list_hits", new=fake_fetch):
        with patch("httpx.AsyncClient.get", new=AsyncMock(return_value=_FakeResp(200))):
            probe = asyncio.run(probe_data_source(row))
    assert probe.ok
    assert probe.status == STATUS_OK
    assert probe.sample_count == 1


def test_probe_html_list_empty(tmp_path) -> None:
    row = {
        "id": "t2",
        "name": "空源",
        "value": "example.com",
        "ingest_mode": "html_list",
        "list_monitor_url": "https://example.com/empty/",
    }

    async def fake_fetch(*_a, **_k):
        return []

    with patch("src.services.data_source_health.fetch_html_list_hits", new=fake_fetch):
        with patch("httpx.AsyncClient.get", new=AsyncMock(return_value=_FakeResp(200))):
            probe = asyncio.run(probe_data_source(row))
    assert not probe.ok
    assert probe.status == STATUS_FAILED


def test_health_store_needs_attention(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    row = {
        "id": "t3",
        "name": "坏源",
        "value": "bad.com",
        "ingest_mode": "html_list",
        "list_monitor_url": "https://bad.com/x",
    }
    from src.services.data_source_health import ProbeResult

    data_source_health_store.record_probe(
        row,
        ProbeResult(ok=False, status=STATUS_FAILED, message="fail", ingest_mode="html_list"),
    )
    resp = data_source_health_store.build_health_response([row])
    key = source_health_key(row)
    assert resp["sources"][key]["needs_attention"] is True
    data_source_health_store.acknowledge_source(key, note="已更换栏目")
    resp2 = data_source_health_store.build_health_response([row])
    assert resp2["sources"][key]["needs_attention"] is False


class _FakeResp:
    status_code = 200
    encoding = "utf-8"

    def __init__(self, code: int) -> None:
        self.status_code = code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            import httpx

            raise httpx.HTTPStatusError("err", request=None, response=self)
