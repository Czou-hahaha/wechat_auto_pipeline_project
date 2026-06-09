"""Event expansion language: title + seed body CJK ratio."""
from __future__ import annotations

import re
from typing import Any, Literal

EventLang = Literal["zh", "en"]

_CJK_RE = re.compile(r"[\u4e00-\u9fff]")


def _meaningful_chars(text: str) -> int:
    return len(re.sub(r"\s+", "", text or ""))


def cjk_ratio(text: str) -> float:
    stripped = (text or "").strip()
    if not stripped:
        return 0.0
    meaningful = _meaningful_chars(stripped)
    if meaningful <= 0:
        return 0.0
    return len(_CJK_RE.findall(stripped)) / meaningful


def detect_event_expansion_lang(
    *,
    event_title: str,
    member_articles: list[dict[str, Any]],
    body_max_chars: int = 2000,
    cjk_threshold: float = 0.15,
) -> EventLang:
    """
    标题 + 主稿正文（``ready_for_review`` 或 map role primary）综合判定。
    ``cjk_ratio >= cjk_threshold`` → zh（扩搜跳过 GDELT）；否则 en（GDELT sourcelang:english）。
    """
    parts: list[str] = [str(event_title or "").strip()]
    for row in member_articles:
        if not isinstance(row, dict):
            continue
        status = str(row.get("status") or "").strip().lower()
        role = str(row.get("map_role") or row.get("role") or "").strip().lower()
        if status != "ready_for_review" and role != "primary":
            continue
        t = str(row.get("title") or "").strip()
        body = str(row.get("extracted_text") or row.get("body_text") or "")[:body_max_chars]
        parts.append(t)
        parts.append(body)
    blob = "\n".join(p for p in parts if p)
    if cjk_ratio(blob) >= float(cjk_threshold):
        return "zh"
    return "en"
