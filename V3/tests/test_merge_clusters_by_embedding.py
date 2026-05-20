"""簇级向量合并：同窗 + 余弦阈值，不依赖关键词枚举。"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from unittest.mock import AsyncMock, patch

from src.config import Settings
from src.ingest_cluster import merge_clusters_by_embedding


@dataclass
class _FakePrepared:
    title: str
    text: str
    source_published_at: str = "2026-05-11T08:00:00+00:00"


def test_merge_clusters_unions_similar_reps_within_span() -> None:
    asyncio.run(_test_merge_clusters_unions_similar_reps_within_span())


async def _test_merge_clusters_unions_similar_reps_within_span() -> None:
    vec = [1.0, 0.0, 0.0]
    c1 = [_FakePrepared("ACSL Canada A", "same story A", "2026-05-11T08:00:00+00:00")]
    c2 = [_FakePrepared("ACSL Canada B", "same story B", "2026-05-15T08:00:00+00:00")]
    settings = Settings(
        EMBEDDING_ENABLED=True,
        EMBEDDING_BACKEND="local",
        EMBEDDING_EVENT_LINK_MIN=0.75,
        CLUSTER_MERGE_HOURS=168,
    )
    with patch(
        "src.ingest_cluster.fetch_embeddings_batch",
        new=AsyncMock(return_value=[vec, vec]),
    ):
        out = await merge_clusters_by_embedding([c1, c2], settings, max_span_hours=168.0)
    assert len(out) == 1
    assert len(out[0]) == 2


def test_merge_clusters_skips_when_embedding_disabled() -> None:
    asyncio.run(_test_merge_clusters_skips_when_embedding_disabled())


async def _test_merge_clusters_skips_when_embedding_disabled() -> None:
    c1 = [_FakePrepared("A", "text")]
    c2 = [_FakePrepared("B", "text")]
    settings = Settings(EMBEDDING_ENABLED=False)
    out = await merge_clusters_by_embedding([c1, c2], settings)
    assert len(out) == 2


def test_merge_clusters_respects_time_span() -> None:
    asyncio.run(_test_merge_clusters_respects_time_span())


async def _test_merge_clusters_respects_time_span() -> None:
    vec_a = [1.0, 0.0]
    vec_b = [1.0, 0.0]
    c1 = [_FakePrepared("ACSL A", "story", "2026-01-01T00:00:00+00:00")]
    c2 = [_FakePrepared("ACSL B", "story", "2026-06-01T00:00:00+00:00")]
    settings = Settings(
        EMBEDDING_ENABLED=True,
        EMBEDDING_BACKEND="local",
        EMBEDDING_EVENT_LINK_MIN=0.75,
        CLUSTER_MERGE_HOURS=24,
    )
    with patch(
        "src.ingest_cluster.fetch_embeddings_batch",
        new=AsyncMock(return_value=[vec_a, vec_b]),
    ):
        out = await merge_clusters_by_embedding([c1, c2], settings, max_span_hours=24.0)
    assert len(out) == 2
