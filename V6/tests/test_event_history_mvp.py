"""事件关联链：排除近重复标题。"""
from __future__ import annotations

from src.services.event_history_mvp import build_event_history_payload
from src.storage import JsonStore


def test_history_excludes_near_duplicate_titles(tmp_path) -> None:
    store = JsonStore(tmp_path)
    keep = "ev-keep"
    dup = "ev-dup"
    other = "ev-other"
    store._write_events(
        [
            {
                "id": keep,
                "headline_zh": "NATS DroneCloud与Network Rail完成无人机操作试验",
                "created_at": "2026-06-08T00:05:25+00:00",
                "dominant_topic_key": "intl_coopcomp",
            },
            {
                "id": dup,
                "headline_zh": "NATS DroneCloud与Network Rail完成铁路周边无人机操作试验",
                "created_at": "2026-06-08T15:21:17+00:00",
                "dominant_topic_key": "intl_coopcomp",
            },
            {
                "id": other,
                "headline_zh": "芬兰无人机服务商公开招募飞行员",
                "created_at": "2026-06-07T10:00:00+00:00",
                "dominant_topic_key": "intl_coopcomp",
            },
        ]
    )
    payload = build_event_history_payload(store, keep)
    chain_ids = {x["eventId"] for x in payload["chain"]}
    assert dup not in chain_ids
    assert other in chain_ids
