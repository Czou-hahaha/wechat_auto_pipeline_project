"""入库累增：同题簇并入库内已有 event。"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from unittest.mock import AsyncMock, patch

from src.config import Settings
from src.storage import JsonStore
from src.utils.event_accumulate import (
    existing_event_by_urls,
    match_existing_event_id,
    urls_already_in_event,
)


@dataclass
class _Hit:
    url: str


@dataclass
class _Prep:
    title: str
    text: str
    source_published_at: str
    final_url: str = ""
    hit: _Hit | None = None

    def __post_init__(self) -> None:
        if self.hit is None:
            self.hit = _Hit(url=self.final_url or "https://example.com/a")


def test_existing_event_by_url(tmp_path) -> None:
    store = JsonStore(tmp_path)
    eid = "ev-keep-001"
    store._write_events(
        [
            {
                "id": eid,
                "title": "ACSL Draganfly",
                "summary": "",
                "created_at": "2026-05-17T15:21:54+00:00",
            }
        ]
    )
    store._write(
        [
            {
                "id": "art-1",
                "title": "Partner",
                "source_url": "https://www.suasnews.com/2026/05/acsl-draganfly/",
                "resolved_url": "https://www.suasnews.com/2026/05/acsl-draganfly/",
                "event_id": eid,
                "source_published_at": "2026-05-12T00:00:00+00:00",
                "extracted_text": "ACSL Draganfly deal",
            }
        ]
    )
    cluster = [
        _Prep(
            "Drone Makers ACSL and Draganfly Partner",
            "NDAA compliant drones Canada",
            "2026-05-17T15:22:17+00:00",
            final_url="https://www.suasnews.com/2026/05/acsl-draganfly/",
        )
    ]
    assert existing_event_by_urls(store, cluster) == eid


def test_match_existing_by_embedding(tmp_path) -> None:
    asyncio.run(_test_match_existing_by_embedding(tmp_path))


async def _test_match_existing_by_embedding(tmp_path) -> None:
    store = JsonStore(tmp_path)
    eid = "ev-acsl-001"
    store._write_events(
        [
            {
                "id": eid,
                "title": "ACSL SOTEN Canada Draganfly",
                "created_at": "2026-05-17T15:21:54+00:00",
            }
        ]
    )
    store._write(
        [
            {
                "id": "a1",
                "title": "ACSL lands in Canada through Draganfly",
                "source_url": "https://dronedj.com/acsl",
                "resolved_url": "https://dronedj.com/acsl",
                "event_id": eid,
                "source_published_at": "2026-05-11T08:00:00+00:00",
                "extracted_text": "ACSL Draganfly exclusive distribution Canada SOTEN",
            }
        ]
    )
    cluster = [
        _Prep(
            "Drone Makers ACSL and Draganfly Partner NDAA",
            "Japanese ACSL Canadian Draganfly agreement",
            "2026-05-17T15:22:00+00:00",
            final_url="https://other.com/new-acsl-story",
        )
    ]
    vec = [1.0, 0.0, 0.0]
    settings = Settings(
        EMBEDDING_ENABLED=True,
        EMBEDDING_BACKEND="local",
        EMBEDDING_EVENT_LINK_MIN=0.75,
        CLUSTER_MERGE_HOURS=168,
    )
    with patch(
        "src.utils.event_accumulate.fetch_embeddings_batch",
        new=AsyncMock(return_value=[vec, vec]),
    ):
        matched = await match_existing_event_id(
            cluster=cluster, store=store, settings=settings
        )
    assert matched == eid


def test_urls_already_in_event(tmp_path) -> None:
    store = JsonStore(tmp_path)
    eid = "ev-1"
    url = "https://dronedj.com/2026/05/11/acsl/"
    store._write(
        [
            {
                "id": "x",
                "title": "t",
                "source_url": url,
                "resolved_url": url,
                "event_id": eid,
            }
        ]
    )
    fps = urls_already_in_event(store, eid)
    assert JsonStore.url_fingerprint(url) in fps
