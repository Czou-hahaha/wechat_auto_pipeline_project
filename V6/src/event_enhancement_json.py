"""
事件增强 — **仅 JSON / 无 PostgreSQL** 路径。

当 ``EVENT_ENHANCEMENT_DATABASE_URL`` 未配置时，由 ``event_enhancement_workflow.run_event_enhancement_post_pipeline``
调用本模块：复用与 PG 模式相同的 **GDELT DOC → 抓正文 → bge-m3 嵌入 → 与事件成员向量 bank 比余弦门槛**（见 ``expansion.yaml``）；
中文 event 跳过 GDELT；英文 event 使用简短纯文本 query；GDELT 请求全进程串行限速，event 扩搜串行。

运行结束后在 ``<DATA_DIR>/event_enhancement_last_run.json`` 写入结构化结果（含满足相似度并写入库的 URL 列表）。
"""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

import httpx
import numpy as np
from zoneinfo import ZoneInfo

if TYPE_CHECKING:
    from event_enhancement.config_expansion import ExpansionConfig
    from event_enhancement.gdelt.client import GdeltAsyncClient

    from src.config import Settings
    from src.storage import JsonStore

logger = logging.getLogger(__name__)


def _write_last_run_json(store: "JsonStore", payload: dict[str, Any]) -> Path:
    path = store.data_dir / "event_enhancement_last_run.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("event enhancement json: wrote %s", path)
    return path


def _url_roles_for_event(store: "JsonStore", event_id: str) -> dict[str, str]:
    roles: dict[str, str] = {}
    for row in store._read_event_map():  # noqa: SLF001
        if not isinstance(row, dict) or str(row.get("event_id") or "").strip() != event_id:
            continue
        role = str(row.get("role") or "").strip().lower()
        for k in ("resolved_url", "source_url"):
            u = str(row.get(k) or "").strip()
            if u and role:
                roles[u] = role
    return roles


def _members_with_roles(members: list[dict], url_roles: dict[str, str]) -> list[dict]:
    out: list[dict] = []
    for m in members:
        if not isinstance(m, dict):
            continue
        row = dict(m)
        for k in ("resolved_url", "source_url"):
            u = str(row.get(k) or "").strip()
            if u and u in url_roles:
                row["map_role"] = url_roles[u]
                break
        out.append(row)
    return out


async def _score_candidate_hit(
    h: Any,
    *,
    fetch_client: httpx.AsyncClient,
    exp: "ExpansionConfig",
    enh_ns: SimpleNamespace,
    bank: np.ndarray,
    threshold: float,
    existing_urls: set[str],
    seen_urls_global: set[str],
    fetch_sem: asyncio.Semaphore,
) -> tuple[float, Any, str, str, str, str, np.ndarray] | None:
    url = str(getattr(h, "url", "") or "").strip()
    if not url or url in existing_urls:
        return None
    async with fetch_sem:
        try:
            from event_enhancement.extract.article_body import (
                extract_body_trafilatura,
                fetch_html_text_with_effective_url,
            )

            html, page_eff = await fetch_html_text_with_effective_url(
                fetch_client,
                url,
                timeout_sec=exp.http_fetch_timeout_sec,
            )
        except Exception as exc:
            logger.debug("fetch failed url=%s err=%s", url[:80], exc)
            return None
    store_url = (page_eff or url).strip()
    if store_url in existing_urls:
        return None
    body = extract_body_trafilatura(
        html,
        page_url=page_eff or url,
        min_chars=exp.trafilatura_min_chars,
    )
    if not body:
        return None
    title = str(getattr(h, "title", "") or "").strip() or "未命名"
    from event_enhancement.embed import bge_m3
    from event_enhancement.similarity.faiss_filter import max_cosine_vs_bank

    cand_text = f"{title}\n{body}"[: exp.embedding_max_input_chars]
    cvecs = await bge_m3.encode_texts([cand_text], enh_ns.embedding_model_id)
    if not cvecs:
        return None
    cvec = np.asarray(cvecs[0], dtype=np.float32).reshape(-1)
    sim = max_cosine_vs_bank(cvec, bank)
    if sim <= threshold:
        return None
    return (float(sim), h, url, store_url, title, body, cvec)


