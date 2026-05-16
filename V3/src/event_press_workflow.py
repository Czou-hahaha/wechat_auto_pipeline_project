"""
阶段四（可选）：基于同一 event 下多篇 article 生成中文通稿，写入 ``events.json``。

在「阶段三：事件增强」之后执行，以便扩搜稿件已进入 ``articles.json``。
受 ``EVENT_AI_PRESS_ENABLED`` 控制；需 ``DEEPSEEK_API_KEY``。

阶段四成功后，默认自动执行阶段五（QA + 条件重写），终稿仍写入 ``event_press_zh``。
阶段五受 ``QA_REWRITE_ENABLED`` 控制（默认 true）。
"""
from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.config import Settings
    from src.storage import JsonStore

logger = logging.getLogger(__name__)

_INSUFFICIENT_PRESS = "【信息不足，无法生成高质量通稿】"


def _should_run_qa_on_press(body: str) -> bool:
    b = (body or "").strip()
    return bool(b) and b != _INSUFFICIENT_PRESS


def _qa_sources_for_event(rows: list[dict[str, Any]], settings: "Settings") -> list[dict[str, str]]:
    from src.services.ai_press_writer.article_selector import article_rows_to_qa_sources

    raw_mode = str(getattr(settings, "event_ai_press_selection_mode", "") or "all_by_tier").strip().lower()
    mode = raw_mode if raw_mode in ("top_k_dedupe", "all_by_tier") else "all_by_tier"
    per_cap = int(getattr(settings, "event_ai_press_per_article_max_chars", 0) or 0)
    max_n = max(1, min(int(getattr(settings, "event_ai_press_max_articles_in_prompt", 20)), 60))
    return article_rows_to_qa_sources(
        rows,
        selection_mode=mode,
        top_k=5,
        max_articles_in_prompt=max_n,
        per_article_max_chars=per_cap,
    )


async def _apply_press_quality(
    *,
    settings: "Settings",
    event_articles: list[dict[str, str]],
    draft: str,
    event_id: str,
) -> tuple[str, dict[str, Any]]:
    """阶段五：QA →（未达标则重写）→ 终稿；返回 (final_body, patch_fields)。"""
    from src.services.qa_rewrite.pipeline import run_press_quality_pipeline
    from src.storage import JsonStore

    if not bool(getattr(settings, "qa_rewrite_enabled", True)):
        return draft, {}

    if not _should_run_qa_on_press(draft):
        logger.debug("event press qa: skip event=%s (insufficient draft)", event_id[:13])
        return draft, {}

    result = await run_press_quality_pipeline(
        event_articles=event_articles,
        draft=draft,
        settings=settings,
    )
    qa = result.last_qa
    patch: dict[str, Any] = {
        "event_press_qa_score": int(qa.score),
        "event_press_qa_approved": bool(qa.approved),
        "event_press_qa_hallucination": bool(qa.hallucination),
        "event_press_qa_rewrite_attempts": int(result.rewrite_attempts),
        "event_press_qa_stopped_reason": str(result.stopped_reason or ""),
        "event_press_qa_at": JsonStore.now_iso(),
    }
    logger.info(
        "%s",
        json.dumps(
            {
                "event": "event_press_qa_done",
                "event_id_prefix": event_id[:13],
                **{k: patch[k] for k in patch if k != "event_press_qa_at"},
                **result.to_log_dict(),
            },
            ensure_ascii=False,
        ),
    )
    return (result.final_article or draft).strip(), patch


async def run_event_press_generation(
    store: "JsonStore", settings: "Settings", *, force: bool = False
) -> None:
    """遍历事件：满足最少篇数则调用 DeepSeek，经阶段五后写入 ``event_press_zh``。"""
    if not force and not bool(getattr(settings, "event_ai_press_enabled", False)):
        return
    if not (settings.deepseek_api_key or "").strip():
        logger.info("event press: skipped (DEEPSEEK_API_KEY empty)")
        return
    from src.services.ai_press_writer.ai_writer_service import EventPressWriterService
    from src.storage import JsonStore

    min_n = max(1, int(getattr(settings, "event_ai_press_min_articles", 2)))
    skip_existing = bool(getattr(settings, "event_ai_press_skip_if_exists", True))

    svc = EventPressWriterService(settings)
    if not svc.available:
        return

    events = store.list_events()
    if not events:
        logger.debug("event press: no events in store")
        return

    for ev in events:
        if not isinstance(ev, dict):
            continue
        eid = str(ev.get("id") or "").strip()
        if not eid:
            continue
        if skip_existing and str(ev.get("event_press_zh") or "").strip():
            continue
        rows = store.articles_for_event(eid)
        if len(rows) < min_n:
            logger.debug("event press: skip event=%s articles=%d < min=%d", eid[:13], len(rows), min_n)
            continue
        title = str(ev.get("title") or "").strip()
        dom = str(ev.get("dominant_topic_key") or "").strip()
        try:
            draft = await svc.generate_press_for_event(
                event_title=title,
                dominant_topic_key=dom,
                article_rows=rows,
            )
        except Exception:
            logger.exception("event press: generation failed event=%s", eid[:13])
            continue

        body = (draft or "").strip()
        qa_patch: dict[str, Any] = {}
        try:
            sources = _qa_sources_for_event(rows, settings)
            if sources:
                body, qa_patch = await _apply_press_quality(
                    settings=settings,
                    event_articles=sources,
                    draft=body,
                    event_id=eid,
                )
            elif bool(getattr(settings, "qa_rewrite_enabled", True)) and _should_run_qa_on_press(body):
                logger.warning("event press qa: no sources for event=%s, keep stage-4 draft", eid[:13])
        except Exception:
            logger.exception("event press qa: failed event=%s, keep stage-4 draft", eid[:13])
            body = (draft or "").strip()

        patch: dict[str, Any] = {
            "event_press_zh": body,
            "event_press_generated_at": JsonStore.now_iso(),
            **qa_patch,
        }
        ok = store.patch_event(eid, patch)
        if ok:
            logger.info(
                "event press: wrote event=%s chars=%d qa_score=%s rewrites=%s",
                eid[:13],
                len(body or ""),
                patch.get("event_press_qa_score", "n/a"),
                patch.get("event_press_qa_rewrite_attempts", "n/a"),
            )
        else:
            logger.warning("event press: patch_event miss event=%s", eid[:13])
