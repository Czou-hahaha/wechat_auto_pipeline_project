"""发布时间解析与日历窗单测。"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from bs4 import BeautifulSoup

from src.ai import SummaryService
from src.pipeline import PipelineRunner
from src.rss_aggregate import _parse_iso_from_pubdate


def test_rss_pubdate_non_rfc() -> None:
    assert "2026-05-12" in _parse_iso_from_pubdate("2026-05-12 19:22:30")


def test_parse_chinese_with_clock() -> None:
    iso, coarse = PipelineRunner._parse_published_raw_to_utc("2026年05月12日 10:11")
    assert iso
    assert coarse is False


def test_parse_chinese_date_only() -> None:
    iso, coarse = PipelineRunner._parse_published_raw_to_utc("2026年05月12日")
    assert iso
    assert coarse is True


def test_parse_dot_separated_datetime() -> None:
    iso, coarse = PipelineRunner._parse_published_raw_to_utc("2026.05.19 22:09")
    assert iso
    assert coarse is False


def test_prefer_full_publish_datetime_text() -> None:
    picked = PipelineRunner._prefer_publish_datetime_text(["21:46", "2026.05.20 19:54", "09:10"])
    assert "2026.05.20" in picked


def test_extract_tmtpost_article_time_from_html() -> None:
    html = '<div class="section-article"><p class="time">2026.05.20 19:54</p></div><p class="time">21:46</p>'
    soup = BeautifulSoup(html, "html.parser")
    settings = MagicMock()
    settings.his_data_sources_path = "config/data_sources.json"
    runner = PipelineRunner.__new__(PipelineRunner)
    runner._published_css_by_host = {
        "tmtpost.com": [".section-article .time", ".post_left .time", ".time", "span.time"]
    }
    runner.settings = settings
    iso, coarse = runner._extract_published_at(soup, page_url="https://www.tmtpost.com/7995553.html")
    assert iso.startswith("2026-05-20")
    assert coarse is False


def test_extract_faa_drupal_mb4() -> None:
    html = (
        '<div class="node__content mt-0 clearfix">'
        '<h1 class="page__title">x</h1>'
        '<div class="mb-4">Wednesday, May 6, 2026</div></div>'
    )
    soup = BeautifulSoup(html, "html.parser")
    settings = MagicMock()
    settings.his_data_sources_path = "__missing__.json"
    runner = PipelineRunner.__new__(PipelineRunner)
    runner._published_css_by_host = {}
    runner.settings = settings
    iso, coarse = runner._extract_published_at(soup, page_url="https://www.faa.gov/newsroom/foo")
    assert iso.startswith("2026-05-06")
    assert coarse is True


def test_qa_date_only_in_calendar_window() -> None:
    from zoneinfo import ZoneInfo

    tz = ZoneInfo("Asia/Shanghai")
    now = datetime.now(timezone.utc).astimezone(tz)
    noon = now.replace(hour=12, minute=0, second=0, microsecond=0)
    ok = SummaryService._source_published_in_window(
        source_published_at=noon.isoformat(),
        max_article_age_hours=12,
        date_only_coarse=True,
        date_only_max_calendar_age_days=3,
        schedule_timezone="Asia/Shanghai",
    )
    assert ok is True


def test_qa_full_timestamp_outside_hours() -> None:
    old = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    ok = SummaryService._source_published_in_window(
        source_published_at=old,
        max_article_age_hours=12,
        date_only_coarse=False,
        date_only_max_calendar_age_days=3,
        schedule_timezone="Asia/Shanghai",
    )
    assert ok is False
