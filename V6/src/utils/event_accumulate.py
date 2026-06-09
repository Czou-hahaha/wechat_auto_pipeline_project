"""入库累增：新簇优先并入库内已有 event（同题合作新闻不重复建 event）。"""
from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Any, TYPE_CHECKING

import httpx

from src.embed_dedupe import cosine_similarity, fetch_embeddings_batch, truncate_for_embedding
from src.ingest_cluster import _cluster_representative, _embedding_available

if TYPE_CHECKING:
    from src.config import Settings
    from src.storage import JsonStore

logger = logging.getLogger(__name__)

_ENTITY_STOP = frozenset(
    "the and for with from that this will have been are was has into over new".split()
)
_CJK_STOP = frozenset("的与及等在是了为以将并而于对中")


def _prepared_text(item: Any) -> str:
    title = str(getattr(item, "title", "") or "")
    body = str(getattr(item, "text", "") or getattr(item, "extracted_text", "") or "")
    return truncate_for_embedding(f"{title}\n{body}", 4000)


def _article_row_text(row: dict[str, Any]) -> str:
    title = str(row.get("title") or "")
    body = str(row.get("extracted_text") or row.get("summary") or "")
    return truncate_for_embedding(f"{title}\n{body}", 4000)


def _parse_iso(raw: str) -> datetime | None:
    s = (raw or "").strip()
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def _span_hours(
    cluster: list[Any],
    existing_rows: list[dict[str, Any]],
    *,
    event: dict[str, Any] | None = None,
) -> float:
    times: list[datetime] = []
    for p in cluster:
        t = _parse_iso(str(getattr(p, "source_published_at", "") or ""))
        if t:
            times.append(t)
    for row in existing_rows:
        t = _parse_iso(str(row.get("source_published_at") or ""))
        if t:
            times.append(t)
    if event:
        t = _parse_iso(str(event.get("created_at") or ""))
        if t:
            times.append(t)
    if len(times) < 2:
        return 0.0
    return (max(times) - min(times)).total_seconds() / 3600.0


def _title_tokens(text: str) -> set[str]:
    """英文按词、中文按连续字串的 2-gram，避免整句中文被当成单一 token。"""
    out: set[str] = set()
    for m in re.finditer(r"[A-Za-z][A-Za-z0-9\-]{2,}", text or ""):
        low = m.group().lower()
        if low in _ENTITY_STOP:
            continue
        out.add(low)
    for m in re.finditer(r"[\u4e00-\u9fff]+", text or ""):
        run = m.group()
        if len(run) >= 2:
            for i in range(len(run) - 1):
                gram = run[i : i + 2]
                if gram not in _CJK_STOP:
                    out.add(gram)
    return out


def _title_overlap(a: str, b: str) -> float:
    ta, tb = _title_tokens(a), _title_tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / max(len(ta | tb), 1)


def _event_title_blob(event: dict[str, Any], articles: list[dict[str, Any]]) -> str:
    parts = [
        str(event.get("title") or ""),
        str(event.get("title_zh") or ""),
        str(event.get("headline_zh") or ""),
        str(event.get("summary") or "")[:1200],
        str(event.get("event_press_zh") or "")[:2000],
    ]
    for row in articles[:6]:
        parts.append(str(row.get("title") or ""))
    return "\n".join(p for p in parts if p.strip())


def _event_rep_text(event: dict[str, Any], articles: list[dict[str, Any]]) -> str:
    if articles:
        ev_rep = min(
            articles,
            key=lambda r: str(r.get("source_published_at") or "") or "9999-12-31T99:99:99",
        )
        return _article_row_text(ev_rep)
    return truncate_for_embedding(_event_title_blob(event, []), 4000)


def _cluster_url_fingerprints(cluster: list[Any]) -> set[str]:
    from src.storage import JsonStore

    fps: set[str] = set()
    for p in cluster:
        for raw in (
            str(getattr(p, "final_url", "") or ""),
            str(getattr(getattr(p, "hit", None), "url", "") or ""),
        ):
            fp = JsonStore.url_fingerprint(raw)
            if fp:
                fps.add(fp)
    return fps


def existing_event_by_urls(
    store: "JsonStore", cluster: list[Any]
) -> str | None:
    """任一新稿 URL 已在库中（articles 或 event_article_map）且带 event_id → 归入该 event。"""
    from src.storage import JsonStore

    fps = _cluster_url_fingerprints(cluster)
    if not fps:
        return None

    for row in store._read():
        if not isinstance(row, dict):
            continue
        eid = str(row.get("event_id") or "").strip()
        if not eid:
            continue
        for raw in (
            str(row.get("resolved_url") or ""),
            str(row.get("source_url") or ""),
        ):
            if JsonStore.url_fingerprint(raw) in fps:
                return eid

    for m in store._read_event_map():
        if not isinstance(m, dict):
            continue
        eid = str(m.get("event_id") or "").strip()
        if not eid:
            continue
        for raw in (
            str(m.get("resolved_url") or ""),
            str(m.get("source_url") or ""),
        ):
            if JsonStore.url_fingerprint(raw) in fps:
                return eid
    return None


