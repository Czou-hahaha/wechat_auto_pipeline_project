"""FastAPI BFF — read-only event intelligence API."""

from __future__ import annotations

import os
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import Body, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from src.bff import config_api, schedule_config
from src.bff.enhancement_loader import load_enhancement_runs_by_event
from src.bff.event_mapper import (
    aggregate_hot_keywords,
    event_to_intelligence,
    event_to_list_item,
)
from src.bff.event_search import filter_and_rank_events
from src.bff.pipeline_run import read_status, start_run_once
from src.bff.scheduler_run import read_status as read_scheduler_status, sync_scheduler
from src.bff.wechat_draft import push_event_press_to_wechat_sync
from src.config import Settings
from src.storage import JsonStore

app = FastAPI(title="Low-Altitude Intelligence BFF", version="0.1.0")


@app.on_event("startup")
def _bff_startup_sync_scheduler() -> None:
    """BFF 启动时若配置已启用定时采集，自动拉起 run-scheduler。"""
    try:
        from src.bff.schedule_config import _read_jobs_file

        data = _read_jobs_file()
        if not data.get("enabled"):
            return
        jobs = data.get("jobs") or []
        if not jobs:
            return
        store = _store()
        sync_scheduler(
            Path(store.data_dir),
            enabled=True,
            jobs=jobs,
            timezone=str(data.get("timezone") or "Asia/Shanghai"),
        )
    except Exception:
        import logging

        logging.getLogger(__name__).warning(
            "scheduler auto-start on BFF startup failed", exc_info=True
        )


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


def _url_roles_for_event(store: JsonStore, event_id: str) -> dict[str, str]:
    eid = (event_id or "").strip()
    roles: dict[str, str] = {}
    for m in store._read_event_map():  # noqa: SLF001
        if not isinstance(m, dict) or str(m.get("event_id") or "").strip() != eid:
            continue
        role = str(m.get("role") or "source").strip()
        for key in ("resolved_url", "source_url"):
            u = str(m.get(key) or "").strip()
            if u:
                roles[u] = role
    return roles


def _enhancement_index(store: JsonStore) -> dict[str, dict[str, Any]]:
    return load_enhancement_runs_by_event(Path(store.data_dir))


def _all_events_enriched(store: JsonStore) -> list[dict[str, Any]]:
    enh_idx = _enhancement_index(store)
    out: list[dict[str, Any]] = []
    for ev in store.list_events():
        if not isinstance(ev, dict):
            continue
        eid = str(ev.get("id") or "").strip()
        if not eid:
            continue
        articles = store.articles_for_event(eid)
        out.append(
            event_to_list_item(
                ev,
                articles,
                url_roles=_url_roles_for_event(store, eid),
                enhancement_row=enh_idx.get(eid),
            )
        )
    out.sort(key=lambda x: (-int(x.get("importance_score") or 0), x.get("createdAt") or ""))
    return out


def _topic_trend_from_events(enriched: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """近 7 日按关键词计数（来自真实事件 keywords，非占位）。"""
    from collections import Counter, defaultdict
    from datetime import datetime, timedelta, timezone

    buckets: dict[str, Counter[str]] = defaultdict(Counter)
    today = datetime.now(timezone.utc).date()
    for item in enriched:
        created = str(item.get("createdAt") or "")[:10]
        if not created:
            continue
        try:
            day = datetime.fromisoformat(created).date()
        except ValueError:
            continue
        if (today - day).days > 6:
            continue
        for kw in item.get("keywords") or []:
            k = str(kw).strip()
            if k and len(k) <= 12:
                buckets[created][k] += 1
    days = [(today - timedelta(days=i)).isoformat() for i in range(6, -1, -1)]
    top_kw = ("低空经济", "无人机", "eVTOL", "UAM", "AAM")
    out: list[dict[str, Any]] = []
    for d in days:
        row: dict[str, Any] = {"date": d[5:]}
        for kw in top_kw:
            row[kw] = int(buckets.get(d, Counter()).get(kw, 0))  # type: ignore[arg-type]
        out.append(row)
    return out


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "v3-bff"}


@app.get("/api/pipeline/status")
def pipeline_status() -> dict[str, Any]:
    store = _store()
    return read_status(Path(store.data_dir))


@app.post("/api/pipeline/run-once")
def pipeline_run_once() -> dict[str, Any]:
    store = _store()
    result = start_run_once(Path(store.data_dir))
    if not result.get("ok"):
        raise HTTPException(
            status_code=409,
            detail=str(result.get("error") or "already_running"),
        )
    return result


