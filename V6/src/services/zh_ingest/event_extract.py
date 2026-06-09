"""中文簇级 LLM 事件提炼（bge-m3 聚类之后）。"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from src.services.zh_ingest.prompt_load import load_zh_ingest_prompt
from src.utils.headline_zh import trim_zh_headline_heuristic
from src.utils.topic_prefilter import should_keep_editorial_content

if TYPE_CHECKING:
    from src.ai import SummaryService
    from src.config import Settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ZhClusterExtractResult:
    event_title_zh: str
    event_title_en: str
    keep_cluster: bool
    reject_reason: str


def _articles_block(cluster: list[Any], *, excerpt_chars: int = 1200) -> str:
    lines: list[str] = []
    for i, p in enumerate(cluster, start=1):
        title = getattr(p, "title", "") or ""
        snippet = ""
        hit = getattr(p, "hit", None)
        if hit is not None:
            snippet = getattr(hit, "snippet", "") or ""
        text = (getattr(p, "text", "") or "")[:excerpt_chars]
        url = getattr(p, "final_url", "") or ""
        if not url and hit is not None:
            url = getattr(hit, "url", "") or ""
        lines.append(
            f"【{i}】标题：{title}\n来源：{url}\n摘要：{snippet[:400]}\n正文节选：{text}\n"
        )
    return "\n".join(lines)


def _fallback_extract(cluster: list[Any], *, max_chars: int) -> ZhClusterExtractResult:
    primary = cluster[0]
    title = (getattr(primary, "title", "") or "").strip()
    blob_parts = [title]
    for p in cluster:
        blob_parts.append(getattr(p, "text", "")[:800])
    blob = "\n".join(blob_parts)
    url = getattr(primary, "final_url", "") or ""
    hit = getattr(primary, "hit", None)
    if hit is not None:
        url = url or getattr(hit, "url", "") or ""
    keep = should_keep_editorial_content(
        title=title,
        snippet=(getattr(hit, "snippet", "") if hit else "") or "",
        text=blob,
        url=url,
    )
    event_zh = trim_zh_headline_heuristic(title, max_len=max_chars) if keep else ""
    return ZhClusterExtractResult(
        event_title_zh=event_zh,
        event_title_en="",
        keep_cluster=keep,
        reject_reason="" if keep else "关键词离题",
    )


def _parse_extract_json(data: dict, *, max_chars: int) -> ZhClusterExtractResult:
    keep = bool(data.get("keep_cluster", True))
    reason = str(data.get("reject_reason", "") or "").strip()[:120]
    event_zh = trim_zh_headline_heuristic(
        str(data.get("event_title_zh", "") or "").strip(),
        max_len=max_chars,
    )
    event_en = str(data.get("event_title_en", "") or "").strip()[:120]
    if not keep:
        event_zh = ""
        event_en = ""
    elif not event_zh:
        keep = False
        reason = reason or "无有效事件句"
    return ZhClusterExtractResult(
        event_title_zh=event_zh,
        event_title_en=event_en,
        keep_cluster=keep,
        reject_reason=reason,
    )


async def extract_zh_cluster_event(
    summarizer: SummaryService,
    settings: Settings,
    cluster: list[Any],
) -> ZhClusterExtractResult:
    """读全簇文章，输出 ~20 字中文事件句；离题簇 keep_cluster=false。"""
    max_chars = int(settings.zh_llm_event_extract_max_chars)
    if not cluster:
        return ZhClusterExtractResult("", "", False, "空簇")

    if not summarizer._api_key:
        return _fallback_extract(cluster, max_chars=max_chars)

    system = load_zh_ingest_prompt("event_extract_system").replace(
        "{{MAX_CHARS}}", str(max_chars)
    )
    user_tpl = load_zh_ingest_prompt("event_extract_user")
    block = _articles_block(cluster)
    user = user_tpl.replace("{{ARTICLE_COUNT}}", str(len(cluster))).replace(
        "{{ARTICLES_BLOCK}}", block
    )
    data = await summarizer._chat_json(
        system_prompt=system,
        user_prompt=user,
        timeout=60.0,
        max_tokens=280,
    )
    if not data:
        logger.warning("zh cluster extract LLM empty, fallback cluster_size=%d", len(cluster))
        return _fallback_extract(cluster, max_chars=max_chars)
    try:
        return _parse_extract_json(data, max_chars=max_chars)
    except Exception:
        logger.warning("zh cluster extract parse failed", exc_info=True)
        return _fallback_extract(cluster, max_chars=max_chars)