async def match_existing_event_id(
    *,
    cluster: list[Any],
    store: "JsonStore",
    settings: "Settings",
) -> str | None:
    """
    为待入库簇匹配库内 event：URL 命中优先，否则向量/标题重叠（同窗 ``cluster_merge_hours``）。
    """
    if not cluster:
        return None

    by_url = existing_event_by_urls(store, cluster)
    if by_url:
        logger.info(
            "event accumulate: url hit existing=%s cluster_size=%d",
            by_url[:13],
            len(cluster),
        )
        return by_url

    events = [e for e in store.list_events() if isinstance(e, dict) and e.get("id")]
    if not events:
        return None

    rep = _cluster_representative(cluster)
    cluster_title = " ".join(
        str(getattr(p, "title", "") or "") for p in cluster[:4]
    )
    span_limit = float(settings.cluster_merge_hours)
    t_link = float(settings.embedding_event_link_min)
    title_min_overlap = 0.32

    candidates: list[tuple[str, list[dict[str, Any]], str, str, dict[str, Any]]] = []
    for ev in events:
        eid = str(ev.get("id") or "").strip()
        if not eid:
            continue
        rows = store.articles_for_event(eid)
        map_rows = store.map_entries_for_event(eid)
        if not rows and not map_rows and not _event_title_blob(ev, []):
            continue
        candidates.append(
            (
                eid,
                rows,
                _event_rep_text(ev, rows),
                _event_title_blob(ev, rows),
                ev,
            )
        )

    if not candidates:
        return None

    best_id = ""
    best_sim = 0.0
    best_overlap = 0.0

    if _embedding_available(settings):
        texts = [_prepared_text(rep)] + [c[2] for c in candidates]
        embeddings: list[list[float] | None] = [None] * len(texts)
        bs = max(1, int(settings.embedding_batch_size))
        try:
            async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as client:
                pos = 0
                while pos < len(texts):
                    chunk = texts[pos : pos + bs]
                    be = (settings.embedding_backend or "local").strip().lower()
                    sub_client = client if be == "http" else None
                    part = await fetch_embeddings_batch(
                        settings=settings,
                        inputs=chunk,
                        client=sub_client,
                    )
                    for j, vec in enumerate(part):
                        if pos + j < len(texts):
                            embeddings[pos + j] = vec
                    pos += bs
        except Exception:
            logger.exception("event accumulate: embedding failed")
            embeddings = [None] * len(texts)

        v0 = embeddings[0]
        if v0 is not None:
            for i, (eid, rows, _txt, ev_titles, ev) in enumerate(candidates):
                vi = embeddings[i + 1]
                if vi is None:
                    continue
                sim = cosine_similarity(v0, vi)
                overlap = _title_overlap(cluster_title, ev_titles)
                if sim < t_link and overlap < title_min_overlap:
                    continue
                if _span_hours(cluster, rows, event=ev) > span_limit:
                    continue
                score = sim * 0.85 + overlap * 0.15
                if score > best_sim or (score == best_sim and overlap > best_overlap):
                    best_sim = score
                    best_overlap = overlap
                    best_id = eid

    if not best_id:
        for eid, rows, _txt, ev_titles, ev in candidates:
            overlap = _title_overlap(cluster_title, ev_titles)
            if overlap < title_min_overlap:
                continue
            if _span_hours(cluster, rows, event=ev) > span_limit:
                continue
            if overlap > best_overlap:
                best_overlap = overlap
                best_id = eid

    if best_id:
        logger.info(
            "event accumulate: matched existing=%s cosine=%.3f title_overlap=%.3f cluster_size=%d",
            best_id[:13],
            best_sim,
            best_overlap,
            len(cluster),
        )
    return best_id or None


def urls_already_in_event(store: "JsonStore", event_id: str) -> set[str]:
    from src.storage import JsonStore

    out: set[str] = set()
    for row in store.articles_for_event(event_id):
        for raw in (
            str(row.get("resolved_url") or ""),
            str(row.get("source_url") or ""),
        ):
            fp = JsonStore.url_fingerprint(raw)
            if fp:
                out.add(fp)
    for m in store.map_entries_for_event(event_id):
        for raw in (
            str(m.get("resolved_url") or ""),
            str(m.get("source_url") or ""),
        ):
            fp = JsonStore.url_fingerprint(raw)
            if fp:
                out.add(fp)
    return out
