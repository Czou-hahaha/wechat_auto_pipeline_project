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


def test_existing_event_by_map_url_without_articles(tmp_path) -> None:
    """articles.json 已清空时，仍可通过 event_article_map 命中已有 event。"""
    store = JsonStore(tmp_path)
    eid = "ev-map-001"
    url = "https://dronedj.com/2026/06/04/dji-drone-maya-civilization-guatemala/"
    store._write_events(
        [
            {
                "id": eid,
                "title": "This DJI drone uncovered Maya megacities",
                "title_zh": "大疆无人机在热带雨林中借助激光雷达发现千年玛雅古城",
                "created_at": "2026-06-07T14:38:17+00:00",
            }
        ]
    )
    store._write_event_map(
        [
            {
                "event_id": eid,
                "source_url": url,
                "resolved_url": url,
                "role": "primary",
            }
        ]
    )
    cluster = [
        _Prep(
            "This DJI drone uncovered Maya megacities hidden for 1,000 years",
            "DJI Matrice Maya LiDAR Guatemala",
            "2026-06-08T00:47:00+00:00",
            final_url=url,
        )
    ]
    assert existing_event_by_urls(store, cluster) == eid


def test_title_overlap_chinese_bigrams() -> None:
    from src.utils.event_accumulate import _title_overlap

    a = "大疆无人机揭示隐藏千年的玛雅巨型城市"
    b = "大疆无人机在热带雨林中借助激光雷达发现千年玛雅古城"
    assert _title_overlap(a, b) >= 0.15


def test_match_existing_when_articles_stripped(tmp_path) -> None:
    asyncio.run(_test_match_existing_when_articles_stripped(tmp_path))


async def _test_match_existing_when_articles_stripped(tmp_path) -> None:
    store = JsonStore(tmp_path)
    eid = "ev-nats-001"
    store._write_events(
        [
            {
                "id": eid,
                "title": "NATS DroneCloud and Network Rail complete trial",
                "title_zh": "NATS DroneCloud与Network Rail完成无人机操作试验",
                "headline_zh": "NATS DroneCloud与Network Rail完成无人机操作试验",
                "event_press_zh": "NATS DroneCloud Network Rail BVLOS trial UK",
                "created_at": "2026-06-08T00:05:25+00:00",
            }
        ]
    )
    store._write_event_map(
        [
            {
                "event_id": eid,
                "source_url": "https://dronecloud.io/",
                "resolved_url": "https://dronecloud.io/",
                "role": "support",
            }
        ]
    )
    cluster = [
        _Prep(
            "NATS DroneCloud and Network Rail complete trial around railways",
            "Network Rail drone operations SOCNI",
            "2026-06-08T15:21:00+00:00",
            final_url="https://dronecloud.io/",
        )
    ]
    settings = Settings(
        EMBEDDING_ENABLED=False,
        CLUSTER_MERGE_HOURS=168,
    )
    matched = await match_existing_event_id(cluster=cluster, store=store, settings=settings)
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
