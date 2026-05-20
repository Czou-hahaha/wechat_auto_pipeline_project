"""抓正文前主题过滤。"""
from __future__ import annotations

from src.search import SearchHit
from src.utils.topic_prefilter import (
    is_obvious_offtopic_headline,
    is_prison_crime_drone_headline,
    is_taiwan_politics_headline,
    is_traditional_chinese_dominant,
    should_fetch_search_hit,
    should_keep_editorial_content,
)


def test_rejects_war_drone_strike_without_industry_context() -> None:
    hit = SearchHit(
        title="Iran drone strike hits UAE nuclear plant",
        url="https://example.com/a",
        snippet="Middle East conflict escalates",
        published_at="2026-05-19T00:00:00Z",
    )
    assert not should_fetch_search_hit(hit)


def test_keeps_evtol_headline() -> None:
    hit = SearchHit(
        title="FAA advances eVTOL air taxi certification path",
        url="https://example.com/b",
        snippet="Urban air mobility operators await rulemaking",
        published_at="2026-05-19T00:00:00Z",
    )
    assert should_fetch_search_hit(hit)


def test_rejects_mining_subsidy_noise() -> None:
    assert is_obvious_offtopic_headline(
        title="Mining subsidy overhaul in iron ore sector",
        snippet="Government adjusts coal subsidy rules",
    )


def test_rejects_forbes_war_corridor() -> None:
    hit = SearchHit(
        title="Russians Establish Drone Corridors Through Ukrainian Kill Zones",
        url="https://www.forbes.com/example",
        snippet="",
        published_at="2026-05-19T00:00:00Z",
    )
    assert not should_fetch_search_hit(hit)


def test_rejects_mashable_deal() -> None:
    hit = SearchHit(
        title="The DJI Neo drone hits record - low price at Amazon - save $30",
        url="https://mashable.com/article/deal",
        snippet="Memorial Day sale",
        published_at="2026-05-19T00:00:00Z",
    )
    assert not should_fetch_search_hit(hit)


def test_rejects_prison_drone_operator() -> None:
    assert is_prison_crime_drone_headline(
        title="Prison ‘drone operator’ held",
        snippet="contraband smuggled into jail",
    )
    assert not should_keep_editorial_content(
        title="Prison ‘drone operator’ held",
        snippet="contraband",
        url="https://example.com/p",
    )


def test_rejects_taiwan_politics_without_industry() -> None:
    assert is_taiwan_politics_headline(
        title="台海局势最新：军方回应",
        snippet="两岸关系",
        url="https://news.example.tw/a",
    )


def test_rejects_traditional_chinese_headline() -> None:
    assert is_traditional_chinese_dominant(
        title="無人機產業在臺灣的發展與挑戰",
        snippet="",
    )


def test_keeps_fcc_drone_policy() -> None:
    assert should_keep_editorial_content(
        title="FCC just saved millions of DJI drones from going obsolete",
        snippet="firmware waiver drone operators",
        url="https://dronedj.com/a",
    )


def test_keeps_pinned_url_without_title() -> None:
    hit = SearchHit(
        title="",
        url="https://dronedj.com/2026/05/18/dji-autel-fcc-drone-firmware/",
        snippet="",
        published_at="2026-05-19T00:00:00Z",
    )
    assert should_fetch_search_hit(hit)