async def _enhance_one_event_json(
    *,
    eid: str,
    members: list[dict],
    ev: dict,
    store: "JsonStore",
    exp: "ExpansionConfig",
    enh_ns: SimpleNamespace,
    gdelt_client: "GdeltAsyncClient",
    fetch_client: httpx.AsyncClient,
    url_roles: dict[str, str],
    store_lock: asyncio.Lock,
) -> dict[str, Any]:
    from event_enhancement.embed import bge_m3
    from event_enhancement.expansion_cascade import expansion_sources_for_event_lang, fetch_expansion_source_hits
    from event_enhancement.gdelt.query import build_expansion_plain_phrase, gdelt_query_from_plain
    from event_enhancement.lang_detect import detect_event_expansion_lang
    from event_enhancement.scoring.importance import host_from_url
    from src.storage import ArticleRecord

    row: dict[str, Any] = {
        "event_id": eid,
        "event_title": str(ev.get("title") or "")[:200],
        "seed_article_count": len(members),
    }
    cap = max(1, int(exp.max_articles_per_event))
    if len(members) >= cap:
        row["status"] = "skipped"
        row["reason"] = "event_article_cap_reached"
        row["urls_added_to_store"] = []
        row["urls_passed_similarity"] = []
        row["gdelt_candidate_urls"] = []
        logger.info(
            "event enhancement json skip cap event=%s members=%d max=%d",
            eid[:13],
            len(members),
            cap,
        )
        return row

    slots = cap - len(members)
    event_title = str(ev.get("title") or "").strip() or "未命名事件"
    members_lang = _members_with_roles(members, url_roles)
    event_lang = detect_event_expansion_lang(
        event_title=event_title,
        member_articles=members_lang,
        cjk_threshold=float(exp.expansion_event_lang_cjk_ratio),
    )
    plain = build_expansion_plain_phrase(
        event_title=event_title,
        anchor_terms=list(exp.anchor_terms),
        event_title_max_chars=exp.gdelt_event_title_max_chars,
        primary_anchor=exp.gdelt_primary_anchor,
        event_lang=event_lang,
        max_english_words=int(exp.gdelt_event_title_max_words_en),
    )
    sources_order = expansion_sources_for_event_lang(event_lang, exp)
    gdelt_skipped = event_lang == "zh"
    gdelt_q = "" if gdelt_skipped else gdelt_query_from_plain(plain, lang=event_lang)

    row["gdelt_query_profile"] = {
        "plain_phrase": plain,
        "event_lang": event_lang,
        "gdelt_skipped": gdelt_skipped,
        "gdelt_query": gdelt_q,
        "search_cascade": list(sources_order),
        "search_attempts_per_source": exp.search_attempts_per_source,
        "expansion_search_cascade": exp.expansion_search_cascade,
        "web_search_backend": exp.web_search_backend,
        "gdelt_primary_anchor": exp.gdelt_primary_anchor,
        "event_title_max_chars": exp.gdelt_event_title_max_chars,
        "event_title_max_words_en": exp.gdelt_event_title_max_words_en,
        "include_member_titles": exp.gdelt_query_include_member_titles,
        "max_or_terms": exp.gdelt_query_max_or_terms,
        "expansion_event_lang_cjk_ratio": exp.expansion_event_lang_cjk_ratio,
    }
    row["queries"] = [gdelt_q] if gdelt_q else []
    source_trace: list[dict] = []
    row["source_trace"] = source_trace

    texts: list[str] = []
    for m in members:
        t = str(m.get("title") or "").strip()
        body = str(m.get("extracted_text") or "")
        blob = f"{t}\n{body}"[: exp.embedding_max_input_chars]
        texts.append(blob)
    if not any((x or "").strip() for x in texts):
        row["status"] = "skipped"
        row["reason"] = "no_text_for_embedding"
        row["urls_added_to_store"] = []
        row["urls_passed_similarity"] = []
        row["gdelt_candidate_urls"] = []
        return row

    vecs = await bge_m3.encode_texts(texts, enh_ns.embedding_model_id)
    if not vecs:
        row["status"] = "skipped"
        row["reason"] = "embedding_empty"
        row["urls_added_to_store"] = []
        row["urls_passed_similarity"] = []
        row["gdelt_candidate_urls"] = []
        return row
    bank = np.stack([np.asarray(v, dtype=np.float32).reshape(-1) for v in vecs], axis=0)
    if bank.size == 0:
        row["status"] = "skipped"
        row["reason"] = "no_embedding_bank"
        row["urls_added_to_store"] = []
        row["urls_passed_similarity"] = []
        row["gdelt_candidate_urls"] = []
        return row

    seen_urls_global: set[str] = set()
    uniq: list[Any] = []
    existing_urls: set[str] = set()
    for m in members:
        for k in ("source_url", "resolved_url"):
            u = str(m.get(k) or "").strip()
            if u:
                existing_urls.add(u)

    threshold = float(exp.similarity_threshold)
    inserted = 0
    passed_detail: list[dict[str, Any]] = []
    added_urls: list[str] = []
    now_iso = datetime.now(timezone.utc).isoformat()
    dom_key = str(ev.get("dominant_topic_key") or "").strip()
    fetch_sem = asyncio.Semaphore(max(1, int(exp.expansion_fetch_concurrency)))

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

        batch_hits: list[Any] = []
        for h in hits:
            u = str(getattr(h, "url", "") or "").strip()
            if not u or u in seen_urls_global:
                continue
            seen_urls_global.add(u)
            uniq.append(h)
            batch_hits.append(h)

        scored = await asyncio.gather(
            *[
                _score_candidate_hit(
                    h,
                    fetch_client=fetch_client,
                    exp=exp,
                    enh_ns=enh_ns,
                    bank=bank,
                    threshold=threshold,
                    existing_urls=existing_urls,
                    seen_urls_global=seen_urls_global,
                    fetch_sem=fetch_sem,
                )
                for h in batch_hits
            ]
        )

        pending_rows: list[tuple[float, Any, str, str, str, str, np.ndarray]] = []
        pending_store_urls: set[str] = set()
        for item in scored:
            if item is None:
                continue
            sim, h, url, store_url, title, body, cvec = item
            if store_url in pending_store_urls:
                continue
            pending_store_urls.add(store_url)
            pending_rows.append((sim, h, url, store_url, title, body, cvec))

        pending_rows.sort(key=lambda r: r[0])

        for sim, h, url, store_url, title, body, cvec in pending_rows:
            if inserted >= slots:
                break
            if url in existing_urls or store_url in existing_urls:
                continue
            passed_detail.append(
                {
                    "url": store_url,
                    "source_hit": url,
                    "similarity": round(float(sim), 4),
                    "title": title[:160],
                }
            )
            art_id = str(uuid.uuid4())
            host = host_from_url(store_url)
            rec = ArticleRecord(
                id=art_id,
                title=title,
                source_url=url,
                source_published_at="",
                extracted_text=body,
                summary="【事件增强·JSON 模式】补充来源，待人工复核或重新摘要。",
                status="event_enhancement",
                created_at=now_iso,
                published_at="",
                source_published_at_date_only=False,
                resolved_url=store_url,
                source_host=host,
                topic_key=dom_key,
                topic_category="",
                topic_is_important=False,
                topic_source_count=0,
                deepseek_semantic_decision="",
                novelty_passed=False,
                wechat_draft_pushed_at="",
                cluster_size=0,
                synthesis_multi_source=True,
                event_id=eid,
                summary_zh="",
                expansion_similarity=float(sim),
            )
            async with store_lock:
                store.add(rec)
                store.append_event_article_map(
                    [
                        {
                            "event_id": eid,
                            "source_url": url,
                            "resolved_url": store_url,
                            "role": "support",
                        }
                    ]
                )
            existing_urls.add(url)
            existing_urls.add(store_url)
            bank = np.concatenate([bank, cvec.reshape(1, -1)], axis=0)
            inserted += 1
            added_urls.append(store_url)

        if inserted > 0:
            break

    row["gdelt_candidate_urls"] = [str(getattr(x, "url", "") or "") for x in uniq]
    row["status"] = "success"
    row["urls_passed_similarity"] = passed_detail
    row["urls_added_to_store"] = added_urls
    row["candidates_fetched"] = len(uniq)
    row["articles_inserted"] = inserted
    row["similarity_threshold"] = threshold
    row["event_lang"] = event_lang
    logger.info(
        "event enhancement json event=%s lang=%s inserted=%d fetched=%d",
        eid[:13],
        event_lang,
        inserted,
        len(uniq),
    )
    return row


