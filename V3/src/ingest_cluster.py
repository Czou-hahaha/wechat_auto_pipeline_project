"""Batch embedding: reprint merge (high cosine) + event linking (mid cosine), then cluster lists."""
from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from typing import Any

import httpx

from src.config import Settings
from src.embed_dedupe import (
    cosine_similarity,
    dedupe_by_embedding_greedy,
    fetch_embeddings_batch,
    truncate_for_embedding,
)

logger = logging.getLogger(__name__)


class _UF:
    __slots__ = ("p",)

    def __init__(self, n: int) -> None:
        self.p = list(range(n))

    def find(self, x: int) -> int:
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[rb] = ra


def _embedding_gate(settings: Settings) -> bool:
    if not settings.embedding_cluster_enabled or not settings.embedding_enabled:
        return False
    backend = (settings.embedding_backend or "local").strip().lower()
    if backend == "local":
        return True
    return bool((settings.embedding_api_key or "").strip())


def _iso_sort_key(published_at: str) -> str:
    return (published_at or "").strip() or "9999-12-31T99:99:99"


def _article_url(item: Any) -> str:
    hit = getattr(item, "hit", None)
    if hit is not None:
        u = getattr(hit, "url", "") or ""
        if u:
            return str(u)
    return str(getattr(item, "final_url", "") or getattr(item, "url", "") or "")


def _article_title(item: Any) -> str:
    t = getattr(item, "title", "") or ""
    if t:
        return str(t)
    hit = getattr(item, "hit", None)
    if hit is not None:
        return str(getattr(hit, "title", "") or "")
    return ""


@dataclass
class EmbeddingClusterReport:
    """可 JSON 落盘的聚类/去重说明（与 ``build_embedding_event_clusters`` 同源）。"""

    input_count: int = 0
    embedding_model: str = ""
    reprint_threshold: float = 0.9
    event_link_min: float = 0.75
    reprint_groups: int = 0
    reprint_dropped: int = 0
    # 转载合并：保留 earliest 的 canonical，其余为 dropped
    reprint_merges: list[dict[str, Any]] = field(default_factory=list)
    # 同事件连边（canonical 之间，余弦 ∈ [event_link_min, reprint_threshold)）
    event_link_edges: list[dict[str, Any]] = field(default_factory=list)
    # 便于人工扫：余弦 ≥ preview_min 的无向对（含转载对与事件对）
    similarity_pairs: list[dict[str, Any]] = field(default_factory=list)
    preview_min_cosine: float = 0.55
    event_count: int = 0
    # 每个事件一条：canonical URLs 顺序 + 条数
    events: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


