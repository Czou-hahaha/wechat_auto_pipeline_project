"""Main-body extraction helpers (trafilatura primary, caller supplies fallback)."""
from __future__ import annotations

import logging
from typing import Callable

logger = logging.getLogger(__name__)


def extract_main_text_trafilatura(
    html: str,
    *,
    page_url: str,
    min_chars: int,
) -> str | None:
    """
    Run trafilatura on decoded HTML. Returns stripped text or None if unusable.

    ``min_chars``: below this length the extraction is treated as failed (caller
    should fall back to legacy parsing).
    """
    raw = (html or "").strip()
    if not raw or min_chars <= 0:
        return None
    try:
        import trafilatura
    except ImportError:
        logger.warning("trafilatura not installed; skipping trafilatura extract")
        return None
    try:
        extracted = trafilatura.extract(
            raw,
            url=page_url or None,
            favor_recall=True,
            include_comments=False,
            include_tables=True,
        )
    except Exception:
        logger.debug("trafilatura.extract failed", exc_info=True)
        return None
    if not extracted:
        return None
    text = extracted.strip()
    if len(text) < min_chars:
        return None
    return text[:20000]


def main_text_with_trafilatura_fallback(
    html: str,
    *,
    page_url: str,
    min_chars: int,
    trafilatura_enabled: bool,
    fallback: Callable[[], str],
) -> str:
    """
    If ``trafilatura_enabled``, try trafilatura; on failure use ``fallback()`` result.
    """
    if trafilatura_enabled:
        got = extract_main_text_trafilatura(html, page_url=page_url, min_chars=min_chars)
        if got:
            return got
    return fallback()
