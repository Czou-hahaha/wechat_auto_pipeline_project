"""article_selector：来源优先级与转载去重。"""

from __future__ import annotations

from src.services.ai_press_writer.article_selector import (
    select_articles_for_event,
    source_tier_for_host,
)


def test_tier_official_gov_cn() -> None:
    assert source_tier_for_host("www.miit.gov.cn") == 1


def test_tier_wire_reuters() -> None:
    assert source_tier_for_host("www.reuters.com") == 2


def test_tier_tech_36kr() -> None:
    assert source_tier_for_host("36kr.com") == 3


def test_tier_cn_media() -> None:
    assert source_tier_for_host("www.thepaper.cn") == 4


def test_select_top_k_respects_priority() -> None:
    rows = [
        {
            "id": "1",
            "title": "Low topic A",
            "extracted_text": "x" * 500,
            "source_host": "example.com",
            "resolved_url": "https://example.com/a",
        },
        {
            "id": "2",
            "title": "Policy B",
            "extracted_text": "y" * 500,
            "source_host": "www.miit.gov.cn",
            "resolved_url": "https://www.miit.gov.cn/b",
        },
        {
            "id": "3",
            "title": "Wire C",
            "extracted_text": "z" * 500,
            "source_host": "reuters.com",
            "resolved_url": "https://reuters.com/c",
        },
    ]
    # gov.cn tier 1 first
    picked = select_articles_for_event(rows, top_k=2)
    assert len(picked) == 2
    assert picked[0].source_label == "www.miit.gov.cn"
    assert picked[1].source_label == "reuters.com"


def test_all_by_tier_includes_all_distinct_urls() -> None:
    rows = [
        {
            "id": "1",
            "title": "A",
            "extracted_text": "x" * 500,
            "source_host": "www.miit.gov.cn",
            "resolved_url": "https://www.miit.gov.cn/a",
        },
        {
            "id": "2",
            "title": "B",
            "extracted_text": "x" * 500,
            "source_host": "reuters.com",
            "resolved_url": "https://reuters.com/b",
        },
        {
            "id": "3",
            "title": "C",
            "extracted_text": "x" * 500,
            "source_host": "example.com",
            "resolved_url": "https://example.com/c",
        },
    ]
    picked = select_articles_for_event(rows, mode="all_by_tier", max_articles_in_prompt=10)
    assert len(picked) == 3


def test_select_dedupes_near_duplicate_titles() -> None:
    body = "国务院某部门发布通知，明确无人机管理新要求。" * 5
    rows = [
        {
            "id": "a",
            "title": "国务院发布无人机管理新规",
            "extracted_text": body,
            "source_host": "news.site1.com",
            "resolved_url": "https://news.site1.com/1",
        },
        {
            "id": "b",
            "title": "国务院发布无人机管理新规",
            "extracted_text": body,
            "source_host": "news.site2.com",
            "resolved_url": "https://news.site2.com/2",
        },
        {
            "id": "c",
            "title": "另一主题：民航局同步细化登记办法",
            "extracted_text": "完全不同的正文内容。" * 40,
            "source_host": "other.net",
            "resolved_url": "https://other.net/c",
        },
    ]
    picked = select_articles_for_event(rows, top_k=5)
    assert len(picked) == 2
    assert sum(1 for p in picked if "国务院" in p.title) == 1


def test_all_by_tier_dedupes_identical_canonical_url() -> None:
    rows = [
        {
            "id": "a",
            "title": "稿一",
            "extracted_text": "正文甲内容不重复。" * 20,
            "source_host": "a.com",
            "resolved_url": "https://same.example/x",
        },
        {
            "id": "b",
            "title": "稿二",
            "extracted_text": "正文乙另一套字。" * 20,
            "source_host": "b.com",
            "resolved_url": "https://same.example/x",
        },
    ]
    picked = select_articles_for_event(rows, mode="all_by_tier", max_articles_in_prompt=10)
    assert len(picked) == 1
