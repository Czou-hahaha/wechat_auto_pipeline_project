"""FastAPI BFF — read-only event intelligence API."""

from __future__ import annotations

import os
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import Body, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from src.bff import config_api, data_source_health_store, schedule_config
from src.services.data_source_health import probe_data_source, validate_row_shape
from src.bff.enhancement_loader import load_enhancement_runs_by_event
from src.bff.event_list_cache import get_cached_event_list_items, invalidate_event_list_cache
from src.bff.event_mapper import (
    aggregate_hot_keywords,
    event_to_intelligence,
)
from src.bff.event_search import filter_and_rank_events
from src.bff.pipeline_run import read_status, start_run_once
from src.bff.scheduler_run import read_status as read_scheduler_status, sync_scheduler
from src.bff.wechat_draft import (
    mark_event_draft_pushed_sync,
    push_event_press_to_wechat_sync,
)
from src.config import Settings
from src.services.ai_press_writer.prompt_builder import (
    get_event_press_system_prompt,
    get_event_press_user_template,
)
from src.services.event_history_mvp import build_event_history_payload
from src.services.event_map_mvp import build_event_map_payload
from src.services.event_memory_mvp import EventMemoryStore
from src.services.feedback_loop_mvp import FeedbackStore
from src.services.feedback_policy_mvp import FeedbackPolicyEngine
from src.services.feedback_prompt_engine import FeedbackPromptEngine
from src.services.event_intelligence_graph import build_event_intelligence_graph
from src.services.notifications import build_notifications
from src.services.source_intake import probe_source_intake, save_source_intake
from src.services.prompt_contract_mvp import PromptContractStore
from src.services.source_discovery_mvp import SourceCandidateStore
from src.storage import JsonStore

app = FastAPI(title="Low-Altitude Intelligence BFF", version="0.1.0")


@app.on_event("startup")
def _bff_startup_sync_scheduler() -> None:
    """BFF 启动时若配置已启用定时采集，自动拉起 run-scheduler（V6 默认关闭）。"""
    store = _store()
    data_dir = Path(store.data_dir)
    settings = Settings()
    if not settings.bff_scheduler_autostart:
        import logging

        sync_scheduler(data_dir, enabled=False, jobs=[])
        logging.getLogger(__name__).info(
            "BFF_SCHEDULER_AUTOSTART=false: V6 不启动定时调度（生产请用 V5 run-scheduler）"
        )
        try:
            n = store.sync_event_draft_pushed_flags()
            if n:
                logging.getLogger(__name__).info(
                    "synced event_wechat_draft_pushed_at for %d events", n
                )
        except Exception:
            logging.getLogger(__name__).warning(
                "sync_event_draft_pushed_flags on startup failed", exc_info=True
            )
        return
    try:
        from src.bff.schedule_config import _read_jobs_file

        data = _read_jobs_file()
        if not data.get("enabled"):
            return
        jobs = data.get("jobs") or []
        if not jobs:
            return
        sync_scheduler(
            data_dir,
            enabled=True,
            jobs=jobs,
            timezone=str(data.get("timezone") or "Asia/Shanghai"),
        )
    except Exception:
        import logging

        logging.getLogger(__name__).warning(
            "scheduler auto-start on BFF startup failed", exc_info=True
        )
    try:
        n = store.sync_event_draft_pushed_flags()
        if n:
            import logging

            logging.getLogger(__name__).info(
                "synced event_wechat_draft_pushed_at for %d events", n
            )
    except Exception:
        import logging

        logging.getLogger(__name__).warning(
            "sync draft pushed flags on startup failed", exc_info=True
        )


app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("BFF_CORS_ORIGINS", "http://localhost:3000,http://localhost:3001").split(","),
    allow_credentials=True,
    allow_methods=["GET", "PUT", "POST", "OPTIONS"],
    allow_headers=["*"],
)


def _store() -> JsonStore:
    s = Settings()
    return JsonStore(Path(s.data_dir))


def _feedback_store() -> FeedbackStore:
    return FeedbackStore(_store().data_dir)


def _source_candidate_store() -> SourceCandidateStore:
    return SourceCandidateStore(_store().data_dir)


def _event_memory_store() -> EventMemoryStore:
    return EventMemoryStore(_store().data_dir)


def _feedback_prompt_engine() -> FeedbackPromptEngine:
    return FeedbackPromptEngine(Settings())


def _feedback_policy_engine() -> FeedbackPolicyEngine:
    return FeedbackPolicyEngine(Settings())


