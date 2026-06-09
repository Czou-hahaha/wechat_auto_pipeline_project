"""数据源可达性与可采集性探测（RSS / 栏目页）。"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import httpx

from src.config import Settings
from src.html_list_monitor import DEFAULT_INGEST_UA, fetch_html_list_hits
from src.rss_aggregate import _fetch_one_feed

logger = logging.getLogger(__name__)

STATUS_OK = "ok"
STATUS_FAILED = "failed"
STATUS_CHECKING = "checking"


@dataclass
class ProbeResult:
    ok: bool
    status: str
    message: str
    sample_count: int = 0
    http_status: int | None = None
    ingest_mode: str = ""
    probe_url: str = ""


def source_health_key(row: dict[str, Any]) -> str:
    """稳定键：同一 id 不同栏目 URL 视为不同探测目标。"""
    sid = str(row.get("id") or "").strip()
    mode = str(row.get("ingest_mode") or "html_list").strip().lower()
    if mode == "rss" or bool(row.get("rss_available")):
        url = str(row.get("rss") or row.get("list_monitor_url") or "").strip()
    else:
        url = str(row.get("list_monitor_url") or "").strip()
    return f"{sid}|{url}" if url else sid or "unknown"


def _probe_url_for_row(row: dict[str, Any]) -> tuple[str, str]:
    mode = str(row.get("ingest_mode") or "html_list").strip().lower()
    if mode == "rss" or bool(row.get("rss_available")):
        url = str(row.get("rss") or row.get("list_monitor_url") or "").strip()
        return "rss", url
    return "html_list", str(row.get("list_monitor_url") or "").strip()


def validate_row_shape(row: dict[str, Any]) -> str | None:
    if not str(row.get("id") or "").strip():
        return "缺少数据源 id"
    if not str(row.get("name") or "").strip():
        return "缺少名称"
    if not str(row.get("value") or "").strip():
        return "缺少域名 value"
    mode, url = _probe_url_for_row(row)
    if not url.startswith("http"):
        return "RSS 地址" if mode == "rss" else "栏目页地址" + "须为 http(s) URL"
    return None


async def probe_data_source(
    row: dict[str, Any],
    settings: Settings | None = None,
) -> ProbeResult:
    """探测单个数据源是否可 HTTP 访问且能解析出稿件条目。"""
    s = settings or Settings()
    err = validate_row_shape(row)
    if err:
        return ProbeResult(ok=False, status=STATUS_FAILED, message=err)

    mode, url = _probe_url_for_row(row)
    site = str(row.get("value") or "").strip()
    name = str(row.get("name") or "").strip()
    timeout = max(8.0, float(s.data_source_health_timeout_sec))
    min_samples = max(1, int(s.data_source_health_min_samples))

    async with httpx.AsyncClient(
        timeout=httpx.Timeout(timeout),
        follow_redirects=True,
    ) as client:
        if mode == "rss":
            try:
                resp = await client.get(url, headers={"User-Agent": DEFAULT_INGEST_UA})
                http_status = resp.status_code
                resp.raise_for_status()
            except httpx.HTTPStatusError as exc:
                code = exc.response.status_code if exc.response else None
                return ProbeResult(
                    ok=False,
                    status=STATUS_FAILED,
                    message=f"RSS 请求失败 HTTP {code}",
                    http_status=code,
                    ingest_mode=mode,
                    probe_url=url,
                )
            except Exception as exc:
                logger.warning("rss probe failed name=%s", name, exc_info=True)
                return ProbeResult(
                    ok=False,
                    status=STATUS_FAILED,
                    message=f"RSS 无法访问：{type(exc).__name__}",
                    ingest_mode=mode,
                    probe_url=url,
                )
            hits = await _fetch_one_feed(
                client,
                url,
                per_feed_max=10,
                keywords=None,
                relevance_filter=False,
            )
            count = len(hits)
            if count >= min_samples:
                return ProbeResult(
                    ok=True,
                    status=STATUS_OK,
                    message=f"验证通过：解析到 {count} 条 RSS 条目",
                    sample_count=count,
                    http_status=http_status,
                    ingest_mode=mode,
                    probe_url=url,
                )
            return ProbeResult(
                ok=False,
                status=STATUS_FAILED,
                message="RSS 可访问但未解析到稿件条目（检查 feed 是否为空或格式异常）",
                sample_count=count,
                http_status=http_status,
                ingest_mode=mode,
                probe_url=url,
            )

        hits = await fetch_html_list_hits(
            client,
            list_url=url,
            site_value=site,
            per_feed_max=15,
            keywords=None,
            relevance_filter=False,
            source_name=name,
        )
        count = len(hits)
        if count >= min_samples:
            return ProbeResult(
                ok=True,
                status=STATUS_OK,
                message=f"验证通过：发现 {count} 条可采集链接",
                sample_count=count,
                ingest_mode=mode,
                probe_url=url,
            )
        if count == 0:
            msg = "栏目页无法访问或未匹配到本站稿件链接（检查域名与栏目 URL 是否变更）"
        else:
            msg = "页面可访问但未匹配到本站稿件链接（检查域名与栏目 URL 是否变更）"
        return ProbeResult(
            ok=False,
            status=STATUS_FAILED,
            message=msg,
            sample_count=count,
            ingest_mode=mode,
            probe_url=url,
        )


async def probe_all_configured_sources(settings: Settings | None = None) -> dict[str, ProbeResult]:
    from src.bff import config_api

    s = settings or Settings()
    rows = config_api.get_data_sources()
    out: dict[str, ProbeResult] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        key = source_health_key(row)
        out[key] = await probe_data_source(row, s)
    return out
