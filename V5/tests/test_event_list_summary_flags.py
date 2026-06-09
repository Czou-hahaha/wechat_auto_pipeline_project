"""界面 hasSummary = 仅 DeepSeek 事件通稿 event_press_zh（新闻稿），非簇摘要。"""
from __future__ import annotations

from src.bff.event_mapper import (
    _has_event_news_press,
    _event_summary_kind,
    event_to_list_item,
)


def test_press_generated_is_has_summary() -> None:
    ev = {
        "id": "e1",
        "title": "ACSL partners Draganfly",
        "summary": "簇摘要不应算" * 50,
        "event_press_zh": "通稿正文" * 40,
        "event_press_generated_at": "2026-05-17T15:31:33+00:00",
        "created_at": "2026-05-19T16:16:47+00:00",
    }
    arts = [{"id": "a1", "status": "ready_for_review"}, {"id": "a2", "status": "pending_summary"}]
    assert _has_event_news_press(ev, arts) is True
    item = event_to_list_item(ev, arts)
    assert item["hasSummary"] is True
    assert item["summaryKind"] == "press"
    assert item["summaryPreview"]


def test_cluster_only_not_has_summary() -> None:
    ev = {
        "id": "e2",
        "title": "BAE Vantor GPS",
        "summary": "仅有簇摘要" * 80,
        "event_press_zh": "",
        "created_at": "2026-05-18T13:27:31+00:00",
    }
    arts = [{"id": "a1", "status": "ready_for_review"}]
    item = event_to_list_item(ev, arts)
    assert item["hasSummary"] is False
    assert item["summaryKind"] == "none"
    assert not item["summaryPreview"]


def test_single_reference_no_press_not_has_summary() -> None:
    ev = {
        "id": "e3",
        "title": "One article only",
        "summary": "x" * 200,
        "event_press_zh": "",
        "created_at": "2026-05-21T00:00:00+00:00",
    }
    arts = [{"id": "a1", "status": "ready_for_review"}]
    assert event_to_list_item(ev, arts)["hasSummary"] is False


def test_press_without_generated_at_not_has_summary() -> None:
    ev = {
        "id": "e4",
        "event_press_zh": "y" * 200,
        "event_press_generated_at": "",
        "created_at": "2026-05-21T00:00:00+00:00",
    }
    arts = [{"id": "a1"}, {"id": "a2"}]
    assert _has_event_news_press(ev, arts) is False


def test_pushable_tag_requires_qa() -> None:
    ev = {
        "id": "e5",
        "title": "Ready press",
        "event_press_zh": "通稿正文" * 40,
        "event_press_generated_at": "2026-05-17T15:31:33+00:00",
        "event_press_qa_score": 85,
        "event_press_qa_approved": True,
        "created_at": "2026-05-19T16:16:47+00:00",
    }
    arts = [
        {"id": "a1", "status": "ready_for_review"},
        {"id": "a2", "status": "pending_summary"},
    ]
    item = event_to_list_item(ev, arts)
    assert item["hasSummary"] is True
    assert item["tags"] == ["可推送"]
    assert item["pushable"] is True
    assert item["needsExpansion"] is False


def test_pushed_tag_overrides_pushable() -> None:
    ev = {
        "id": "e7",
        "title": "Already pushed",
        "event_press_zh": "通稿正文" * 40,
        "event_press_generated_at": "2026-05-17T15:31:33+00:00",
        "event_press_qa_score": 90,
        "event_press_qa_approved": True,
        "event_wechat_draft_pushed_at": "2026-05-18T10:00:00+00:00",
        "created_at": "2026-05-19T16:16:47+00:00",
    }
    arts = [
        {"id": "a1", "status": "ready_for_review"},
        {"id": "a2", "status": "pending_summary"},
    ]
    item = event_to_list_item(ev, arts)
    assert item["tags"] == ["草稿已推"]
    assert item["pushed"] is True
    assert item["pushable"] is False


def test_needs_expansion_tag_single_seed() -> None:
    ev = {
        "id": "e6",
        "title": "One seed only",
        "event_press_zh": "",
        "created_at": "2026-05-21T00:00:00+00:00",
    }
    arts = [{"id": "a1", "status": "ready_for_review", "title": "seed"}]
    item = event_to_list_item(ev, arts)
    assert item["tags"] == ["待扩搜"]
    assert item["needsExpansion"] is True
    assert item["pushable"] is False