@app.get("/api/events")
def list_events(
    q: str = "",
    keyword: str = "",
    min_importance: int = 0,
    sort: str = Query("importance", pattern="^(importance|recent|qa)$"),
) -> dict[str, Any]:
    store = _store()
    rows = _all_events_enriched(store)
    needle = (q or keyword or "").strip()
    if needle:
        rows = filter_and_rank_events(rows, needle)
    if min_importance > 0:
        rows = [r for r in rows if int(r.get("importance_score") or 0) >= min_importance]
    if sort == "recent":
        rows.sort(key=lambda x: x.get("createdAt") or "", reverse=True)
    elif sort == "qa":
        rows.sort(key=lambda x: -int(x.get("qa_score") or 0))
    else:
        rows.sort(key=lambda x: -int(x.get("importance_score") or 0))
    return {"items": rows, "total": len(rows)}


@app.put("/api/events/{event_id}/press")
def put_event_press(event_id: str, body: dict = Body(...)) -> dict[str, Any]:
    store = _store()
    ev = store.get_event(event_id)
    if not ev:
        raise HTTPException(status_code=404, detail="event not found")
    press = str(body.get("summary") or body.get("event_press_zh") or "").strip()
    title = str(body.get("title") or "").strip()
    updates: dict[str, Any] = {}
    if press:
        updates["event_press_zh"] = press
    if title:
        updates["title"] = title
    if not updates:
        raise HTTPException(status_code=400, detail="empty body")
    store.patch_event(event_id, updates)
    articles = store.articles_for_event(event_id)
    enh_idx = _enhancement_index(store)
    return event_to_intelligence(
        store.get_event(event_id) or ev,
        articles,
        url_roles=_url_roles_for_event(store, event_id),
        enhancement_row=enh_idx.get(event_id),
    )


@app.post("/api/events/{event_id}/push-draft")
def post_event_push_draft(event_id: str, body: dict = Body(default={})) -> dict[str, Any]:
    store = _store()
    if not store.get_event(event_id):
        raise HTTPException(status_code=404, detail="event not found")
    settings = Settings()
    try:
        return push_event_press_to_wechat_sync(
            store,
            settings,
            event_id,
            title=str(body.get("title") or ""),
            summary=str(body.get("summary") or body.get("event_press_zh") or ""),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e


@app.get("/api/events/{event_id}")
def get_event(event_id: str) -> dict[str, Any]:
    store = _store()
    ev = store.get_event(event_id)
    if not ev:
        raise HTTPException(status_code=404, detail="event not found")
    eid = str(ev.get("id") or event_id).strip()
    articles = store.articles_for_event(eid)
    enh_idx = _enhancement_index(store)
    return event_to_intelligence(
        ev,
        articles,
        url_roles=_url_roles_for_event(store, eid),
        enhancement_row=enh_idx.get(eid),
    )


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

    cn, intl = 0, 0
    for item in enriched:
        for c in item.get("countries") or []:
            if c == "CN":
                cn += 1
            else:
                intl += 1
    trend = _topic_trend_from_events(enriched)
    return {
        "todayNewEvents": today_new,
        "highImportanceEvents": high,
        "hotKeywords": aggregate_hot_keywords(enriched),
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
        enh_idx = _enhancement_index(store)
        intel = event_to_intelligence(
            ev,
            articles,
            url_roles=_url_roles_for_event(store, eid),
            enhancement_row=enh_idx.get(eid),
        )
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
    type: str = Query("", alias="type"),  # 已废弃，保留参数兼容旧前端
) -> dict[str, Any]:
    """在已入库事件中检索：标题、摘要、关键词统一打分排序。"""
    store = _store()
    needle = (q or "").strip()
    if not needle:
        return {"items": [], "total": 0, "mode": "unified"}
    rows = filter_and_rank_events(_all_events_enriched(store), needle)
    return {"items": rows, "total": len(rows), "mode": "unified"}


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


@app.get("/api/scheduler/status")
def scheduler_status() -> dict[str, Any]:
    store = _store()
    return read_scheduler_status(Path(store.data_dir))


@app.put("/api/config/schedule")
def put_config_schedule(body: dict = Body(...)) -> dict[str, Any]:
    try:
        return schedule_config.put_schedule_config(body)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
