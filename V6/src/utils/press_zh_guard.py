"""通稿/标题中文门禁：模型偶发英文成稿时强制译为简体中文。"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.ai import SummaryService

logger = logging.getLogger(__name__)


async def ensure_press_title_body_zh(
    summarizer: "SummaryService",
    *,
    title: str,
    body: str,
) -> tuple[str, str, str]:
    """
    若标题或正文以外文为主，调用中译。

    Returns:
        (title_zh, display_title, body_zh)
    """
    raw_title = (title or "").strip()
    raw_body = (body or "").strip()
    title_zh = ""
    display_title = raw_title
    body_zh = raw_body

    if not summarizer._api_key:
        return title_zh, display_title, body_zh

    need_title = bool(raw_title) and summarizer._text_is_mostly_non_cjk(raw_title)
    need_body = bool(raw_body) and summarizer._text_is_mostly_non_cjk(raw_body)

    if need_body or (need_title and raw_body):
        tzh, szh = await summarizer.translate_title_summary_to_zh(
            title=raw_title or "事件通稿",
            summary=raw_body or raw_title,
        )
        if tzh:
            title_zh = tzh
            display_title = tzh
        if szh:
            body_zh = szh
        elif need_body:
            fallback = await summarizer.translate_press_body_to_zh(
                title=raw_title or "事件通稿",
                body=raw_body,
            )
            if fallback:
                body_zh = fallback
            else:
                logger.warning("press body translate returned empty, keep original")
    elif need_title:
        title_zh = await summarizer.translate_title_to_zh(title=raw_title)
        if title_zh:
            display_title = title_zh

    if body_zh and summarizer._text_is_mostly_non_cjk(body_zh):
        logger.warning(
            "press body still mostly non-CJK after translate title=%s",
            (raw_title or "")[:40],
        )

    return title_zh, display_title, body_zh
