"""FastAPI BFF — read-only event intelligence API."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import Body, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from src.bff import config_api, schedule_config
from src.bff.event_mapper import event_to_intelligence, event_to_list_item
from src.config import Settings
from src.storage import JsonStore

app = FastAPI(title="Low-Altitude Intelligence BFF", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("BFF_CORS_ORIGINS", "http://localhost:3000").split(","),
    allow_credentials=True,
    allow_methods=["GET", "PUT", "POST", "OPTIONS"],
    allow_headers=["*"],
)


def _store() -> JsonStore:
    s = Settings()
    return JsonStore(Path(s.data_dir))


def _all_events_enriched(store: JsonStore) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for ev in store.list_events():
        if not isinstance(ev, dict):
            continue
        eid = str(ev.get("id") or "").strip()
        if not eid:
            continue
        articles = store.articles_for_event(eid)
        out.append(event_to_list_item(ev, articles))
    out.sort(key=lambda x: (-int(x.get("importance_score") or 0), x.get("createdAt") or ""))
    return out


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/events")
def list_events(
    q: str = "",
    keyword: str = "",
    min_importance: int = 0,
    sort: str = Query("importance", pattern="^(importance|recent|qa)$"),
) -> dict[str, Any]:
    store = _store()
    rows = _all_events_enriched(store)
    needle = (q or keyword or "").strip().lower()
    if needle:
        rows = [
            r
            for r in rows
            if needle in (r.get("title") or "").lower()
            or any(needle in (k or "").lower() for k in r.get("keywords") or [])
        ]
    if min_importance > 0:
        rows = [r for r in rows if int(r.get("importance_score") or 0) >= min_importance]
    if sort == "recent":
        rows.sort(key=lambda x: x.get("createdAt") or "", reverse=True)
    elif sort == "qa":
        rows.sort(key=lambda x: -int(x.get("qa_score") or 0))
    else:
        rows.sort(key=lambda x: -int(x.get("importance_score") or 0))
    return {"items": rows, "total": len(rows)}


@app.get("/api/events/{event_id}")
def get_event(event_id: str) -> dict[str, Any]:
    store = _store()
    ev = store.get_event(event_id)
    if not ev:
        raise HTTPException(status_code=404, detail="event not found")
    articles = store.articles_for_event(event_id)
    return event_to_intelligence(ev, articles)


@app.get("/api/dashboard")
def dashboard() -> dict[str, Any]:
    store = _store()
    events = store.list_events()
    today = datetime.now(timezone.utc).date().isoformat()
    today_new = sum(
        1
        for e in events
        if isinstance(e, dict) and str(e.get("created_at") or "").startswith(today)
    )
    enriched = _all_events_enriched(store)
    high = sorted(enriched, key=lambda x: -int(x.get("importance_score") or 0))[:5]
    qa_scores = [int(e.get("event_press_qa_score") or 0) for e in events if isinstance(e, dict) and e.get("event_press_qa_score")]
    avg_qa = round(sum(qa_scores) / len(qa_scores), 1) if qa_scores else 0.0
    rewrites = sum(int(e.get("event_press_qa_rewrite_attempts") or 0) for e in events if isinstance(e, dict))
    from collections import Counter

    cn, intl = 0, 0
    kw_counter: Counter[str] = Counter()
    for item in enriched:
        for c in item.get("countries") or []:
            if c == "CN":
                cn += 1
            else:
                intl += 1
        for k in item.get("keywords") or []:
            kw_counter[k] += 1
    trend = [
        {"date": f"2026-05-{10 + i}", "FAA": 12 + i * 2, "BVLOS": 8 + i, "eVTOL": 15 + i * 3}
        for i in range(7)
    ]
    return {
        "todayNewEvents": today_new,
        "highImportanceEvents": high,
        "hotKeywords": [{"keyword": k, "count": v} for k, v in kw_counter.most_common(8)],
        "regionSplit": {"domestic": cn, "international": intl},
        "topicTrend": trend,
        "aiRewriteCount": rewrites,
        "avgQaScore": avg_qa,
        "totalEvents": len(events),
    }


@app.get("/api/qa")
def qa_list(min_score: int = 0, max_score: int = 100) -> dict[str, Any]:
    store = _store()
    items: list[dict[str, Any]] = []
    for ev in store.list_events():
        if not isinstance(ev, dict):
            continue
        score = int(ev.get("event_press_qa_score") or 0)
        if score < min_score or score > max_score:
            continue
        if not ev.get("event_press_zh"):
            continue
        eid = str(ev.get("id") or "")
        articles = store.articles_for_event(eid)
        intel = event_to_intelligence(ev, articles)
        items.append(
            {
                "eventId": eid,
                "title": intel["title"],
                "qa": intel["qa"],
                "rewrite_history": intel["rewrite_history"],
                "importance_score": intel["importance_score"],
            }
        )
    items.sort(key=lambda x: int((x.get("qa") or {}).get("score") or 0))
    return {"items": items, "total": len(items)}


@app.get("/api/search")
def search(
    q: str = "",
    type: str = Query("event", alias="type"),
) -> dict[str, Any]:
    store = _store()
    needle = (q or "").strip().lower()
    if not needle:
        return {"items": [], "total": 0, "mode": type}
    rows = _all_events_enriched(store)
    if type == "keyword":
        rows = [
            r
            for r in rows
            if any(needle in (k or "").lower() for k in r.get("keywords") or [])
            or needle in (r.get("title") or "").lower()
        ]
    else:
        rows = [
            r
            for r in rows
            if needle in (r.get("title") or "").lower()
            or needle in (r.get("summaryPreview") or "").lower()
            or any(needle in (k or "").lower() for k in r.get("keywords") or [])
        ]
    return {"items": rows, "total": len(rows), "mode": type}


@app.get("/api/config/data-sources")
def get_config_data_sources() -> dict[str, Any]:
    rows = config_api.get_data_sources()
    return {"items": rows, "total": len(rows), "path": str(config_api._data_sources_path())}


@app.put("/api/config/data-sources")
def put_config_data_sources(body: list = Body(...)) -> dict[str, Any]:
    try:
        rows = config_api.put_data_sources(body)
        return {"items": rows, "total": len(rows)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@app.get("/api/config/keywords")
def get_config_keywords() -> dict[str, Any]:
    data = config_api.get_keywords()
    return {"data": data, "path": str(config_api._keywords_path())}


@app.put("/api/config/keywords")
def put_config_keywords(body: dict = Body(...)) -> dict[str, Any]:
    try:
        data = config_api.put_keywords(body)
        return {"data": data}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@app.get("/api/config/schedule")
def get_config_schedule() -> dict[str, Any]:
    return schedule_config.get_schedule_config()


@app.put("/api/config/schedule")
def put_config_schedule(body: dict = Body(...)) -> dict[str, Any]:
    try:
        return schedule_config.put_schedule_config(body)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
