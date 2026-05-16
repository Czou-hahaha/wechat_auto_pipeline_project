"""Resolve ``news.google.com/rss/articles/...`` wrappers to publisher URLs."""
from __future__ import annotations

import logging
from urllib.parse import urlparse, urlunparse

logger = logging.getLogger(__name__)


def _strip_google_news_article_tracking(url: str) -> str:
    """Remove ``?oc=`` / ``ceid`` etc. from ``.../rss/articles/...`` so ``gnewsdecoder`` is more reliable."""
    try:
        p = urlparse(url)
        host = (p.hostname or "").lower()
        if "news.google.com" not in host:
            return url
        path = p.path or ""
        if "/rss/articles/" not in path and "/articles/" not in path:
            return url
        return urlunparse((p.scheme or "https", host, path, "", "", ""))
    except Exception:
        return url


def decode_google_news_url(url: str, *, decoder_interval: float = 0.25) -> str:
    """
    When *url* is a Google News RSS article wrapper, call ``googlenewsdecoder`` (batchexecute RPC).

    On success returns the publisher URL; otherwise returns *url* unchanged. Non-Google URLs are
    returned as-is. If the optional dependency is missing, returns *url* unchanged.
    """
    raw = (url or "").strip()
    if not raw:
        return raw
    try:
        host = (urlparse(raw).hostname or "").lower()
    except Exception:
        return raw
    if "news.google.com" not in host:
        return raw
    normalized = _strip_google_news_article_tracking(raw)
    try:
        from googlenewsdecoder import gnewsdecoder
    except ImportError:
        logger.debug("googlenewsdecoder not installed; cannot unwrap google news url")
        return raw
    try:
        decoded = gnewsdecoder(normalized, interval=float(decoder_interval))
        if decoded.get("status"):
            out = (decoded.get("decoded_url") or "").strip()
            if out:
                return out
    except Exception:
        logger.debug("gnewsdecoder failed", exc_info=True)
    return raw
