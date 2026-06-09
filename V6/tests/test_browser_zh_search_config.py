"""browser_zh_sources 配置与日期解析（不启动浏览器）。"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from src.browser_zh_search import (
    _parse_context_datetime,
    _published_at_for_browser_hit,
    _within_max_age,
    load_browser_zh_site_configs,
)
from src.config import Settings


def test_load_browser_zh_sites_has_cls() -> None:
    root = Path(__file__).resolve().parents[1]
    settings = Settings(browser_zh_sources_path=str(root / "config/browser_zh_sources.json"))
    sites = load_browser_zh_site_configs(settings)
    ids = {s["source_id"] for s in sites}
    assert "cn_cls_001" in ids


def test_browser_zh_keywords_three_terms() -> None:
    root = Path(__file__).resolve().parents[1]
    settings = Settings(browser_zh_keywords_path=str(root / "config/browser_zh_keywords.json"))
    kws = settings.parsed_browser_zh_keywords()
    assert kws == ["无人机", "低空经济", "eVTOL"]


def test_parse_zh_datetime_recent() -> None:
    now = datetime(2026, 5, 31, 2, 0, tzinfo=timezone.utc)
    iso = _parse_context_datetime("财联社 5月30日 22:18", now=now)
    assert iso
    assert _within_max_age(iso, max_hours=24, now=now)


def test_empty_published_at_kept_for_backfill() -> None:
    now = datetime(2026, 5, 31, 2, 0, tzinfo=timezone.utc)
    assert _within_max_age("", max_hours=24, now=now)


def test_stale_list_date_deferred_to_pipeline() -> None:
    now = datetime(2026, 6, 6, 12, 0, tzinfo=timezone.utc)
    old = "2026-05-20T04:00:00+00:00"
    assert not _within_max_age(old, max_hours=24, now=now)
    assert _published_at_for_browser_hit(old, max_hours=24, now=now) == ""


def test_sites_search_url_only() -> None:
    root = Path(__file__).resolve().parents[1]
    settings = Settings(browser_zh_sources_path=str(root / "config/browser_zh_sources.json"))
    by_id = {s["source_id"]: s for s in load_browser_zh_site_configs(settings)}
    jm = by_id["cn_jiemian_001"]["strategies"]
    assert all(s.get("kind") == "search_url" for s in jm)
    assert any("a.jiemian.com" in s.get("url", "") for s in jm)
    kr = by_id["cn_36kr_001"]["strategies"]
    assert all(s.get("kind") == "search_url" for s in kr)
    cls = by_id["cn_cls_001"]["strategies"]
    assert len(cls) == 1 and cls[0].get("kind") == "search_url"
