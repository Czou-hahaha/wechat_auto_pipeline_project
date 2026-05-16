"""Map V3 JsonStore records to event-intelligence DTOs for the UI."""

from __future__ import annotations

import re
from collections import Counter
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

_STOPWORDS = frozenset(
    "的 了 在 是 与 及 等 将 对 为 从 被 已 也 并 而 或 一个 这一 该 其".split()
)
_TOPIC_KEYWORDS = ("FAA", "BVLOS", "eVTOL", "低空经济", "无人机", "UAM", "AAM")


def _host_country(host: str) -> str:
    h = (host or "").lower()
    if not h:
        return "INTL"
    if h.endswith(".cn") or h.endswith(".gov.cn") or "people.com" in h or "xinhua" in h:
        return "CN"
    return "INTL"


def _tokenize(text: str) -> set[str]:
    parts = re.findall(r"[\u4e00-\u9fff]{2,}|[A-Za-z]{3,}|\d+", text or "")
    return {p.lower() for p in parts if p and p not in _STOPWORDS}


def _overlap_score(a: str, b: str) -> float:
    ta, tb = _tokenize(a), _tokenize(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / max(len(ta | tb), 1)


def _importance_score(event: dict[str, Any], articles: list[dict[str, Any]]) -> int:
    qa = int(event.get("event_press_qa_score") or 0)
    n = len(articles) or int(event.get("article_count") or 0)
    important = sum(1 for a in articles if a.get("topic_is_important"))
    base = min(100, n * 12 + qa * 0.35 + important * 8)
    if event.get("event_press_zh"):
        base = min(100, base + 5)
    return int(round(base))


def _extract_keywords(event: dict[str, Any], articles: list[dict[str, Any]]) -> list[str]:
    blob = " ".join(
        [
            str(event.get("title") or ""),
            str(event.get("dominant_topic_key") or ""),
            *(str(a.get("title") or "") for a in articles[:6]),
        ]
    )
    found = [k for k in _TOPIC_KEYWORDS if k.lower() in blob.lower() or k in blob]
    tokens = re.findall(r"[\u4e00-\u9fff]{2,6}", blob)
    freq = Counter(t for t in tokens if t not in _STOPWORDS)
    for word, _ in freq.most_common(5):
        if word not in found:
            found.append(word)
    return found[:10]


def _build_timeline(event: dict[str, Any], articles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []
    for a in articles:
        ts = str(a.get("source_published_at") or a.get("created_at") or "")
        nodes.append(
            {
                "id": f"tl-{a.get('id', '')}",
                "at": ts,
                "label": str(a.get("title") or "")[:80],
                "type": "article",
                "articleId": str(a.get("id") or ""),
                "sourceHost": str(a.get("source_host") or ""),
            }
        )
    created = str(event.get("created_at") or "")
    if created:
        nodes.append(
            {
                "id": f"tl-event-{event.get('id', '')}",
                "at": created,
                "label": "事件聚类入库",
                "type": "cluster",
                "articleId": "",
                "sourceHost": "",
            }
        )
    press_at = str(event.get("event_press_generated_at") or "")
    if press_at:
        nodes.append(
            {
                "id": f"tl-press-{event.get('id', '')}",
                "at": press_at,
                "label": "AI 通稿生成",
                "type": "press",
                "articleId": "",
                "sourceHost": "",
            }
        )
    nodes.sort(key=lambda n: n.get("at") or "")
    return nodes


def _split_paragraphs(text: str) -> list[str]:
    raw = (text or "").strip()
    if not raw:
        return []
    parts = [p.strip() for p in re.split(r"\n\s*\n", raw) if p.strip()]
    return parts if parts else [raw]


def _build_grounding(press: str, articles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    spans: list[dict[str, Any]] = []
    for idx, para in enumerate(_split_paragraphs(press)):
        scored: list[tuple[float, str]] = []
        for a in articles:
            aid = str(a.get("id") or "")
            body = " ".join(
                [
                    str(a.get("title") or ""),
                    str(a.get("extracted_text") or "")[:2000],
                ]
            )
            score = _overlap_score(para, body)
            if score > 0.05:
                scored.append((score, aid))
        scored.sort(key=lambda x: -x[0])
        article_ids = [aid for _, aid in scored[:3]]
        confidence = min(0.95, 0.55 + (scored[0][0] if scored else 0))
        spans.append(
            {
                "paragraphId": f"p{idx}",
                "text": para,
                "articleIds": article_ids,
                "confidence": round(confidence, 2),
            }
        )
    return spans


def _article_dto(row: dict[str, Any], press: str) -> dict[str, Any]:
    host = str(row.get("source_host") or "")
    if not host:
        try:
            host = urlparse(str(row.get("resolved_url") or row.get("source_url") or "")).netloc
        except Exception:
            host = ""
    body = str(row.get("extracted_text") or row.get("summary") or "")
    sim = _overlap_score(press, body) if press else 0.35
    return {
        "id": str(row.get("id") or ""),
        "title": str(row.get("title") or ""),
        "url": str(row.get("resolved_url") or row.get("source_url") or ""),
        "sourceHost": host,
        "publishedAt": str(row.get("source_published_at") or row.get("created_at") or ""),
        "similarity": round(min(0.99, 0.4 + sim), 2),
        "excerpt": body[:280] + ("…" if len(body) > 280 else ""),
        "rejected": str(row.get("status") or "").startswith("rejected"),
    }


def _qa_detail(event: dict[str, Any]) -> dict[str, Any]:
    score = int(event.get("event_press_qa_score") or 0)
    hallucination = bool(event.get("event_press_qa_hallucination"))
    rewrites = int(event.get("event_press_qa_rewrite_attempts") or 0)
    risk = "low"
    if hallucination:
        risk = "high"
    elif score < 70:
        risk = "medium"
    elif score < 85:
        risk = "low-medium"
    return {
        "score": score,
        "approved": bool(event.get("event_press_qa_approved")),
        "hallucinationRisk": risk,
        "hallucination": hallucination,
        "rewriteTriggered": rewrites > 0,
        "rewriteAttempts": rewrites,
        "aiStyleRisk": max(0, min(100, 100 - score)) if score else 40,
        "missingFacts": [],
        "issues": [],
        "rejectedArticleIds": [],
        "stoppedReason": str(event.get("event_press_qa_stopped_reason") or ""),
    }


def _rewrite_history(event: dict[str, Any], press: str) -> list[dict[str, Any]]:
    rewrites = int(event.get("event_press_qa_rewrite_attempts") or 0)
    if rewrites <= 0:
        return [
            {
                "round": 0,
                "at": str(event.get("event_press_qa_at") or event.get("event_press_generated_at") or ""),
                "before": "",
                "after": press,
                "reason": "初稿（未触发重写）",
            }
        ]
    return [
        {
            "round": i + 1,
            "at": str(event.get("event_press_qa_at") or ""),
            "before": f"【第 {i + 1} 轮重写前占位】",
            "after": press if i + 1 == rewrites else f"【第 {i + 1} 轮重写后占位】",
            "reason": "QA 未达标触发重写",
        }
        for i in range(rewrites)
    ]


def event_to_intelligence(event: dict[str, Any], articles: list[dict[str, Any]]) -> dict[str, Any]:
    """Full detail DTO."""
    press = str(event.get("event_press_zh") or event.get("summary_zh") or event.get("summary") or "")
    countries = sorted({_host_country(str(a.get("source_host") or "")) for a in articles})
    domains = sorted({str(a.get("source_host") or "") for a in articles if a.get("source_host")})
    return {
        "id": str(event.get("id") or ""),
        "title": str(event.get("title") or ""),
        "importance_score": _importance_score(event, articles),
        "qa_score": int(event.get("event_press_qa_score") or 0),
        "article_count": len(articles),
        "summary": press,
        "summaryPreview": press[:220] + ("…" if len(press) > 220 else ""),
        "keywords": _extract_keywords(event, articles),
        "countries": countries or ["CN"],
        "timeline": _build_timeline(event, articles),
        "articles": [_article_dto(a, press) for a in articles],
        "sourceDomains": domains,
        "rewrite_history": _rewrite_history(event, press),
        "grounding": _build_grounding(press, articles),
        "qa": _qa_detail(event),
        "createdAt": str(event.get("created_at") or ""),
        "dominantTopicKey": str(event.get("dominant_topic_key") or ""),
    }


def event_to_list_item(event: dict[str, Any], articles: list[dict[str, Any]]) -> dict[str, Any]:
    full = event_to_intelligence(event, articles)
    return {
        "id": full["id"],
        "title": full["title"],
        "importance_score": full["importance_score"],
        "qa_score": full["qa_score"],
        "article_count": full["article_count"],
        "summaryPreview": full["summaryPreview"],
        "keywords": full["keywords"][:6],
        "countries": full["countries"],
        "timeline": full["timeline"][-3:],
        "createdAt": full["createdAt"],
    }
