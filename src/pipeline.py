from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4

import httpx
from bs4 import BeautifulSoup

from src.ai import SummaryService
from src.config import Settings
from src.search import SearchHit, filter_by_age, search_with_toolchain
from src.storage import ArticleRecord, JsonStore
from src.wechat import WeChatDraftClient

logger = logging.getLogger(__name__)


@dataclass
class RunStats:
    total_candidates: int = 0
    published: int = 0
    skipped_duplicate: int = 0
    failed: int = 0


class PipelineRunner:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.store = JsonStore(settings.data_path())
        self.summarizer = SummaryService(
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url,
            model=settings.deepseek_model,
        )
        self.wechat = WeChatDraftClient(
            app_id=settings.wechat_mp_app_id,
            app_secret=settings.wechat_mp_app_secret,
            author=settings.wechat_mp_author,
        )

    async def run_once(self) -> RunStats:
        queries = self.settings.parsed_queries()
        target_sites = self.settings.parsed_target_sites()
        if not queries:
            raise ValueError("SEARCH_QUERIES 为空")
        if not self.settings.wechat_ready():
            raise ValueError("微信公众号参数未配置完整（WECHAT_MP_APP_ID / WECHAT_MP_APP_SECRET）")

        all_hits: list[SearchHit] = []
        for q in queries:
            rows, tool = await search_with_toolchain(
                query=q,
                max_results=self.settings.search_max_results,
                target_sites=target_sites,
                max_attempts_per_tool=3,
            )
            if not rows:
                raise RuntimeError(
                    f"外部搜索在 3 个工具链路内均失败或无结果，已暂停本次任务。query={q}, tool={tool}"
                )
            logger.info("query=%s selected_search_tool=%s rows=%d", q, tool, len(rows))
            all_hits.extend(rows)

        unique: dict[str, SearchHit] = {}
        for hit in all_hits:
            key = hit.url.strip().lower().rstrip("/")
            if key and key not in unique:
                unique[key] = hit
        candidates = filter_by_age(list(unique.values()), self.settings.max_article_age_hours)
        candidates = candidates[: self.settings.max_publish_per_run]

        thumb = self.settings.wechat_mp_thumb_media_id.strip()
        if not thumb:
            thumb = await self.wechat.upload_local_cover(self.settings.wechat_mp_thumb_local_path)

        stats = RunStats(total_candidates=len(candidates))
        for hit in candidates:
            try:
                title, text = await self._fetch_text(hit.url, fallback_title=hit.title, fallback_snippet=hit.snippet)
                if self.store.exists_duplicate(hit.url, title, text):
                    stats.skipped_duplicate += 1
                    continue
                summary = await self.summarizer.summarize(title=title, text=text, max_chars=2200)
                await self.wechat.add_draft(title=title, summary=summary, source_url=hit.url, thumb_media_id=thumb)
                rec = ArticleRecord(
                    id=str(uuid4()),
                    title=title,
                    source_url=hit.url,
                    source_published_at=hit.published_at,
                    extracted_text=text,
                    summary=summary,
                    status="published",
                    created_at=datetime.now(timezone.utc).isoformat(),
                    published_at=datetime.now(timezone.utc).isoformat(),
                )
                self.store.add(rec)
                stats.published += 1
            except Exception:
                logger.exception("处理失败: %s", hit.url)
                stats.failed += 1
        return stats

    async def _fetch_text(self, url: str, fallback_title: str, fallback_snippet: str) -> tuple[str, str]:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            resp = await client.get(url, headers={"User-Agent": "Mozilla/5.0"})
            resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        title = (soup.title.text.strip() if soup.title and soup.title.text else fallback_title).strip() or "来源文章"
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()
        parts: list[str] = []
        for p in soup.find_all(["p", "li", "h2", "h3"]):
            txt = (p.get_text(" ", strip=True) or "").strip()
            if len(txt) >= 25:
                parts.append(txt)
        text = "\n".join(parts)[:20000].strip() or fallback_snippet
        return title, text
