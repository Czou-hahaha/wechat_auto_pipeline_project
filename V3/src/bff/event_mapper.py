"""Map V3 JsonStore records to event-intelligence DTOs for the UI."""

from __future__ import annotations

import re
from collections import Counter
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse


def _normalize_article_url(url: str) -> str:
    u = (url or "").strip()
    if not u:
        return ""
    if u.startswith(("http://", "https://")):
        return u
    return f"https://{u.lstrip('/')}"

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


def _configured_search_terms() -> list[str]:
    """检索配置中的完整词/短语，按长度降序（最长匹配优先）。"""
    raw: list[str] = list(_TOPIC_KEYWORDS)
    try:
        from src.config import Settings

        s = Settings()
        raw.extend(s.parsed_chinese_keywords())
        raw.extend(s.parsed_english_keywords())
    except Exception:
        pass
    seen: set[str] = set()
    out: list[str] = []
    for term in sorted(
        {str(x).strip() for x in raw if str(x).strip()},
        key=len,
        reverse=True,
    ):
        key = term.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(term)
    return out


def _terms_in_text(blob: str, terms: list[str]) -> list[str]:
    """在文本中匹配完整检索词，避免按字数截断中文。"""
    if not blob.strip():
        return []
    lower = blob.casefold()
    found: list[str] = []
    seen: set[str] = set()
    for term in terms:
        key = term.casefold()
        if key in seen:
            continue
        if key in lower or term in blob:
            found.append(term)
            seen.add(key)
    return found


def catalog_keywords_in_text(blob: str) -> list[str]:
    """仅返回采集配置中的完整检索词命中（不含标题切片、topic_key）。"""
    found = _terms_in_text(blob, _configured_search_terms())
    pruned: list[str] = []
    for term in found:
        if any(
            term != other and term.casefold() in other.casefold()
            for other in found
        ):
            continue
        pruned.append(term)
    return pruned


def aggregate_hot_keywords(enriched: list[dict[str, Any]], *, limit: int = 8) -> list[dict[str, Any]]:
    """Dashboard 热门词：按事件标题+摘要统计配置词表命中次数。"""
    counter: Counter[str] = Counter()
    for item in enriched:
        blob = " ".join(
            [
                str(item.get("title") or ""),
                str(item.get("summaryPreview") or ""),
                str(item.get("summary") or ""),
            ]
        )
        for term in catalog_keywords_in_text(blob):
            counter[term] += 1
    return [{"keyword": k, "count": v} for k, v in counter.most_common(limit)]


def _extract_keywords(event: dict[str, Any], articles: list[dict[str, Any]]) -> list[str]:
    blob = " ".join(
        [
            str(event.get("title") or ""),
            *(str(a.get("title") or "") for a in articles[:6]),
        ]
    )
    return catalog_keywords_in_text(blob)[:10]


def _article_source_kind(row: dict[str, Any], url_roles: dict[str, str]) -> str:
    """``seed`` | ``expansion`` | ``cluster`` — 供前端区分主稿与扩搜增强稿。"""
    status = str(row.get("status") or "").strip().lower()
    if status == "event_enhancement":
        return "expansion"
    url = str(row.get("resolved_url") or row.get("source_url") or "").strip()
    role = (url_roles.get(url) or "").strip().lower()
    if role == "primary" or status == "ready_for_review":
        return "seed"
    return "cluster"


def _enhancement_dto(
    event_id: str,
    enhancement_row: dict[str, Any] | None,
    articles: list[dict[str, Any]],
) -> dict[str, Any]:
    expansion_count = sum(
        1 for a in articles if _article_source_kind(a, {}) == "expansion"
        or str(a.get("status") or "") == "event_enhancement"
    )
    seed_count = sum(1 for a in articles if str(a.get("status") or "") == "ready_for_review")
    if not enhancement_row:
        return {
            "ran": False,
            "status": "not_run",
            "ranAt": "",
            "seedArticleCount": seed_count,
            "articlesInserted": expansion_count,
            "candidatesFetched": 0,
            "similarityThreshold": 0.0,
            "queries": [],
            "sourceTrace": [],
            "skippedReason": "",
            "expandedArticles": [],
        }
    status = str(enhancement_row.get("status") or "unknown")
    passed = enhancement_row.get("urls_passed_similarity") or []
    expanded: list[dict[str, Any]] = []
    if isinstance(passed, list):
        for item in passed:
            if not isinstance(item, dict):
                continue
            expanded.append(
                {
                    "url": str(item.get("url") or ""),
                    "title": str(item.get("title") or "")[:200],
                    "similarity": round(float(item.get("similarity") or 0), 4),
                }
            )
    trace_out: list[dict[str, Any]] = []
    for tr in enhancement_row.get("source_trace") or []:
        if not isinstance(tr, dict):
            continue
        trace_out.append(
            {
                "source": str(tr.get("source") or ""),
                "query": str(tr.get("query") or "")[:120],
                "attempts": int(tr.get("attempts") or 0),
                "hits": int(tr.get("hits") or 0),
            }
        )
    inserted = int(enhancement_row.get("articles_inserted") or len(expanded))
    profile = enhancement_row.get("gdelt_query_profile") or {}
    if not isinstance(profile, dict):
        profile = {}
    return {
        "ran": True,
        "status": status,
        "ranAt": str(enhancement_row.get("_run_generated_at") or ""),
        "seedArticleCount": int(enhancement_row.get("seed_article_count") or seed_count),
        "articlesInserted": inserted,
        "candidatesFetched": int(enhancement_row.get("candidates_fetched") or 0),
        "similarityThreshold": float(enhancement_row.get("similarity_threshold") or 0.7),
        "queries": list(enhancement_row.get("queries") or [])[:5],
        "sourceTrace": trace_out,
        "skippedReason": str(enhancement_row.get("reason") or ""),
        "expandedArticles": expanded,
        "eventLang": str(enhancement_row.get("event_lang") or profile.get("event_lang") or ""),
        "gdeltSkipped": bool(
            enhancement_row.get("gdelt_skipped")
            if enhancement_row.get("gdelt_skipped") is not None
            else profile.get("gdelt_skipped")
        ),
        "searchCascade": list(profile.get("search_cascade") or []),
    }