def _prompt_contract_store() -> PromptContractStore:
    return PromptContractStore(_store().data_dir)


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
    return get_cached_event_list_items(store)


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


@app.post("/api/events/{event_id}/mark-draft-pushed")
def post_mark_draft_pushed(
    event_id: str,
    body: dict = Body(default={}),
) -> dict[str, Any]:
    """记录「已写入草稿箱」时间，不调用微信（手工推草稿后用）。"""
    store = _store()
    if not store.get_event(event_id):
        raise HTTPException(status_code=404, detail="event not found")
    pushed_at = str(body.get("pushedAt") or body.get("pushed_at") or "").strip() or None
    try:
        return mark_event_draft_pushed_sync(store, event_id, pushed_at=pushed_at)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


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
    invalidate_event_list_cache()
    articles = store.articles_for_event(event_id)
    enh_idx = _enhancement_index(store)
    return event_to_intelligence(  # noqa: SLF001 — detail only
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


@app.get("/api/events/{event_id}/graph")
def get_event_intelligence_graph(event_id: str) -> dict[str, Any]:
    store = _store()
    try:
        return build_event_intelligence_graph(store, event_id, settings=Settings())
    except ValueError:
        raise HTTPException(status_code=404, detail="event not found")


@app.get("/api/events/{event_id}/map")
def get_event_map(event_id: str) -> dict[str, Any]:
    store = _store()
    ev = store.get_event(event_id)
    if not ev:
        raise HTTPException(status_code=404, detail="event not found")
    rows = store.articles_for_event(event_id)
    return build_event_map_payload(ev, rows)


@app.get("/api/events/{event_id}/history")
def get_event_history(event_id: str) -> dict[str, Any]:
    store = _store()
    try:
        return build_event_history_payload(store, event_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="event not found")


@app.post("/api/events/{event_id}/memory/refresh")
def refresh_event_memory(event_id: str) -> dict[str, Any]:
    store = _store()
    ev = store.get_event(event_id)
    if not ev:
        raise HTTPException(status_code=404, detail="event not found")
    rows = store.articles_for_event(event_id)
    snap = _event_memory_store().upsert_snapshot(ev, rows)
    return {"ok": True, "snapshot": snap}


@app.get("/api/events/{event_id}/memory")
def get_event_memory(event_id: str) -> dict[str, Any]:
    snap = _event_memory_store().get_snapshot(event_id)
    if snap is None:
        raise HTTPException(status_code=404, detail="snapshot not found")
    return snap


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
    phase_path = store.data_dir / "phase_timings_last_run.json"
    phase_timings: dict[str, Any] = {"total_sec": 0, "phases": {}}
    if phase_path.is_file():
        import json

        try:
            phase_timings = json.loads(phase_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    notif = build_notifications(Settings())
    return {
        "todayNewEvents": today_new,
        "highImportanceEvents": high,
        "hotKeywords": aggregate_hot_keywords(enriched),
        "regionSplit": {"domestic": cn, "international": intl},
        "topicTrend": trend,
        "aiRewriteCount": rewrites,
        "avgQaScore": avg_qa,
        "totalEvents": len(events),
        "phaseTimings": phase_timings,
        "notificationCount": int(notif.get("total") or 0),
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


@app.post("/api/feedback")
def post_feedback(body: dict = Body(...)) -> dict[str, Any]:
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="body must be a JSON object")
    event_id = str(body.get("eventId") or body.get("event_id") or "").strip()
    note = str(body.get("note") or "").strip()
    if not event_id or not note:
        raise HTTPException(status_code=400, detail="eventId and note are required")
    stage = str(body.get("stage") or "qa").strip().lower()
    category = str(body.get("category") or "general").strip().lower()
    rec = _feedback_store().add(
        event_id=event_id,
        stage=stage,
        category=category,
        note=note,
    )
    return {"ok": True, "item": rec}


@app.get("/api/feedback/summary")
def get_feedback_summary(window_days: int = Query(14, ge=1, le=90)) -> dict[str, Any]:
    return _feedback_prompt_engine().summary_with_prompt(window_days=window_days)


@app.post("/api/feedback/prompt/recompute")
def recompute_feedback_prompt(body: dict = Body(default={})) -> dict[str, Any]:
    window_days = int((body or {}).get("windowDays") or 14)
    rec = _feedback_prompt_engine().recompute_prompt_suggestions(window_days=window_days)
    return {"ok": True, "suggestion": rec}


@app.post("/api/feedback/prompt/apply")
def apply_feedback_prompt(body: dict = Body(...)) -> dict[str, Any]:
    sid = str((body or {}).get("suggestionId") or "").strip()
    token = str((body or {}).get("confirmToken") or "").strip()
    if not sid:
        raise HTTPException(status_code=400, detail="suggestionId is required")
    try:
        ret = _feedback_prompt_engine().apply_prompt_suggestion(suggestion_id=sid, confirm_token=token)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ret


@app.post("/api/feedback/prompt/rollback")
def rollback_feedback_prompt(body: dict = Body(...)) -> dict[str, Any]:
    backup_path = str((body or {}).get("backupPath") or "").strip()
    if not backup_path:
        raise HTTPException(status_code=400, detail="backupPath is required")
    try:
        ret = _feedback_prompt_engine().rollback_prompt(backup_path=backup_path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ret


@app.get("/api/notifications")
def get_notifications() -> dict[str, Any]:
    return build_notifications(Settings())


@app.post("/api/sources/intake/probe")
async def probe_sources_intake(body: dict = Body(...)) -> dict[str, Any]:
    url = str((body or {}).get("url") or "").strip()
    domain = str((body or {}).get("domain") or "").strip()
    language = str((body or {}).get("language") or "zh").strip()
    if not url:
        raise HTTPException(status_code=400, detail="url is required")
    try:
        return await probe_source_intake(url=url, domain=domain, language=language)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/sources/intake/save")
async def save_sources_intake(body: dict = Body(...)) -> dict[str, Any]:
    draft = (body or {}).get("draftSource")
    if not isinstance(draft, dict):
        raise HTTPException(status_code=400, detail="draftSource required")
    settings = Settings()
    draft_bz = (body or {}).get("draftBrowserZh")
    if draft_bz is not None and not isinstance(draft_bz, dict):
        draft_bz = None
    try:
        return await save_source_intake(
            draft_source=draft,
            draft_browser_zh=draft_bz,
            data_sources_path=str(settings.his_data_sources_path or "config/data_sources.json"),
            browser_zh_path=str(settings.browser_zh_sources_path or "config/browser_zh_sources.json"),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/pipeline/phase-timings")
def get_pipeline_phase_timings() -> dict[str, Any]:
    path = _store().data_dir / "phase_timings_last_run.json"
    if not path.is_file():
        return {"total_sec": 0, "phases": {}}
    import json

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"total_sec": 0, "phases": {}}


@app.get("/api/feedback/policy")
def get_feedback_policy() -> dict[str, Any]:
    eng = _feedback_policy_engine()
    return {
        "recommendation": eng.current_recommendation(),
        "overrides": eng.current_overrides(),
    }


def _prompt_preview(text: str, *, max_chars: int = 1800) -> str:
    s = (text or "").strip()
    if len(s) <= max_chars:
        return s
    return s[:max_chars] + "\n\n...[truncated]..."


@app.get("/api/prompts/contract")
def get_prompt_contract() -> dict[str, Any]:
    settings = Settings()
    eng = _feedback_policy_engine()
    editable = _prompt_contract_store().get_editable()
    objective = editable.get("objective") or "多源事件通稿生成与事实性QA重写"
    hard_rules = editable.get("hard_rules") or [
        "仅使用输入材料事实",
        "禁止编造与外部扩展",
        "不足信息输出固定兜底",
        "QA评分与幻觉检测共同决定通过",
    ]
    soft_rules = editable.get("soft_rules") or [
        "表达清晰，优先结论先行",
        "段落结构稳定，避免空泛措辞",
    ]
    return {
        "contract": {
            "objective": objective,
            "hard_rules": hard_rules,
            "soft_rules": soft_rules,
            "enforcement": {
                "hard": "must_pass_gate",
                "soft": "rewrite_preference",
            },
            "effective_runtime": {
                "qa_rewrite_pass_threshold": settings.effective_qa_rewrite_pass_threshold(),
                "qa_rewrite_max_rounds": settings.effective_qa_rewrite_max_rounds(),
                "search_prefilter_enabled": settings.effective_search_prefilter_enabled(),
            },
            "policy_overrides": eng.current_overrides(),
        }
    }


@app.put("/api/prompts/contract")
def put_prompt_contract(body: dict = Body(...)) -> dict[str, Any]:
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="body must be object")
    try:
        editable = _prompt_contract_store().put_editable(body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    settings = Settings()
    eng = _feedback_policy_engine()
    return {
        "contract": {
            "objective": editable["objective"],
            "hard_rules": editable["hard_rules"],
            "soft_rules": editable.get("soft_rules") or [],
            "enforcement": {
                "hard": "must_pass_gate",
                "soft": "rewrite_preference",
            },
            "effective_runtime": {
                "qa_rewrite_pass_threshold": settings.effective_qa_rewrite_pass_threshold(),
                "qa_rewrite_max_rounds": settings.effective_qa_rewrite_max_rounds(),
                "search_prefilter_enabled": settings.effective_search_prefilter_enabled(),
            },
            "policy_overrides": eng.current_overrides(),
        }
    }


@app.get("/api/prompts/preview")
def get_prompt_preview() -> dict[str, Any]:
    system_prompt = get_event_press_system_prompt()
    user_template = get_event_press_user_template()
    return {
        "version": "event_press_v5",
        "systemPreview": _prompt_preview(system_prompt),
        "userTemplatePreview": _prompt_preview(user_template),
    }


@app.post("/api/feedback/policy/recompute")
def recompute_feedback_policy(body: dict = Body(default={})) -> dict[str, Any]:
    window_days = int((body or {}).get("windowDays") or 14)
    eng = _feedback_policy_engine()
    rec = eng.recompute(window_days=window_days)
    return {"ok": True, "recommendation": rec}


@app.post("/api/feedback/policy/apply")
def apply_feedback_policy(body: dict = Body(...)) -> dict[str, Any]:
    rec_id = str((body or {}).get("recommendationId") or "").strip()
    token = str((body or {}).get("confirmToken") or "").strip()
    if not rec_id:
        raise HTTPException(status_code=400, detail="recommendationId is required")
    eng = _feedback_policy_engine()
    try:
        ret = eng.apply(recommendation_id=rec_id, confirm_token=token)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ret


@app.post("/api/feedback/policy/rollback")
def rollback_feedback_policy(body: dict = Body(...)) -> dict[str, Any]:
    backup_path = str((body or {}).get("backupPath") or "").strip()
    if not backup_path:
        raise HTTPException(status_code=400, detail="backupPath is required")
    eng = _feedback_policy_engine()
    try:
        ret = eng.rollback(backup_path=backup_path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ret


@app.post("/api/sources/discover")
def discover_source_candidates() -> dict[str, Any]:
    store = _store()
    return _source_candidate_store().discover_from_articles(store.list_all())


@app.get("/api/sources/candidates")
def list_source_candidates() -> dict[str, Any]:
    rows = _source_candidate_store().list_all()
    return {"items": rows, "total": len(rows)}


@app.post("/api/sources/candidates/{host}/probe")
async def probe_source_candidate(host: str) -> dict[str, Any]:
    try:
        row = await _source_candidate_store().probe_candidate(host=host)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"ok": True, "item": row}


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


@app.post("/api/config/data-sources/validate")
async def validate_config_data_source(body: dict = Body(...)) -> dict[str, Any]:
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="body must be a JSON object")
    shape_err = validate_row_shape(body)
    if shape_err:
        raise HTTPException(status_code=400, detail=shape_err)
    probe = await probe_data_source(body)
    entry = data_source_health_store.record_probe(body, probe)
    return {
        "ok": probe.ok,
        "status": probe.status,
        "message": probe.message,
        "sample_count": probe.sample_count,
        "health": entry,
    }


@app.get("/api/config/data-sources/health")
def get_config_data_sources_health() -> dict[str, Any]:
    rows = config_api.get_data_sources()
    return data_source_health_store.build_health_response(rows)


@app.post("/api/config/data-sources/health/scan")
async def scan_config_data_sources_health() -> dict[str, Any]:
    return await data_source_health_store.run_full_health_scan()


@app.post("/api/config/data-sources/health/acknowledge")
def acknowledge_config_data_source_health(body: dict = Body(...)) -> dict[str, Any]:
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="body must be a JSON object")
    key = str(body.get("key") or "").strip()
    if not key:
        raise HTTPException(status_code=400, detail="key is required")
    note = str(body.get("note") or "").strip()
    entry = data_source_health_store.acknowledge_source(key, note=note)
    if entry is None:
        raise HTTPException(status_code=404, detail="health record not found")
    rows = config_api.get_data_sources()
    return {"ok": True, "entry": entry, **data_source_health_store.build_health_response(rows)}


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