async def build_embedding_event_clusters_with_report(
    items: list[Any],
    settings: Settings,
    *,
    similarity_preview_min: float = 0.55,
) -> tuple[list[list[Any]], int, EmbeddingClusterReport] | None:
    """
    与 ``build_embedding_event_clusters`` 相同聚类逻辑，额外返回 ``EmbeddingClusterReport``。
    """
    if not _embedding_gate(settings) or not items:
        return None
    n = len(items)
    report = EmbeddingClusterReport(
        input_count=n,
        embedding_model=(settings.embedding_model or "").strip(),
        reprint_threshold=float(settings.embedding_reprint_threshold),
        event_link_min=float(settings.embedding_event_link_min),
        preview_min_cosine=float(similarity_preview_min),
    )
    inputs = [
        truncate_for_embedding(
            f"{getattr(it, 'title', '') or ''}\n{getattr(it, 'text', '') or ''}",
            int(settings.embedding_max_input_chars),
        )
        for it in items
    ]
    embeddings: list[list[float] | None] = [None] * n
    bs = max(1, int(settings.embedding_batch_size))
    t_high = float(settings.embedding_reprint_threshold)
    t_low = float(settings.embedding_event_link_min)
    if t_low >= t_high:
        logger.warning(
            "embedding_event_link_min (%.4f) >= embedding_reprint_threshold (%.4f); widen reprint threshold",
            t_low,
            t_high,
        )
        t_low = min(t_low, t_high - 0.01)
        report.event_link_min = t_low

    try:
        async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as client:
            pos = 0
            while pos < n:
                chunk = inputs[pos : pos + bs]
                be = (settings.embedding_backend or "local").strip().lower()
                sub_client = client if be == "http" else None
                part = await fetch_embeddings_batch(
                    settings=settings,
                    inputs=chunk,
                    client=sub_client,
                )
                for j, vec in enumerate(part):
                    if pos + j < n:
                        embeddings[pos + j] = vec
                pos += bs
    except Exception:
        logger.exception("embedding cluster: fetch failed")
        return None

    if not any(v is not None for v in embeddings):
        logger.warning("embedding cluster: no vectors returned, fallback to legacy clustering")
        return None

    for i in range(n):
        vi = embeddings[i]
        if vi is None:
            continue
        for j in range(i + 1, n):
            vj = embeddings[j]
            if vj is None:
                continue
            sim = cosine_similarity(vi, vj)
            if sim >= similarity_preview_min:
                report.similarity_pairs.append(
                    {
                        "index_a": i,
                        "index_b": j,
                        "cosine": round(sim, 5),
                        "url_a": _article_url(items[i]),
                        "url_b": _article_url(items[j]),
                        "title_a": (_article_title(items[i]) or "")[:120],
                        "title_b": (_article_title(items[j]) or "")[:120],
                    }
                )

    uf_r = _UF(n)
    for i in range(n):
        vi = embeddings[i]
        if vi is None:
            continue
        for j in range(i + 1, n):
            vj = embeddings[j]
            if vj is None:
                continue
            sim = cosine_similarity(vi, vj)
            if sim >= t_high:
                uf_r.union(i, j)

    roots: dict[int, list[int]] = defaultdict(list)
    for i in range(n):
        roots[uf_r.find(i)].append(i)

    report.reprint_groups = len(roots)
    canon_orig: list[int] = []
    for _root, idxs in roots.items():
        idxs_sorted = sorted(idxs, key=lambda ii: _iso_sort_key(getattr(items[ii], "source_published_at", "") or ""))
        kept_i = idxs_sorted[0]
        canon_orig.append(kept_i)
        for drop_i in idxs_sorted[1:]:
            sim = cosine_similarity(embeddings[kept_i], embeddings[drop_i])
            report.reprint_merges.append(
                {
                    "kept_url": _article_url(items[kept_i]),
                    "dropped_url": _article_url(items[drop_i]),
                    "cosine": round(sim, 5),
                    "kept_title": (_article_title(items[kept_i]) or "")[:160],
                    "dropped_title": (_article_title(items[drop_i]) or "")[:160],
                }
            )
            report.reprint_dropped += 1

    m = len(canon_orig)
    if m == 0:
        return None

    uf_e = _UF(m)
    for a in range(m):
        va = embeddings[canon_orig[a]]
        if va is None:
            continue
        for b in range(a + 1, m):
            vb = embeddings[canon_orig[b]]
            if vb is None:
                continue
            sim = cosine_similarity(va, vb)
            if t_low <= sim < t_high:
                uf_e.union(a, b)
                report.event_link_edges.append(
                    {
                        "url_a": _article_url(items[canon_orig[a]]),
                        "url_b": _article_url(items[canon_orig[b]]),
                        "cosine": round(sim, 5),
                        "title_a": (_article_title(items[canon_orig[a]]) or "")[:120],
                        "title_b": (_article_title(items[canon_orig[b]]) or "")[:120],
                    }
                )

    event_buckets: dict[int, list[Any]] = defaultdict(list)
    for j in range(m):
        event_buckets[uf_e.find(j)].append(items[canon_orig[j]])

    clusters = list(event_buckets.values())
    report.event_count = len(clusters)
    for ei, cl in enumerate(clusters):
        report.events.append(
            {
                "event_index": ei,
                "member_count": len(cl),
                "members": [
                    {
                        "url": _article_url(p),
                        "title": (_article_title(p) or "")[:200],
                        "text_chars": len(getattr(p, "text", "") or ""),
                    }
                    for p in cl
                ],
            }
        )

    logger.info(
        "embedding_cluster: items=%d reprint_groups=%d events=%d dropped_reprints=%d",
        n,
        len(roots),
        len(clusters),
        report.reprint_dropped,
    )
    return clusters, report.reprint_dropped, report


async def build_embedding_event_clusters(
    items: list[Any],
    settings: Settings,
) -> tuple[list[list[Any]], int] | None:
    """
    Reprint merge: cosine >= ``embedding_reprint_threshold`` → one canonical per group.
    Event link: ``embedding_event_link_min`` <= cosine < reprint threshold → same event cluster.

    Returns ``(clusters, reprint_dropped_count)`` or ``None`` to signal caller to use legacy path.
    """
    out = await build_embedding_event_clusters_with_report(items, settings)
    if out is None:
        return None
    clusters, dropped, _report = out
    return clusters, dropped


async def dedupe_prepared_by_embedding_only(
    items: list[Any],
    settings: Settings,
) -> tuple[list[Any], int] | None:
    """
    Single-threshold greedy dedupe (same semantics as ``tests/integration/run_fetch_embed_dedupe``), for optional reuse.
    Returns ``(kept_items, dropped_count)`` or ``None`` if disabled / failed.
    """
    if not _embedding_gate(settings) or not items:
        return None
    n = len(items)
    inputs = [
        truncate_for_embedding(
            f"{getattr(it, 'title', '') or ''}\n{getattr(it, 'text', '') or ''}",
            int(settings.embedding_max_input_chars),
        )
        for it in items
    ]
    embeddings: list[list[float] | None] = [None] * n
    bs = max(1, int(settings.embedding_batch_size))
    thr = float(settings.embedding_dedupe_threshold)
    try:
        async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as client:
            pos = 0
            while pos < n:
                chunk = inputs[pos : pos + bs]
                be = (settings.embedding_backend or "local").strip().lower()
                sub_client = client if be == "http" else None
                part = await fetch_embeddings_batch(
                    settings=settings,
                    inputs=chunk,
                    client=sub_client,
                )
                for j, vec in enumerate(part):
                    if pos + j < n:
                        embeddings[pos + j] = vec
                pos += bs
    except Exception:
        logger.exception("embedding dedupe: fetch failed")
        return None
    if not any(v is not None for v in embeddings):
        return None
    kept_idx, dropped_pairs = dedupe_by_embedding_greedy(embeddings, threshold=thr)
    kept_set = set(kept_idx)
    kept = [items[i] for i in range(n) if i in kept_set]
    return kept, len(dropped_pairs)
