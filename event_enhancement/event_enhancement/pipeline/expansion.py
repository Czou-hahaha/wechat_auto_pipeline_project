"""Orchestration: refresh scores, pick top-N, GDELT, extract, embed, FAISS gate, persist.

扩搜单源内：先收集高于相似度阈值的候选，再按**余弦相似度升序**（优先与事件 bank 相对更远、仍达标）依次写入，直至达到每事件篇数上限。
中文 event 跳过 GDELT；英文 event 使用 ``sourcelang:english``。
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import httpx
import numpy as np
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from event_enhancement.config_expansion import ExpansionConfig
from event_enhancement.db.models import Article, Event, EventArticleMap, ExpansionLog
from event_enhancement.embed import bge_m3
from event_enhancement.extract.article_body import extract_body_trafilatura, fetch_html_text_with_effective_url
from event_enhancement.gdelt.client import GdeltAsyncClient
from event_enhancement.expansion_cascade import expansion_sources_for_event_lang, fetch_expansion_source_hits
from event_enhancement.gdelt.query import build_expansion_plain_phrase, gdelt_query_from_plain
from event_enhancement.lang_detect import detect_event_expansion_lang
from event_enhancement.gdelt.types import GdeltHit
from event_enhancement.scoring.importance import compute_importance_score, host_from_url
from event_enhancement.settings import Settings
from event_enhancement.similarity.faiss_filter import max_cosine_vs_bank

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _ranking_cutoff(exp: ExpansionConfig) -> datetime:
    tz = ZoneInfo(exp.expansion_ranking_timezone)
    now_local = datetime.now(tz)
    cutoff_local = now_local - timedelta(hours=exp.expansion_ranking_window_hours)
    return cutoff_local.astimezone(timezone.utc)


def _cooldown_cutoff(exp: ExpansionConfig) -> datetime | None:
    h = float(exp.expansion_min_interval_hours)
    if h <= 0:
        return None
    return _utcnow() - timedelta(hours=h)


async def load_events_in_ranking_window(session: AsyncSession, exp: ExpansionConfig) -> list[Event]:
    cutoff = _ranking_cutoff(exp)
    stmt = select(Event).where(
        func.coalesce(Event.first_seen_at, Event.created_at) >= cutoff,
    )
    res = await session.execute(stmt)
    return list(res.scalars().all())


async def refresh_importance_scores(
    session: AsyncSession,
    exp: ExpansionConfig,
) -> None:
    events = await load_events_in_ranking_window(session, exp)
    now = _utcnow()
    for ev in events:
        stmt = (
            select(EventArticleMap)
            .where(EventArticleMap.event_id == ev.id)
            .options(selectinload(EventArticleMap.article))
        )
        maps = (await session.execute(stmt)).scalars().all()
        arts = [m.article for m in maps if m.article is not None]
        hosts = [a.source_host for a in arts]
        titles = [a.title for a in arts]
        pats = [a.published_at for a in arts]
        score = compute_importance_score(
            event_title=ev.title,
            article_titles=titles,
            article_hosts=hosts,
            article_published_ats=pats,
            important_hosts=list(exp.important_hosts),
            keywords=list(exp.keywords),
            now=now,
        )
        ev.importance_score = int(score)
        ev.article_count = len(arts)
        ev.updated_at = now
    await session.flush()
    logger.info("refreshed importance for events count=%d", len(events))


async def select_events_for_expansion(
    session: AsyncSession,
    exp: ExpansionConfig,
    *,
    limit: int,
) -> list[uuid.UUID]:
    cutoff = _ranking_cutoff(exp)
    cd = _cooldown_cutoff(exp)
    stmt = select(Event.id).where(func.coalesce(Event.first_seen_at, Event.created_at) >= cutoff)
    if cd is not None:
        stmt = stmt.where(
            or_(
                Event.last_expansion_at.is_(None),
                Event.last_expansion_at < cd,
            )
        )
    stmt = stmt.order_by(Event.importance_score.desc()).limit(limit)
    res = await session.execute(stmt)
    return list(res.scalars().all())


async def _ensure_article_embedding(
    session: AsyncSession,
    article: Article,
    *,
    model_id: str,
    max_chars: int,
) -> np.ndarray | None:
    if article.embedding:
        return bge_m3.bytes_to_embedding(article.embedding)
    text = f"{article.title}\n{(article.body_text or '')}"[:max_chars]
    if not text.strip():
        return None
    vecs = await bge_m3.encode_texts([text], model_id)
    if not vecs:
        return None
    vec = vecs[0]
    article.embedding = bge_m3.embedding_to_bytes(vec)
    await session.flush()
    return vec


async def _event_embedding_bank(
    session: AsyncSession,
    event: Event,
    *,
    model_id: str,
    max_chars: int,
) -> np.ndarray:
    stmt = (
        select(EventArticleMap)
        .where(EventArticleMap.event_id == event.id)
        .options(selectinload(EventArticleMap.article))
    )
    maps = (await session.execute(stmt)).scalars().all()
    rows: list[np.ndarray] = []
    for m in maps:
        a = m.article
        if a is None:
            continue
        v = await _ensure_article_embedding(session, a, model_id=model_id, max_chars=max_chars)
        if v is not None:
            rows.append(v)
    if not rows:
        return np.zeros((0, 1), dtype=np.float32)
    return np.stack(rows, axis=0)


async def expand_one_event(
    session: AsyncSession,
    *,
    event: Event,
    settings: Settings,
    exp: ExpansionConfig,
    gdelt_client: GdeltAsyncClient,
    http_client: httpx.AsyncClient,
) -> ExpansionLog:
    now = _utcnow()
    log = ExpansionLog(
        id=uuid.uuid4(),
        event_id=event.id,
        started_at=now,
        status="started",
        reason=None,
        queries_json=None,
        candidates_fetched=0,
        candidates_passed_similarity=0,
        articles_inserted=0,
        error_detail=None,
    )
    session.add(log)
    await session.flush()

    try:
        stmt = (
            select(EventArticleMap)
            .where(EventArticleMap.event_id == event.id)
            .options(selectinload(EventArticleMap.article))
        )
        maps = (await session.execute(stmt)).scalars().all()
        member_titles = [m.article.title for m in maps if m.article is not None]

        initial_map_cnt = int(
            (
                await session.execute(
                    select(func.count()).select_from(EventArticleMap).where(EventArticleMap.event_id == event.id)
                )
            ).scalar_one()
        )
        cap = max(1, int(exp.max_articles_per_event))
        slots = max(0, cap - initial_map_cnt)
        if slots == 0:
            log.status = "skipped"
            log.reason = "event_article_cap_reached"
            log.finished_at = _utcnow()
            log.queries_json = {"queries": [], "cap": cap, "existing_maps": initial_map_cnt}
            await session.flush()
            logger.info(
                "expand_one_event skip cap: event=%s existing_maps=%d max=%d",
                event.id,
                initial_map_cnt,
                cap,
            )
            return log

        bank = await _event_embedding_bank(
            session,
            event,
            model_id=settings.embedding_model_id,
            max_chars=exp.embedding_max_input_chars,
        )
        if bank.shape[0] == 0:
            log.status = "skipped"
            log.reason = "no_embedding_bank"
            log.finished_at = _utcnow()
            log.queries_json = {"queries": []}
            await session.flush()
            return log

        member_rows: list[dict] = []
        for m in maps:
            if m.article is None:
                continue
            a = m.article
            member_rows.append(
                {
                    "title": a.title,
                    "extracted_text": a.body_text or "",
                    "status": a.status or "",
                    "map_role": (m.role or "").strip().lower(),
                }
            )
        event_lang = detect_event_expansion_lang(
            event_title=event.title or "",
            member_articles=member_rows,
            cjk_threshold=float(exp.expansion_event_lang_cjk_ratio),
        )
        plain = build_expansion_plain_phrase(
            event_title=event.title or "",
            anchor_terms=list(exp.anchor_terms),
            event_title_max_chars=exp.gdelt_event_title_max_chars,
            primary_anchor=exp.gdelt_primary_anchor,
            event_lang=event_lang,
            max_english_words=int(exp.gdelt_event_title_max_words_en),
        )
        sources_order = expansion_sources_for_event_lang(event_lang, exp)
        gdelt_skipped = event_lang == "zh"
        gdelt_q = "" if gdelt_skipped else gdelt_query_from_plain(plain, lang=event_lang)
        source_trace: list[dict] = []

        log.queries_json = {
            "plain_phrase": plain,
            "event_lang": event_lang,
            "gdelt_skipped": gdelt_skipped,
            "gdelt_query": gdelt_q,
            "search_cascade": list(sources_order),
            "search_attempts_per_source": exp.search_attempts_per_source,
            "expansion_search_cascade": exp.expansion_search_cascade,
            "web_search_backend": exp.web_search_backend,
            "gdelt_primary_anchor": exp.gdelt_primary_anchor,
            "max_articles_per_event": cap,
            "seed_map_count": initial_map_cnt,
            "insert_slots": slots,
            "gdelt_event_title_max_chars": exp.gdelt_event_title_max_chars,
            "gdelt_query_include_member_titles": exp.gdelt_query_include_member_titles,
            "source_trace": source_trace,
        }

        seen_urls_global: set[str] = set()
        uniq: list[GdeltHit] = []

        stmt_urls = (
            select(Article.url)
            .join(EventArticleMap, EventArticleMap.article_id == Article.id)
            .where(EventArticleMap.event_id == event.id)
        )
        existing = set((await session.execute(stmt_urls)).scalars().all())

        inserted = 0
        passed_sim = 0
        threshold = float(exp.similarity_threshold)
        fetch_sem = asyncio.Semaphore(max(1, int(exp.expansion_fetch_concurrency)))

        async def _score_pg_hit(h: GdeltHit) -> tuple[float, GdeltHit, str, str, np.ndarray] | None:
            if h.url in existing:
                return None
            async with fetch_sem:
                try:
                    html, page_eff = await fetch_html_text_with_effective_url(
                        http_client, h.url, timeout_sec=exp.http_fetch_timeout_sec
                    )
                except Exception as e:
                    logger.debug("fetch failed url=%s err=%s", h.url[:80], e)
                    return None
            store_url = (page_eff or h.url).strip()
            if store_url in existing:
                return None
            body = extract_body_trafilatura(
                html,
                page_url=page_eff or h.url,
                min_chars=exp.trafilatura_min_chars,
            )
            if not body:
                return None
            cand_text = f"{h.title}\n{body}"[: exp.embedding_max_input_chars]
            cvecs = await bge_m3.encode_texts([cand_text], settings.embedding_model_id)
            if not cvecs:
                return None
            cvec = np.asarray(cvecs[0], dtype=np.float32).reshape(-1)
            sim = max_cosine_vs_bank(cvec, bank)
            if sim <= threshold:
                return None
            return (float(sim), h, store_url, body, cvec)

        for src in sources_order:
            if inserted >= slots:
                break
            hits, meta = await fetch_expansion_source_hits(
                src,  # type: ignore[arg-type]
                plain_phrase=plain,
                gdelt_client=gdelt_client,
                exp=exp,
                event_lang=event_lang,
            )
            source_trace.append(meta)

            pending_rows: list[tuple[float, GdeltHit, str, str, np.ndarray]] = []
            pending_store_urls: set[str] = set()

            batch: list[GdeltHit] = []
            for h in hits:
                if h.url in seen_urls_global:
                    continue
                seen_urls_global.add(h.url)
                uniq.append(h)
                batch.append(h)

            scored = await asyncio.gather(*[_score_pg_hit(h) for h in batch])
            for item in scored:
                if item is None:
                    continue
                sim, h, store_url, body, cvec = item
                if store_url in pending_store_urls:
                    continue
                pending_store_urls.add(store_url)
                pending_rows.append((float(sim), h, store_url, body, cvec))

            pending_rows.sort(key=lambda row: row[0])
            passed_sim += len(pending_rows)

            for sim, h, store_url, body, cvec in pending_rows:
                if inserted >= slots:
                    break
                if h.url in existing or store_url in existing:
                    continue

                host = host_from_url(store_url)
                art = Article(
                    id=uuid.uuid4(),
                    url=store_url,
                    title=h.title or "未命名",
                    published_at=None,
                    body_text=body,
                    source_host=host,
                    source_tier="",
                    embedding=bge_m3.embedding_to_bytes(cvec),
                    source_url=h.url,
                    resolved_url=store_url,
                    summary=None,
                    summary_zh=None,
                    status="event_enhancement",
                    topic_key=(event.dominant_topic_key or "").strip() or None,
                )
                session.add(art)
                await session.flush()
                session.add(
                    EventArticleMap(
                        id=uuid.uuid4(),
                        event_id=event.id,
                        article_id=art.id,
                        role="support",
                        similarity_to_centroid=float(sim),
                    )
                )
                existing.add(store_url)
                existing.add(h.url)
                bank = await _event_embedding_bank(
                    session,
                    event,
                    model_id=settings.embedding_model_id,
                    max_chars=exp.embedding_max_input_chars,
                )
                inserted += 1

            if inserted > 0:
                break

        log.candidates_fetched = len(uniq)

        log.candidates_passed_similarity = passed_sim
        log.articles_inserted = inserted
        log.status = "success"
        log.finished_at = _utcnow()

        event.last_expansion_at = log.finished_at
        event.expansion_attempts = int(event.expansion_attempts or 0) + 1
        event.updated_at = log.finished_at
        stmt_cnt = select(func.count()).select_from(EventArticleMap).where(EventArticleMap.event_id == event.id)
        event.article_count = int((await session.execute(stmt_cnt)).scalar_one())
        await session.flush()
        return log
    except Exception as e:
        logger.exception("expand_one_event failed event_id=%s", event.id)
        log.status = "failed"
        log.finished_at = _utcnow()
        log.error_detail = str(e)[:4000]
        await session.flush()
        return log


async def run_expansion_batch(
    session: AsyncSession,
    *,
    settings: Settings,
    exp: ExpansionConfig,
) -> list[ExpansionLog]:
    await refresh_importance_scores(session, exp)
    await session.commit()

    limit = int(exp.max_events_per_run)
    targets = await select_events_for_expansion(session, exp, limit=limit)
    await session.commit()

    if not targets:
        logger.info("no events selected for expansion")
        return []

    timeout = httpx.Timeout(exp.http_fetch_timeout_sec)
    logs: list[ExpansionLog] = []
    # GDELT: bypass env HTTP(S)_PROXY — many proxies mishandle CONNECT/TLS to api.gdeltproject.org.
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True, trust_env=True) as fetch_client:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True, trust_env=False) as gdelt_http:
            gdelt_client = GdeltAsyncClient(
                settings=settings,
                expansion=exp,
                http_client=gdelt_http,
            )
            for eid in targets:
                async with session.begin():
                    ev = await session.get(Event, eid)
                    if ev is None:
                        continue
                    log = await expand_one_event(
                        session,
                        event=ev,
                        settings=settings,
                        exp=exp,
                        gdelt_client=gdelt_client,
                        http_client=fetch_client,
                    )
                    logs.append(log)
    return logs