def _build_timeline(
    event: dict[str, Any],
    articles: list[dict[str, Any]],
    *,
    url_roles: dict[str, str],
    enhancement: dict[str, Any],
) -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []
    for a in articles:
        kind = _article_source_kind(a, url_roles)
        ts = str(a.get("source_published_at") or a.get("created_at") or "")
        prefix = "【扩搜】" if kind == "expansion" else ""
        nodes.append(
            {
                "id": f"tl-{a.get('id', '')}",
                "at": ts,
                "label": f"{prefix}{str(a.get('title') or '')[:76]}",
                "type": "expansion" if kind == "expansion" else "article",
                "articleId": str(a.get("id") or ""),
                "sourceHost": str(a.get("source_host") or ""),
                "sourceKind": kind,
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
                "sourceKind": "",
            }
        )
    if enhancement.get("ran") and enhancement.get("ranAt"):
        ins = int(enhancement.get("articlesInserted") or 0)
        nodes.append(
            {
                "id": f"tl-enhance-{event.get('id', '')}",
                "at": str(enhancement.get("ranAt") or ""),
                "label": f"事件增强（扩搜入库 {ins} 篇）",
                "type": "enhancement",
                "articleId": "",
                "sourceHost": "",
                "sourceKind": "",
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
                "sourceKind": "",
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


def _sources_for_paragraph(
    para: str,
    articles: list[dict[str, Any]],
    dto_by_id: dict[str, dict[str, Any]],
) -> tuple[list[str], list[dict[str, Any]], float]:
    """按段落文本匹配当前库内文章，返回 id、DTO 与关联度。"""
    scored: list[tuple[float, str]] = []
    for a in articles:
        aid = str(a.get("id") or "")
        if not aid:
            continue
        body = " ".join(
            [
                str(a.get("title") or ""),
                str(a.get("extracted_text") or "")[:2000],
            ]
        )
        score = _overlap_score(para, body)
        if score > 0.03:
            scored.append((score, aid))
    scored.sort(key=lambda x: -x[0])
    if not scored and dto_by_id:
        fallback_ids = list(dto_by_id.keys())[:3]
        sources = [dto_by_id[i] for i in fallback_ids if i in dto_by_id]
        return fallback_ids, sources, 0.82
    ids = [aid for _, aid in scored[:3]]
    sources = [dto_by_id[aid] for aid in ids if aid in dto_by_id]
    top = scored[0][0] if scored else 0.0
    confidence = round(min(0.96, max(0.82, 0.80 + top * 0.35)), 2)
    return ids, sources, confidence


def _build_grounding(
    press: str,
    articles: list[dict[str, Any]],
    article_dtos: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    dto_by_id = {str(d.get("id") or ""): d for d in article_dtos if d.get("id")}
    spans: list[dict[str, Any]] = []
    for idx, para in enumerate(_split_paragraphs(press)):
        article_ids, sources, confidence = _sources_for_paragraph(para, articles, dto_by_id)
        spans.append(
            {
                "paragraphId": f"p{idx}",
                "text": para,
                "articleIds": article_ids,
                "sources": sources,
                "confidence": confidence,
            }
        )
    return spans


def _article_dto(
    row: dict[str, Any],
    press: str,
    *,
    url_roles: dict[str, str],
    expansion_similarity: float | None = None,
) -> dict[str, Any]:
    host = str(row.get("source_host") or "")
    if not host:
        try:
            host = urlparse(str(row.get("resolved_url") or row.get("source_url") or "")).netloc
        except Exception:
            host = ""
    body = str(row.get("extracted_text") or row.get("summary") or "")
    kind = _article_source_kind(row, url_roles)
    if expansion_similarity is not None and kind == "expansion":
        sim_display = round(min(0.99, expansion_similarity), 2)
    else:
        sim = _overlap_score(press, body) if press else 0.35
        sim_display = round(min(0.99, 0.4 + sim), 2)
    return {
        "id": str(row.get("id") or ""),
        "title": str(row.get("title") or ""),
        "url": _normalize_article_url(
            str(row.get("resolved_url") or row.get("source_url") or "")
        ),
        "sourceHost": host,
        "publishedAt": str(row.get("source_published_at") or row.get("created_at") or ""),
        "similarity": sim_display,
        "excerpt": body[:280] + ("…" if len(body) > 280 else ""),
        "rejected": str(row.get("status") or "").startswith("rejected"),
        "sourceKind": kind,
        "status": str(row.get("status") or ""),
        "mapRole": (url_roles.get(str(row.get("resolved_url") or row.get("source_url") or "").strip()) or ""),
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


def _expansion_similarity_by_url(enhancement_row: dict[str, Any] | None) -> dict[str, float]:
    out: dict[str, float] = {}
    if not enhancement_row:
        return out
    for item in enhancement_row.get("urls_passed_similarity") or []:
        if not isinstance(item, dict):
            continue
        url = str(item.get("url") or "").strip()
        if url:
            out[url] = float(item.get("similarity") or 0)
    return out


def event_to_intelligence(
    event: dict[str, Any],
    articles: list[dict[str, Any]],
    *,
    url_roles: dict[str, str] | None = None,
    enhancement_row: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Full detail DTO."""
    roles = url_roles or {}
    press = str(event.get("event_press_zh") or event.get("summary_zh") or event.get("summary") or "")
    if not press.strip():
        parts = [
            str(a.get("summary_zh") or a.get("summary") or "").strip()
            for a in articles
            if str(a.get("summary_zh") or a.get("summary") or "").strip()
        ]
        if parts:
            press = "\n\n".join(parts[:3])
    countries = sorted({_host_country(str(a.get("source_host") or "")) for a in articles})
    domains = sorted({str(a.get("source_host") or "") for a in articles if a.get("source_host")})
    enhancement = _enhancement_dto(str(event.get("id") or ""), enhancement_row, articles)
    sim_by_url = _expansion_similarity_by_url(enhancement_row)
    article_dtos = []
    for a in articles:
        url = str(a.get("resolved_url") or a.get("source_url") or "").strip()
        article_dtos.append(
            _article_dto(
                a,
                press,
                url_roles=roles,
                expansion_similarity=sim_by_url.get(url),
            )
        )
    article_dtos.sort(
        key=lambda x: (0 if x.get("sourceKind") == "seed" else 1 if x.get("sourceKind") == "expansion" else 2, x.get("title") or "")
    )
    return {
        "id": str(event.get("id") or ""),
        "title": str(event.get("title") or ""),
        "importance_score": _importance_score(event, articles),
        "qa_score": int(event.get("event_press_qa_score") or 0),
        "article_count": len(articles),
        "seed_article_count": sum(1 for x in article_dtos if x.get("sourceKind") == "seed"),
        "expansion_article_count": sum(1 for x in article_dtos if x.get("sourceKind") == "expansion"),
        "summary": press,
        "summaryPreview": press[:220] + ("…" if len(press) > 220 else ""),
        "keywords": _extract_keywords(event, articles),
        "countries": countries or ["CN"],
        "timeline": _build_timeline(event, articles, url_roles=roles, enhancement=enhancement),
        "articles": article_dtos,
        "sourceDomains": domains,
        "rewrite_history": _rewrite_history(event, press),
        "grounding": _build_grounding(press, articles, article_dtos),
        "qa": _qa_detail(event),
        "createdAt": str(event.get("created_at") or ""),
        "dominantTopicKey": str(event.get("dominant_topic_key") or ""),
        "enhancement": enhancement,
        "wechatDraftPushedAt": str(
            event.get("event_wechat_draft_pushed_at") or ""
        ),
    }


def event_to_list_item(
    event: dict[str, Any],
    articles: list[dict[str, Any]],
    *,
    url_roles: dict[str, str] | None = None,
    enhancement_row: dict[str, Any] | None = None,
) -> dict[str, Any]:
    full = event_to_intelligence(
        event, articles, url_roles=url_roles, enhancement_row=enhancement_row
    )
    enh = full.get("enhancement") or {}
    return {
        "id": full["id"],
        "title": full["title"],
        "importance_score": full["importance_score"],
        "qa_score": full["qa_score"],
        "article_count": full["article_count"],
        "seed_article_count": full.get("seed_article_count", 0),
        "expansion_article_count": full.get("expansion_article_count", 0),
        "enhancement_status": str(enh.get("status") or "not_run"),
        "enhancement_inserted": int(enh.get("articlesInserted") or 0),
        "summaryPreview": full["summaryPreview"],
        "keywords": full["keywords"][:6],
        "countries": full["countries"],
        "timeline": full["timeline"][-3:],
        "createdAt": full["createdAt"],
    }
