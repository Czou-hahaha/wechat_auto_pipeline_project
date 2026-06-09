"""草稿已推时间戳同步与手工标记。"""
from __future__ import annotations

from src.bff.wechat_draft import mark_event_draft_pushed
from src.storage import ArticleRecord, EventRecord, JsonStore


def test_sync_event_draft_pushed_from_articles(tmp_path) -> None:
    store = JsonStore(tmp_path)
    store.append_event(
        EventRecord(
            id="ev1",
            title="t",
            summary="",
            summary_zh="",
            dominant_topic_key="",
            created_at="2026-05-18T00:00:00+00:00",
        )
    )
    store.add(
        ArticleRecord(
            id="a1",
            title="a",
            source_url="https://x.com/1",
            source_published_at="2026-05-18T00:00:00+00:00",
            extracted_text="",
            summary="",
            status="ready",
            created_at="2026-05-18T00:00:00+00:00",
            published_at="",
            event_id="ev1",
            wechat_draft_pushed_at="2026-05-18T13:14:09+00:00",
        )
    )
    assert store.sync_event_draft_pushed_flags() == 1
    ev = store.get_event("ev1")
    assert ev is not None
    assert ev.get("event_wechat_draft_pushed_at") == "2026-05-18T13:14:09+00:00"


def test_mark_event_draft_pushed(tmp_path) -> None:
    store = JsonStore(tmp_path)
    store.append_event(
        EventRecord(
            id="ev2",
            title="t",
            summary="",
            summary_zh="",
            dominant_topic_key="",
            created_at="2026-05-18T00:00:00+00:00",
        )
    )
    out = mark_event_draft_pushed(store, "ev2")
    assert out["ok"] is True
    ev = store.get_event("ev2")
    assert ev is not None
    assert str(ev.get("event_wechat_draft_pushed_at") or "").strip()
