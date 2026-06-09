"""将 event articles 与正文打包进字符预算（粗估 token 控制）。"""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping, Sequence
from typing import Any

logger = logging.getLogger(__name__)


def approx_tokens_from_chars(char_count: int) -> int:
    """中文偏多时偏保守：约 1 token ≈ 1.5 中文字符量级，这里用 chars//2 作上界近似。"""
    if char_count <= 0:
        return 0
    return max(1, char_count // 2)


def format_event_articles_block(
    event_articles: str | Sequence[Mapping[str, Any]],
    *,
    max_chars: int,
) -> tuple[str, dict[str, Any]]:
    """
    将 event articles 规范为单一文本块，并在超长时截断。

    Returns:
        (text, meta) 其中 meta 含 structured 字段供日志使用。
    """
    raw = _articles_to_text(event_articles)
    original_chars = len(raw)
    truncated = False
    out = raw
    if max_chars > 0 and len(out) > max_chars:
        out = out[: max_chars - 1].rstrip() + "…"
        truncated = True
    meta = {
        "event_articles_original_chars": original_chars,
        "event_articles_packed_chars": len(out),
        "event_articles_truncated": truncated,
        "approx_input_tokens_event_block": approx_tokens_from_chars(len(out)),
    }
    if truncated:
        logger.warning(
            "%s",
            json.dumps(
                {"event": "context_truncated", **meta},
                ensure_ascii=False,
            ),
        )
    return out, meta


def _articles_to_text(event_articles: str | Sequence[Mapping[str, Any]]) -> str:
    if isinstance(event_articles, str):
        return event_articles.strip()
    lines: list[str] = []
    for idx, row in enumerate(event_articles, start=1):
        if not isinstance(row, Mapping):
            lines.append(f"[{idx}] {row!r}")
            continue
        title = str(row.get("title") or row.get("headline") or "").strip()
        url = str(row.get("url") or row.get("source_url") or "").strip()
        body = str(row.get("body") or row.get("text") or row.get("content") or "").strip()
        header = f"### 来源稿 {idx}"
        if title:
            header += f"：{title}"
        if url:
            header += f"\nURL: {url}"
        chunk = "\n".join([header, body]).strip()
        if chunk:
            lines.append(chunk)
    return "\n\n---\n\n".join(lines).strip()
