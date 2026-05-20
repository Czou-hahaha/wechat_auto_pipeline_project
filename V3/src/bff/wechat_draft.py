"""单事件通稿推送微信公众号草稿箱。"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from src.config import Settings
from src.storage import JsonStore
from src.wechat import WeChatDraftClient

logger = logging.getLogger(__name__)


def _normalize_url(url: str) -> str:
    u = (url or "").strip()
    if not u:
        return ""
    if u.startswith(("http://", "https://")):
        return u
    return f"https://{u.lstrip('/')}"


async def _resolve_thumb(client: WeChatDraftClient, settings: Settings) -> str:
    mid = (settings.wechat_mp_thumb_media_id or "").strip()
    if mid:
        return mid
    local = (settings.wechat_mp_thumb_local_path or "").strip()
    if local:
        return await client.upload_local_cover(local)
    raise RuntimeError("未配置公众号封面（WECHAT_MP_THUMB_MEDIA_ID 或 WECHAT_MP_THUMB_LOCAL_PATH）")


async def push_event_press_to_wechat(
    store: JsonStore,
    settings: Settings,
    event_id: str,
    *,
    title: str,
    summary: str,
) -> dict[str, Any]:
    ev = store.get_event(event_id)
    if not ev:
        raise ValueError("event not found")
    body = (summary or "").strip() or str(ev.get("event_press_zh") or "").strip()
    if not body:
        raise ValueError("通稿内容为空")
    draft_title = (title or "").strip() or str(ev.get("title") or "未命名")[:64]

    articles = store.articles_for_event(event_id)
    primary_url = ""
    for a in articles:
        if str(a.get("status") or "") == "ready_for_review":
            primary_url = _normalize_url(
                str(a.get("resolved_url") or a.get("source_url") or "")
            )
            break
    if not primary_url and articles:
        primary_url = _normalize_url(
            str(articles[0].get("resolved_url") or articles[0].get("source_url") or "")
        )

    if not settings.wechat_ready:
        raise RuntimeError("未配置微信公众号 AppID / AppSecret")

    client = WeChatDraftClient(
        app_id=settings.wechat_mp_app_id,
        app_secret=settings.wechat_mp_app_secret,
        author=settings.wechat_mp_author,
    )
    thumb = await _resolve_thumb(client, settings)
    await client.add_draft(
        title=draft_title,
        summary=body,
        source_url=primary_url,
        thumb_media_id=thumb,
    )

    pushed_at = datetime.now(timezone.utc).isoformat()
    store.patch_event(
        event_id,
        {
            "event_press_zh": body,
            "title": draft_title,
            "event_wechat_draft_pushed_at": pushed_at,
        },
    )
    for a in articles:
        aid = str(a.get("id") or "").strip()
        if aid:
            store.patch_article(aid, {"wechat_draft_pushed_at": pushed_at})

    logger.info("event draft pushed event_id=%s", event_id[:13])
    return {
        "ok": True,
        "pushedAt": pushed_at,
        "title": draft_title,
    }


def push_event_press_to_wechat_sync(
    store: JsonStore,
    settings: Settings,
    event_id: str,
    *,
    title: str = "",
    summary: str = "",
) -> dict[str, Any]:
    return asyncio.run(
        push_event_press_to_wechat(
            store, settings, event_id, title=title, summary=summary
        )
    )
