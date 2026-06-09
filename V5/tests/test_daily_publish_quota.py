"""日配额按事件数统计（非 articles 行数）。"""
from __future__ import annotations

from datetime import date

from src.storage import ArticleRecord, EventRecord, JsonStore


def test_daily_quota_counts_one_event_with_many_articles(tmp_path) -> None:
    store = JsonStore(tmp_path)
    store.append_event(
        EventRecord(
            id="ev1",
            title="t",
            summary="",
            summary_zh="",
            dominant_topic_key="",
            created_at="2026-05-22T00:00:00+00:00",
        )
    )
    store.patch_event("ev1", {"event_wechat_draft_pushed_at": "2026-05-21T16:10:50.718149+00:00"})
    for i in range(6):
        store.add(
            ArticleRecord(
                id=f"a{i}",
                title=f"article {i}",
                source_url=f"https://x.com/{i}",
                source_published_at="2026-05-22T00:00:00+00:00",
                extracted_text="",
                summary="",
                status="ready",
                created_at="2026-05-22T00:00:00+00:00",
                published_at="",
                event_id="ev1",
                wechat_draft_pushed_at="2026-05-21T16:10:50.718149+00:00",
            )
        )
    n = store.count_wechat_draft_pushed_events_on_local_date(
        date(2026, 5, 22),
        timezone="Asia/Shanghai",
    )
    assert n == 1


def test_daily_quota_counts_distinct_events(tmp_path) -> None:
    store = JsonStore(tmp_path)
    for eid, ts in (
        ("ev1", "2026-05-21T16:10:50+00:00"),
        ("ev2", "2026-05-21T16:18:16+00:00"),
    ):
        store.append_event(
            EventRecord(
                id=eid,
                title="t",
                summary="",
                summary_zh="",
                dominant_topic_key="",
                created_at="2026-05-22T00:00:00+00:00",
            )
        )
        store.patch_event(eid, {"event_wechat_draft_pushed_at": ts})
    n = store.count_wechat_draft_pushed_events_on_local_date(
        date(2026, 5, 22),
        timezone="Asia/Shanghai",
    )
    assert n == 2


def test_pipeline_remaining_slots_by_events(tmp_path, monkeypatch) -> None:
    from src.config import Settings
    from src.pipeline import PipelineRunner

    store = JsonStore(tmp_path)
    store.append_event(
        EventRecord(
            id="ev1",
            title="t",
            summary="",
            summary_zh="",
            dominant_topic_key="",
            created_at="2026-05-22T00:00:00+00:00",
        )
    )
    store.patch_event("ev1", {"event_wechat_draft_pushed_at": "2026-05-21T16:10:50+00:00"})
    for i in range(10):
        store.add(
            ArticleRecord(
                id=f"a{i}",
                title="x",
                source_url=f"https://x.com/{i}",
                source_published_at="2026-05-22T00:00:00+00:00",
                extracted_text="",
                summary="",
                status="ready",
                created_at="2026-05-22T00:00:00+00:00",
                published_at="",
                event_id="ev1",
                wechat_draft_pushed_at="2026-05-21T16:10:50+00:00",
            )
        )

    monkeypatch.setenv("MAX_PUBLISH_PER_DAY", "5")
    settings = Settings(
        data_dir=str(tmp_path),
        schedule_timezone="Asia/Shanghai",
    )
    runner = PipelineRunner(settings)
    runner.store = store

    class _FixedDatetime:
        @classmethod
        def now(cls, tz):  # noqa: ANN001
            from datetime import datetime

            return datetime(2026, 5, 22, 8, 0, 0, tzinfo=tz)

    monkeypatch.setattr("src.pipeline.datetime", _FixedDatetime)
    pushed = store.count_wechat_draft_pushed_events_on_local_date(
        date(2026, 5, 22),
        timezone="Asia/Shanghai",
    )
    assert pushed == 1
    assert runner._remaining_daily_publish_slots() == settings.max_publish_per_day - pushed