async def run_event_enhancement_json_pipeline(store: "JsonStore", settings: "Settings") -> list[dict[str, Any]]:
    from event_enhancement.config_expansion import ExpansionConfig
    from event_enhancement.embed import bge_m3
    from event_enhancement.gdelt.client import GdeltAsyncClient

    from src.event_enhancement_workflow import _enhancement_config_path, _ensure_package_path, _parse_iso_dt

    _ensure_package_path()
    cfg_path = _enhancement_config_path(settings)
    if not cfg_path.is_file():
        raise RuntimeError(f"事件增强配置缺失: {cfg_path}")
    exp = ExpansionConfig.from_path(cfg_path)

    enh_ns = SimpleNamespace(
        gdelt_base_url=(settings.gdelt_base_url or "").strip()
        or "https://api.gdeltproject.org/api/v2/doc/doc",
        embedding_model_id=(settings.embedding_model or "BAAI/bge-m3").strip(),
    )

    await bge_m3.encode_texts(["preload"], enh_ns.embedding_model_id)

    tz = ZoneInfo(exp.expansion_ranking_timezone)
    now_local = datetime.now(tz)
    cutoff_local = now_local - timedelta(hours=exp.expansion_ranking_window_hours)
    cutoff_utc = cutoff_local.astimezone(timezone.utc)

    events = store._read_events()  # noqa: SLF001
    articles = store.list_all()
    ev_by_id: dict[str, dict] = {}
    for e in events:
        if isinstance(e, dict) and str(e.get("id") or "").strip():
            ev_by_id[str(e["id"]).strip()] = e

    by_event: dict[str, list[dict]] = defaultdict(list)
    for a in articles:
        if not isinstance(a, dict):
            continue
        eid = str(a.get("event_id") or "").strip()
        if eid:
            by_event[eid].append(a)

    ranked: list[tuple[str, list[dict], dict, int]] = []
    for eid, members in by_event.items():
        ev = ev_by_id.get(eid)
        if not ev:
            continue
        created = _parse_iso_dt(str(ev.get("created_at") or ""))
        if created is not None and created.astimezone(timezone.utc) < cutoff_utc:
            continue
        ranked.append((eid, members, ev, len(members)))
    ranked.sort(key=lambda x: -x[3])
    targets = ranked[: max(1, int(exp.max_events_per_run))]

    url_roles_by_event: dict[str, dict[str, str]] = {
        eid: _url_roles_for_event(store, eid) for eid, _, _, _ in targets
    }

    event_sem = asyncio.Semaphore(1)
    store_lock = asyncio.Lock()
    timeout = httpx.Timeout(exp.http_fetch_timeout_sec)

    async def _run_target(eid: str, members: list[dict], ev: dict) -> dict[str, Any]:
        async with event_sem:
            return await _enhance_one_event_json(
                eid=eid,
                members=members,
                ev=ev,
                store=store,
                exp=exp,
                enh_ns=enh_ns,
                gdelt_client=gdelt_client,
                fetch_client=fetch_client,
                url_roles=url_roles_by_event.get(eid, {}),
                store_lock=store_lock,
            )

    out_logs: list[dict[str, Any]] = []
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True, trust_env=True) as fetch_client:
        cache_dir = Path(settings.data_dir) / "cache" / "gdelt"
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True, trust_env=False) as gdelt_http:
            gdelt_client = GdeltAsyncClient(
                settings=enh_ns,
                expansion=exp,
                http_client=gdelt_http,
                cache_dir=cache_dir,
            )
            for eid, members, ev, _ in targets:
                row = await _run_target(eid, members, ev)
                out_logs.append(row)

    payload: dict[str, Any] = {
        "mode": "json_store",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "max_articles_per_event": exp.max_articles_per_event,
        "expansion_event_concurrency": exp.expansion_event_concurrency,
        "expansion_fetch_concurrency": exp.expansion_fetch_concurrency,
        "events": out_logs,
    }
    _write_last_run_json(store, payload)
    return out_logs
