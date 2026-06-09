"""中文单篇 LLM 入库门禁（抓正文后）。"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from src.services.zh_ingest.prompt_load import load_zh_ingest_prompt
from src.utils.topic_prefilter import (
    EDITORIAL_FULL_TEXT_MAX,
    is_anti_china_smear_headline,
    is_taiwan_politics_headline,
    is_war_conflict_content,
)

if TYPE_CHECKING:
    from src.ai import SummaryService
    from src.config import Settings

logger = logging.getLogger(__name__)

_NEWS_ROUNDUP_RES = (
    re.compile(r"这些新规将(施行|影响)"),
    re.compile(r"影响你我生活"),
    re.compile(r"新规来了"),
    re.compile(r"一批涉及.+的(新规|规定)"),
    re.compile(r"(快讯|速览|速递).{0,8}(；|、|,)"),
)


@dataclass(frozen=True)
class ZhArticleGateResult:
    keep: bool
    is_domain_relevant: bool
    is_political_sensitive: bool
    is_anti_china_smear: bool
    category: str
    reason: str


def _is_news_roundup(*, title: str, text: str, snippet: str) -> bool:
    blob = f"{title}\n{snippet}\n{text[:2000]}"
    return any(r.search(blob) for r in _NEWS_ROUNDUP_RES)


def _deterministic_reject(
    *,
    title: str,
    snippet: str,
    text: str,
    url: str,
) -> ZhArticleGateResult | None:
    if is_war_conflict_content(title=title, snippet=snippet, text=text):
        return ZhArticleGateResult(
            keep=False,
            is_domain_relevant=False,
            is_political_sensitive=False,
            is_anti_china_smear=False,
            category="other",
            reason="战争冲突",
        )
    if is_taiwan_politics_headline(title=title, snippet=snippet, url=url, text=text):
        return ZhArticleGateResult(
            keep=False,
            is_domain_relevant=False,
            is_political_sensitive=True,
            is_anti_china_smear=False,
            category="other",
            reason="政治敏感",
        )
    if is_anti_china_smear_headline(title=title, snippet=snippet, text=text):
        return ZhArticleGateResult(
            keep=False,
            is_domain_relevant=False,
            is_political_sensitive=False,
            is_anti_china_smear=True,
            category="other",
            reason="抹黑唱衰",
        )
    if _is_news_roundup(title=title, text=text, snippet=snippet):
        return ZhArticleGateResult(
            keep=False,
            is_domain_relevant=False,
            is_political_sensitive=False,
            is_anti_china_smear=False,
            category="other",
            reason="新规拼盘",
        )
    return None


def _fallback_result(
    *,
    title: str,
    snippet: str,
    text: str,
    summarizer: SummaryService,
) -> ZhArticleGateResult:
    rel = summarizer._fallback_domain_relevance(title=title, text=text, snippet=snippet)
    political = is_taiwan_politics_headline(title=title, snippet=snippet, text=text)
    smear = is_anti_china_smear_headline(title=title, snippet=snippet, text=text)
    keep = bool(rel.get("is_relevant")) and not political and not smear
    return ZhArticleGateResult(
        keep=keep,
        is_domain_relevant=bool(rel.get("is_relevant")),
        is_political_sensitive=political,
        is_anti_china_smear=smear,
        category=str(rel.get("category", "other") or "other"),
        reason=str(rel.get("reason", "") or ("领域相关" if keep else "非本领域")),
    )


def _parse_gate_json(data: dict) -> ZhArticleGateResult:
    keep = bool(data.get("keep", False))
    is_domain = bool(data.get("is_domain_relevant", keep))
    political = bool(data.get("is_political_sensitive", False))
    smear = bool(data.get("is_anti_china_smear", False))
    if political or smear:
        keep = False
    category = str(data.get("category", "other") or "other").strip().lower()
    if category not in {"policy", "frontier", "industry", "other"}:
        category = "other"
    reason = str(data.get("reason", "") or "").strip()[:120]
    return ZhArticleGateResult(
        keep=keep and is_domain,
        is_domain_relevant=is_domain,
        is_political_sensitive=political,
        is_anti_china_smear=smear,
        category=category,
        reason=reason or ("保留" if keep else "拒绝"),
    )


async def assess_en_article(
    summarizer: SummaryService,
    settings: Settings,
    *,
    title: str,
    text: str,
    snippet: str = "",
    url: str = "",
) -> ZhArticleGateResult:
    """英文入库路径：与中文共用 LLM 领域门禁 prompt。"""
    return await assess_zh_article(
        summarizer,
        settings,
        title=title,
        text=text,
        snippet=snippet,
        url=url,
    )


async def assess_zh_article(
    summarizer: SummaryService,
    settings: Settings,
    *,
    title: str,
    text: str,
    snippet: str = "",
    url: str = "",
) -> ZhArticleGateResult:
    """
    单篇 LLM 入库门禁（中英共用 prompt）。

    确定性规则仅做战争/政治/抹黑等硬安全短路；领域相关性由 LLM 判定。
    """
    title = (title or "").strip()
    snippet = (snippet or "").strip()
    body = (text or "")[:EDITORIAL_FULL_TEXT_MAX]

    hard = _deterministic_reject(title=title, snippet=snippet, text=body, url=url)
    if hard is not None:
        return hard

    if not summarizer._api_key:
        return _fallback_result(title=title, snippet=snippet, text=body, summarizer=summarizer)

    system = load_zh_ingest_prompt("article_gate_system")
    user_tpl = load_zh_ingest_prompt("article_gate_user")
    user = (
        user_tpl.replace("{{URL}}", url or "")
        .replace("{{TITLE}}", title)
        .replace("{{SNIPPET}}", snippet[:800])
        .replace("{{BODY}}", body[:2000])
    )
    data = await summarizer._chat_json(
        system_prompt=system,
        user_prompt=user,
        timeout=45.0,
        max_tokens=220,
    )
    if not data:
        logger.warning("zh article gate LLM empty, fallback: %s", url[:80])
        return _fallback_result(title=title, snippet=snippet, text=body, summarizer=summarizer)
    try:
        return _parse_gate_json(data)
    except Exception:
        logger.warning("zh article gate parse failed, fallback: %s", url[:80], exc_info=True)
        return _fallback_result(title=title, snippet=snippet, text=body, summarizer=summarizer)
