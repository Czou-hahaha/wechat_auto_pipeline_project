from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from urllib.parse import urljoin
from uuid import uuid4
import re
from time import perf_counter
from difflib import SequenceMatcher

import httpx
from bs4 import BeautifulSoup

from src.ai import SummaryService
from src.config import Settings
from src.ingest_cluster import build_embedding_event_clusters
from src.rss_aggregate import aggregate_rss_from_data_sources
from src.search import (
    SearchHit,
    filter_by_age,
    merge_search_hits,
    normalize_title,
    search_gdelt_topics_bilingual,
    search_with_toolchain,
)
from src.storage import ArticleRecord, EventRecord, JsonStore
from src.utils.article_extract import main_text_with_trafilatura_fallback
from src.utils.http_decode import decode_http_html_bytes
from src.wechat import WeChatDraftClient

logger = logging.getLogger(__name__)


def _load_published_at_css_by_host(settings: Settings) -> dict[str, list[str]]:
    """从 ``data_sources.json`` 读取 ``published_at_css``（按 ``value`` 域名索引，可多段合并）。"""
    path = Path((settings.his_data_sources_path or "").strip()).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    if not path.is_file():
        return {}
    try:
        rows = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        logger.warning("published_at_css: failed to read %s", path, exc_info=True)
        return {}
    if not isinstance(rows, list):
        return {}
    out: dict[str, list[str]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        val = str(row.get("value") or "").strip().lower()
        if not val:
            continue
        raw_css = row.get("published_at_css")
        sels: list[str] = []
        if isinstance(raw_css, str) and raw_css.strip():
            sels = [raw_css.strip()]
        elif isinstance(raw_css, list):
            sels = [str(x).strip() for x in raw_css if str(x).strip()]
        if not sels:
            continue
        prev = out.get(val, [])
        seen: set[str] = set()
        merged: list[str] = []
        for x in prev + sels:
            if x not in seen:
                seen.add(x)
                merged.append(x)
        out[val] = merged
    return out


@dataclass
class RunStats:
    total_candidates: int = 0
    published: int = 0
    skipped_duplicate: int = 0
    skipped_policy: int = 0
    skipped_encoding: int = 0
    skipped_digest: int = 0
    skipped_too_short: int = 0
    skipped_summary_fallback: int = 0
    skipped_qa: int = 0
    staged_for_review: int = 0
    failed: int = 0


# 快餐/合集栏目标题：与政策、产业、技术主线弱相关，不入库
_DIGEST_TITLE_RES = (
    re.compile(r"科技早报"),
    re.compile(r"财经早报"),
    re.compile(r"商业早报"),
    re.compile(r"晨报\s*[-|｜·]"),
    re.compile(r"早报\s*[-|｜·]"),
    re.compile(r"午夜快讯"),
    re.compile(r"今日要闻"),
    re.compile(r"一图读懂"),
    re.compile(r"\d+\s*秒读懂"),
    re.compile(r"[「【]早间?(速递|速览|必读)[」】]"),
    re.compile(r"(午|晚)报\s*[-|｜·].{0,80}[；;]"),
)

_NEWS_ROUNDUP_TITLE_RES = (
    re.compile(r"新规来了"),
    re.compile(r"这些新规将施行"),
    re.compile(r"这些新规将影响"),
    re.compile(r"影响你我生活"),
    re.compile(r"重磅新规落地"),
    re.compile(r"今起\d+项国家标准开始实施"),
    re.compile(r"快讯"),
    re.compile(r"速览"),
    re.compile(r"速递"),
)

_LOW_ALTITUDE_RELEVANCE_CJK_KEYWORDS = (
    "低空",
    "无人机",
    "无人驾驶航空器",
    "民航局",
    "通用航空",
    "飞行汽车",
    "空域",
)

_LOW_ALTITUDE_RELEVANCE_LATIN_KEYWORDS = (
    "evtol",
    "uam",
    "drone",
    "uav",
)


@dataclass
class TodayDraftPushStats:
    """将本地库中「指定本地日」已摘要稿件写入公众号草稿箱（不重新搜索）。"""

    eligible: int = 0
    skipped_already: int = 0
    skipped_empty: int = 0
    skipped_outdated: int = 0
    skipped_qa: int = 0
    pushed: int = 0
    failed: int = 0


@dataclass
class LibraryCleanStats:
    total: int = 0
    kept: int = 0
    removed: int = 0
    removed_missing_time: int = 0
    removed_time_window: int = 0
    removed_scope: int = 0
    removed_policy: int = 0
    removed_low_relevance: int = 0
    removed_digest: int = 0
    removed_too_short: int = 0


@dataclass
class PreparedArticle:
    hit: SearchHit
    title: str
    text: str
    final_url: str
    first_image_url: str | None
    source_host: str
    source_published_at: str
    source_published_at_date_only: bool
    topic_is_important: bool
    topic_category: str
    topic_key: str
    deepseek_semantic_decision: str
    novelty_passed: bool


class PipelineRunner:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.store = JsonStore(settings.data_path())
        self._published_css_by_host = _load_published_at_css_by_host(settings)
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

    def _global_dedupe_prepared(self, items: list[PreparedArticle], stats: RunStats) -> list[PreparedArticle]:
        """本批候选在抓取后的全局去重（URL/标题/正文近重复）。"""
        ordered = sorted(items, key=lambda p: p.source_published_at or "")
        kept: list[PreparedArticle] = []
        for p in ordered:
            if any(self._prepared_near_duplicate(p, k) for k in kept):
                stats.skipped_duplicate += 1
                logger.info("global batch dedupe skip: %s", p.hit.url)
                continue
            kept.append(p)
        return kept

    @staticmethod
    def _prepared_near_duplicate(a: PreparedArticle, b: PreparedArticle) -> bool:
        na = JsonStore._norm_text(a.title)
        nb = JsonStore._norm_text(b.title)
        if na and nb and JsonStore.titles_duplicated(na, nb):
            return True
        ta = JsonStore._norm_text(a.text)[:3000]
        tb = JsonStore._norm_text(b.text)[:3000]
        if ta and tb and len(ta) >= 200 and len(tb) >= 200 and SequenceMatcher(None, ta, tb).ratio() >= 0.88:
            return True
        fa = JsonStore.url_fingerprint(a.final_url or a.hit.url)
        fb = JsonStore.url_fingerprint(b.final_url or b.hit.url)
        return bool(fa and fb and fa == fb)

    def _clusters_from_prepared(self, items: list[PreparedArticle]) -> list[list[PreparedArticle]]:
        groups: dict[str, list[PreparedArticle]] = defaultdict(list)
        tails: list[PreparedArticle] = []
        for p in items:
            if p.topic_is_important and p.topic_key:
                groups[p.topic_key].append(p)
            else:
                tails.append(p)
        clusters = [v for v in groups.values() if v] + [[x] for x in tails]
        return self._merge_soft_policy_clusters(clusters)

    def _merge_soft_policy_clusters(self, clusters: list[list[PreparedArticle]]) -> list[list[PreparedArticle]]:
        """同窗内政策相关（如禁飞/禁售）且均为重要 topic 的簇做软合并。"""
        n = len(clusters)
        if n <= 1:
            return clusters
        parent = list(range(n))

        def find(i: int) -> int:
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i

        def union(i: int, j: int) -> None:
            ri, rj = find(i), find(j)
            if ri != rj:
                parent[rj] = ri

        for i in range(n):
            for j in range(i + 1, n):
                if self._clusters_policy_mergeable(clusters[i], clusters[j]):
                    union(i, j)
        buckets: dict[int, list[PreparedArticle]] = defaultdict(list)
        for i in range(n):
            buckets[find(i)].extend(clusters[i])
        return list(buckets.values())

    def _clusters_policy_mergeable(self, a: list[PreparedArticle], b: list[PreparedArticle]) -> bool:
        if not any(p.topic_is_important for p in a) or not any(p.topic_is_important for p in b):
            return False
        span = self._cluster_time_span_hours(a + b)
        if span > float(self.settings.cluster_merge_hours):
            return False
        titles = [p.title for p in a] + [p.title for p in b]
        return self._policy_drone_ban_pack(titles)

    @staticmethod
    def _policy_drone_ban_pack(titles: list[str]) -> bool:
        blob = " ".join(titles)
        drone = ("无人机" in blob) or ("无人驾驶" in blob) or ("drone" in blob.lower())
        ban = ("禁飞" in blob) or ("禁售" in blob)
        return drone and ban

    def _cluster_time_span_hours(self, parts: list[PreparedArticle]) -> float:
        times: list[datetime] = []
        for p in parts:
            dt = self._parse_iso_datetime(p.source_published_at)
            if dt is not None:
                times.append(dt)
        if len(times) < 2:
            return 0.0
        return (max(times) - min(times)).total_seconds() / 3600.0

    def _dedupe_within_cluster(self, cluster: list[PreparedArticle]) -> list[PreparedArticle]:
        ordered = sorted(cluster, key=lambda p: p.source_published_at or "")
        kept: list[PreparedArticle] = []
        for p in ordered:
            if any(self._prepared_near_duplicate(p, k) for k in kept):
                continue
            kept.append(p)
        return kept[:8] if kept else []

    def _order_clusters_for_publish(self, clusters: list[list[PreparedArticle]]) -> list[list[PreparedArticle]]:
        tz = ZoneInfo(self.settings.schedule_timezone.strip() or "Asia/Shanghai")
        today = datetime.now(tz).date()
        existing_topics: set[str] = set()
        for row in self.store.list_all():
            if not isinstance(row, dict):
                continue
            if not bool(row.get("topic_is_important", False)):
                continue
            topic = str(row.get("topic_key", "") or "").strip().lower()
            if not topic:
                continue
            created = self._parse_iso_datetime(str(row.get("created_at") or ""))
            if created and created.astimezone(tz).date() == today:
                existing_topics.add(topic)

        def is_important_cluster(c: list[PreparedArticle]) -> bool:
            return any(p.topic_is_important and p.topic_key for p in c)

        important_clusters = [c for c in clusters if is_important_cluster(c)]
        other_clusters = [c for c in clusters if not is_important_cluster(c)]
        important_clusters.sort(key=len, reverse=True)
        topic_slots = max(0, 7 - len(existing_topics))
        out: list[list[PreparedArticle]] = []
        for c in important_clusters:
            primary_key = self._dominant_topic_key_for_cluster(c)
            if primary_key:
                if primary_key not in existing_topics:
                    if topic_slots <= 0:
                        continue
                    topic_slots -= 1
                history_count = self.store.count_unique_sources_for_topic(primary_key)
                if history_count >= 3 and not any(p.novelty_passed for p in c):
                    logger.info("skip cluster: no novelty vs history topic=%s", primary_key)
                    continue
            out.append(c)
            if primary_key:
                existing_topics.add(primary_key)
        out.extend(other_clusters)
        return out

    @staticmethod
    def _dominant_topic_key_for_cluster(cluster: list[PreparedArticle]) -> str:
        keys = [p.topic_key for p in cluster if p.topic_is_important and p.topic_key]
        if not keys:
            return ""
        counts: dict[str, int] = defaultdict(int)
        for k in keys:
            counts[k] += 1
        return max(counts.items(), key=lambda kv: kv[1])[0]

    @staticmethod
    def _pick_primary_article(cluster: list[PreparedArticle]) -> PreparedArticle:
        imp = [p for p in cluster if p.topic_is_important]
        pool = imp or cluster
        return sorted(pool, key=lambda p: p.source_published_at or "")[0]

    @staticmethod
    def _log_cluster_overview(clusters: list[list[PreparedArticle]]) -> None:
        if not clusters:
            logger.info("clusters overview: none")
            return
        sizes = [len(c) for c in clusters]
        logger.info("clusters overview: count=%d sizes=%s", len(clusters), sizes[:30])
        for i, c in enumerate(clusters[:15], start=1):
            titles = " | ".join(x.title[:56] for x in c[:4])
            logger.info("cluster[%d] n=%d sample=%s", i, len(c), titles)

    async def _run_mandatory_event_enhancement_post_pipeline(self) -> None:
        """事件增强为必选阶段；所有 ``run_once`` 出口（含提前 return）前须调用。"""
        try:
            from src.event_enhancement_workflow import run_event_enhancement_post_pipeline

            await run_event_enhancement_post_pipeline(self.store, self.settings)
        except ImportError as exc:
            raise RuntimeError(
                "事件增强为必选阶段：请安装依赖 pip install -r requirements.txt "
                "（含 sqlalchemy asyncio asyncpg numpy faiss-cpu pyyaml）"
            ) from exc
        await self._run_optional_event_press_post_pipeline()

    async def _run_optional_event_press_post_pipeline(self) -> None:
        """阶段四：多源事件通稿。失败不阻断 ``run_once``。"""
        try:
            from src.event_press_workflow import run_event_press_generation

            await run_event_press_generation(self.store, self.settings, force=False)
        except Exception:
            logger.exception("event press post-pipeline failed (ignored)")

    async def run_once(self) -> RunStats:
        target_sites = self.settings.parsed_target_sites()
        publish_to_wechat = bool(self.settings.run_once_push_to_wechat)
        if publish_to_wechat and not self.settings.wechat_ready():
            raise ValueError("微信公众号参数未配置完整（WECHAT_MP_APP_ID / WECHAT_MP_APP_SECRET）")

        logger.info(
            "run_once ingest: rss_then_gdelt | gdelt_site_scoped=%s target_sites=%d",
            self.settings.gdelt_site_scoped_enabled,
            len(target_sites),
        )
        logger.info(
            "deepseek semantic dedupe criteria: same event + no new facts => duplicate; "
            "new policy clause/data/timeline/regulatory action => allow as new info"
        )
        rss_hits: list[SearchHit] = []
        if self.settings.rss_aggregate_enabled:
            rss_hits = await aggregate_rss_from_data_sources(self.settings)
        logger.info("phase0 rss aggregate rows=%d", len(rss_hits))

        search_started = perf_counter()
        site_phase_hits: list[SearchHit] = []
        global_phase_hits: list[SearchHit] = []
        site_phase_effective = False
        merge_cap = max(1500, int(self.settings.search_max_results) * 50)
        gdelt_http = 0

        if self.settings.gdelt_site_scoped_enabled and target_sites:
            site_queries = self.settings.parsed_site_queries()
            global_queries = self.settings.parsed_global_queries()
            if not global_queries and not site_queries:
                raise ValueError("SEARCH_QUERIES 为空")
            logger.info(
                "phase1 legacy gdelt site-scoped: queries=%d sites=%d",
                len(site_queries),
                len(target_sites),
            )
            site_gdelt_any = False
            for q in site_queries:
                q_started = perf_counter()
                rows, tool = await search_with_toolchain(
                    query=q,
                    max_results=self.settings.search_max_results,
                    target_sites=target_sites,
                    max_attempts_per_tool=3,
                    allow_global_fallback=False,
                )
                if not rows:
                    logger.warning(
                        "site gdelt returned no rows for query=%s tool=%s elapsed=%.2fs",
                        q,
                        tool,
                        perf_counter() - q_started,
                    )
                    continue
                site_gdelt_any = True
                logger.info(
                    "site gdelt query=%s tool=%s rows=%d elapsed=%.2fs",
                    q,
                    tool,
                    len(rows),
                    perf_counter() - q_started,
                )
                site_phase_hits.extend(rows)

            if site_gdelt_any:
                site_phase_effective = True
                logger.info("phase1 satisfied: site gdelt rows=%d", len(site_phase_hits))
            else:
                logger.info("phase2 legacy gdelt global: queries=%d", len(global_queries))
                for q in global_queries:
                    q_started = perf_counter()
                    rows, tool = await search_with_toolchain(
                        query=q,
                        max_results=self.settings.search_max_results,
                        target_sites=[],
                        max_attempts_per_tool=3,
                    )
                    if not rows:
                        logger.warning(
                            "global gdelt no rows for query=%s tool=%s elapsed=%.2fs",
                            q,
                            tool,
                            perf_counter() - q_started,
                        )
                        continue
                    logger.info(
                        "global gdelt query=%s tool=%s rows=%d elapsed=%.2fs",
                        q,
                        tool,
                        len(rows),
                        perf_counter() - q_started,
                    )
                    global_phase_hits.extend(rows)
        else:
            zh_kw = self.settings.parsed_chinese_keywords()
            en_kw = self.settings.parsed_english_keywords()
            if not zh_kw and not en_kw:
                raise ValueError(
                    "请在 config/search_keywords.json 中配置 chinese_keywords 与/或 english_keywords（低空主题检索词）"
                )
            global_phase_hits, gdelt_http = await search_gdelt_topics_bilingual(self.settings)
            logger.info(
                "gdelt topic bilingual rows=%d http_requests=%d zh_terms=%d en_terms=%d",
                len(global_phase_hits),
                gdelt_http,
                len(zh_kw),
                len(en_kw),
            )

        all_hits = merge_search_hits(rss_hits, site_phase_hits, global_phase_hits, max_total=merge_cap)
        logger.info(
            "search phase result: site_phase_effective=%s site_gdelt_rows=%d global_gdelt_rows=%d merged=%d",
            site_phase_effective,
            len(site_phase_hits),
            len(global_phase_hits),
            len(all_hits),
        )
        logger.info("rss+gdelt ingest total elapsed=%.2fs", perf_counter() - search_started)
        if not all_hits:
            logger.warning("no search hits in current run; return 0 published")
            await self._run_mandatory_event_enhancement_post_pipeline()
            return RunStats(total_candidates=0)

        unique: dict[str, SearchHit] = {}
        for hit in all_hits:
            key = self._canonical_url(hit.url)
            if key and key not in unique:
                unique[key] = hit
        candidates = filter_by_age(list(unique.values()), self.settings.max_article_age_hours)
        candidates = candidates[: max(self.settings.max_publish_per_run, 50)]

        thumb = ""
        if publish_to_wechat:
            thumb = self.settings.wechat_mp_thumb_media_id.strip()
            if not thumb:
                thumb = await self.wechat.upload_local_cover(self.settings.wechat_mp_thumb_local_path)

        stats = RunStats(total_candidates=len(candidates))
        processed_keys: set[str] = set()
        processed_title_norms: set[str] = set()
        seen_landing_fingerprints: set[str] = set()
        seen_search_title_norms: set[str] = set()
        prepared_buffer: list[PreparedArticle] = []
        for hit in candidates:
            try:
                key = self._canonical_url(hit.url)
                if key and key in processed_keys:
                    stats.skipped_duplicate += 1
                    continue
                probe_title = normalize_title((hit.title or "").strip())
                probe_norm = JsonStore._norm_text(probe_title)
                if len(probe_norm) >= 8 and any(
                    JsonStore.titles_duplicated(probe_norm, prev) for prev in seen_search_title_norms
                ):
                    stats.skipped_duplicate += 1
                    logger.info("skip duplicate title vs same-run candidates: %s", hit.url)
                    continue
                if probe_norm and self.store.title_duplicate_against_history(probe_title):
                    stats.skipped_duplicate += 1
                    logger.info("skip duplicate title vs history (before fetch): %s", hit.url)
                    continue
                if self._is_low_signal_digest_column(probe_title, hit.snippet):
                    stats.skipped_digest += 1
                    logger.info("skip digest/column headline (before fetch): %s", hit.url)
                    continue
                title, text, first_image_url, final_url, page_published_at, page_date_only = await self._fetch_text(
                    hit.url, fallback_title=hit.title, fallback_snippet=hit.snippet
                )
                if site_phase_effective and not self._host_matches_target_sites(
                    url=final_url or hit.url,
                    target_sites=target_sites,
                ) and not getattr(hit, "from_rss", False):
                    stats.skipped_policy += 1
                    logger.info("skip leaked non-target host in site phase: %s", final_url or hit.url)
                    continue
                source_published_at, date_only = self._resolve_source_published_at(
                    page_published_at=page_published_at,
                    page_date_only_coarse=page_date_only,
                )
                if not source_published_at:
                    stats.skipped_policy += 1
                    logger.info(
                        "skip missing page published_at: url=%s search_published_at=%s page_published_at=%s",
                        final_url or hit.url,
                        hit.published_at,
                        page_published_at,
                    )
                    continue
                if not self._published_at_within_window(
                    source_published_at=source_published_at,
                    max_hours=self.settings.max_article_age_hours,
                    date_only_coarse=date_only,
                ):
                    stats.skipped_policy += 1
                    logger.info(
                        "skip by published_at guard: url=%s search_published_at=%s page_published_at=%s resolved=%s date_only=%s",
                        final_url or hit.url,
                        hit.published_at,
                        page_published_at,
                        source_published_at,
                        date_only,
                    )
                    continue
                if self._blocked_ingest_host(final_url or hit.url):
                    stats.skipped_policy += 1
                    logger.info("skip blocked ingest host: %s", final_url or hit.url)
                    continue
                if self._is_probable_charset_garbage(title=title, text=text):
                    stats.skipped_encoding += 1
                    logger.info("skip probable charset / surface garbage page: %s", final_url or hit.url)
                    continue
                if self._is_low_signal_digest_column(title, text[:800]):
                    stats.skipped_digest += 1
                    logger.info("skip digest/column headline (after fetch): %s", final_url or hit.url)
                    continue
                if not self._passes_scope_gate(
                    title=title,
                    text=text,
                    snippet=hit.snippet,
                    source_url=final_url or hit.url,
                ):
                    stats.skipped_policy += 1
                    continue
                norm_title_key = JsonStore._norm_text(title)
                if len(norm_title_key) >= 12 and any(
                    JsonStore.titles_duplicated(norm_title_key, prev) for prev in processed_title_norms
                ):
                    stats.skipped_duplicate += 1
                    continue
                land_fp = JsonStore.url_fingerprint(final_url)
                if land_fp and land_fp in seen_landing_fingerprints:
                    stats.skipped_duplicate += 1
                    continue
                if self.store.exists_duplicate(hit.url, title, text, landing_url=final_url):
                    stats.skipped_duplicate += 1
                    continue
                if self._is_too_short(text, min_chars=400):
                    stats.skipped_too_short += 1
                    logger.info("skip too short article (<400 chars): %s", hit.url)
                    continue
                if self._is_policy_blocked(title=title, text=text, source_url=hit.url):
                    stats.skipped_policy += 1
                    logger.info("skip policy-blocked article: %s", hit.url)
                    continue
                topic = await self.summarizer.classify_topic(title=title, text=text)
                source_host = (urlparse(final_url or hit.url).hostname or "").lower()
                semantic_decision = ""
                novelty_passed = True
                if topic.get("is_important"):
                    topic_key = str(topic.get("topic_key", "")).strip().lower()
                    if not topic_key:
                        topic = {"is_important": False, "category": "other", "topic_key": ""}
                    else:
                        history_rows = self.store.find_by_topic_key(topic_key)
                        history_unique_sources = self.store.count_unique_sources_for_topic(topic_key)
                        logger.info(
                            "important topic detected: topic=%s category=%s title=%s history_sources=%d",
                            topic_key,
                            topic.get("category", "other"),
                            title[:80],
                            history_unique_sources,
                        )
                        if history_rows:
                            sem = await self.summarizer.semantic_duplicate_decision(
                                title=title,
                                text=text,
                                candidates=history_rows[-5:],
                            )
                            semantic_decision = sem.get("reason", "")
                            novelty_passed = bool(sem.get("has_new_info", True))
                            logger.info(
                                "important semantic decision: topic=%s is_duplicate=%s has_new_info=%s reason=%s",
                                topic_key,
                                sem.get("is_duplicate", False),
                                novelty_passed,
                                semantic_decision,
                            )
                            if history_unique_sources >= 3 and sem.get("is_duplicate") and not novelty_passed:
                                stats.skipped_duplicate += 1
                                logger.info("skip duplicate important topic after quota: %s topic=%s", hit.url, topic_key)
                                continue
                else:
                    sem = await self.summarizer.semantic_duplicate_decision(
                        title=title,
                        text=text,
                        candidates=self.store.semantic_candidates(limit=8, important_only=False),
                    )
                    semantic_decision = sem.get("reason", "")
                    logger.info(
                        "non-important semantic decision: title=%s is_duplicate=%s has_new_info=%s reason=%s",
                        title[:80],
                        sem.get("is_duplicate", False),
                        sem.get("has_new_info", True),
                        semantic_decision,
                    )
                    if sem.get("is_duplicate"):
                        stats.skipped_duplicate += 1
                        logger.info("skip semantic duplicate non-important: %s", hit.url)
                        continue

                prepared = PreparedArticle(
                    hit=hit,
                    title=title,
                    text=text,
                    final_url=final_url or "",
                    first_image_url=first_image_url,
                    source_host=source_host,
                    source_published_at=source_published_at,
                    source_published_at_date_only=date_only,
                    topic_is_important=bool(topic.get("is_important", False)),
                    topic_category=str(topic.get("category", "other") or "other"),
                    topic_key=str(topic.get("topic_key", "") or "").strip().lower(),
                    deepseek_semantic_decision=semantic_decision,
                    novelty_passed=novelty_passed,
                )
                prepared_buffer.append(prepared)
                if key:
                    processed_keys.add(key)
                if len(norm_title_key) >= 12:
                    processed_title_norms.add(norm_title_key)
                if land_fp:
                    seen_landing_fingerprints.add(land_fp)
                if len(probe_norm) >= 8:
                    seen_search_title_norms.add(probe_norm)
            except Exception:
                logger.exception("处理失败: %s", hit.url)
                stats.failed += 1

        emb_clusters = await build_embedding_event_clusters(prepared_buffer, self.settings)
        if emb_clusters is None:
            prepared_buffer = self._global_dedupe_prepared(prepared_buffer, stats)
            clusters_merged = self._clusters_from_prepared(prepared_buffer)
        else:
            clusters_merged, reprint_dropped = emb_clusters
            stats.skipped_duplicate += int(reprint_dropped)
            clusters_merged = self._merge_soft_policy_clusters(clusters_merged)
        clusters_deduped: list[list[PreparedArticle]] = []
        for c in clusters_merged:
            d = self._dedupe_within_cluster(c)
            if d:
                clusters_deduped.append(d)
        ordered_clusters = self._order_clusters_for_publish(clusters_deduped)
        self._log_cluster_overview(ordered_clusters)

        publish_limit = self.settings.max_publish_per_run
        if publish_to_wechat:
            publish_limit = self._remaining_daily_publish_slots()
            if publish_limit <= 0:
                logger.info("daily publish cap reached, skip wechat push in this run")
                await self._run_mandatory_event_enhancement_post_pipeline()
                return stats
        for cluster in ordered_clusters[:publish_limit]:
            try:
                deduped = cluster
                primary = self._pick_primary_article(deduped)
                cluster_payload = [
                    {"title": x.title, "text": x.text[:8000], "source_host": x.source_host} for x in deduped
                ]
                draft_title, summary = await self.summarizer.summarize_cluster(
                    items=cluster_payload,
                    max_chars=2200,
                    min_chars=400,
                )
                if not (draft_title or "").strip():
                    draft_title = primary.title
                if (summary or "").lstrip().startswith("【摘要】"):
                    stats.skipped_summary_fallback += 1
                    logger.info("skip fallback summary (not strict deepseek output): %s", primary.hit.url)
                    continue
                if self._is_too_short(summary, min_chars=400):
                    stats.skipped_too_short += 1
                    logger.info("skip summary shorter than 400 chars: %s", primary.hit.url)
                    continue
                summary_zh = ""
                display_title = draft_title
                display_summary = summary
                if self.settings.event_translate_summary_enabled:
                    tzh, szh = await self.summarizer.translate_title_summary_to_zh(
                        title=draft_title,
                        summary=summary,
                    )
                    if tzh:
                        display_title = tzh
                    if szh:
                        display_summary = szh
                        summary_zh = szh
                combined_text = "\n\n".join(p.text[:3000] for p in deduped)
                dom_key = self._dominant_topic_key_for_cluster(deduped)
                if not self._passes_scope_gate(
                    title=display_title,
                    text=f"{combined_text[:1800]}\n{display_summary[:1000]}",
                    snippet="",
                    source_url=primary.final_url or primary.hit.url,
                ):
                    stats.skipped_policy += 1
                    logger.info("skip by pre-push scope recheck: %s", primary.hit.url)
                    continue
                qa = await self.summarizer.review_summary_for_publish(
                    title=display_title,
                    source_url=primary.final_url or primary.hit.url,
                    source_published_at=primary.source_published_at,
                    source_text=combined_text,
                    summary=display_summary,
                    max_article_age_hours=self.settings.max_article_age_hours,
                    min_score=self.settings.summary_qa_min_score,
                    enabled=self.settings.summary_qa_enabled,
                    source_published_at_date_only=primary.source_published_at_date_only,
                    date_only_max_calendar_age_days=self.settings.date_only_max_calendar_age_days,
                    schedule_timezone=self.settings.schedule_timezone,
                )
                if not qa.get("pass", False):
                    stats.skipped_qa += 1
                    logger.info(
                        "skip by deepseek qa: url=%s score=%s hard_fails=%s verdict=%s",
                        primary.hit.url,
                        qa.get("score", 0),
                        qa.get("hard_fail_items", []),
                        qa.get("quick_verdict", ""),
                    )
                    continue
                event_id = str(uuid4())
                status = "ready_for_review"
                published_at = ""
                wechat_draft_pushed_at = ""
                if publish_to_wechat:
                    thumb_media_id = thumb
                    if primary.first_image_url:
                        try:
                            thumb_media_id = await self.wechat.upload_cover_from_url(primary.first_image_url)
                        except Exception as exc:
                            logger.warning(
                                "first image cover upload failed, fallback to default thumb: %s err=%s",
                                primary.first_image_url,
                                exc,
                            )
                    else:
                        logger.info(
                            "no valid first-image candidate found, fallback to default thumb: %s",
                            primary.hit.url,
                        )
                    await self._push_draft(
                        title=display_title,
                        summary=display_summary,
                        source_url=primary.hit.url,
                        thumb_media_id=thumb_media_id,
                        default_thumb=thumb,
                    )
                    status = "published"
                    published_at = datetime.now(timezone.utc).isoformat()
                    wechat_draft_pushed_at = published_at
                unique_hosts = {p.source_host for p in deduped if p.source_host}
                topic_src = len(unique_hosts)
                rec = ArticleRecord(
                    id=str(uuid4()),
                    title=display_title,
                    source_url=primary.hit.url,
                    source_published_at=primary.source_published_at,
                    source_published_at_date_only=primary.source_published_at_date_only,
                    extracted_text=primary.text,
                    summary=display_summary,
                    status=status,
                    created_at=datetime.now(timezone.utc).isoformat(),
                    published_at=published_at,
                    resolved_url=primary.final_url,
                    source_host=primary.source_host,
                    topic_key=dom_key or primary.topic_key,
                    topic_category=primary.topic_category,
                    topic_is_important=any(p.topic_is_important for p in deduped),
                    topic_source_count=topic_src,
                    deepseek_semantic_decision=primary.deepseek_semantic_decision,
                    novelty_passed=any(p.novelty_passed for p in deduped),
                    wechat_draft_pushed_at=wechat_draft_pushed_at,
                    cluster_size=len(deduped),
                    synthesis_multi_source=len(deduped) > 1,
                    event_id=event_id,
                    summary_zh=summary_zh,
                )
                self.store.add(rec)
                self.store.append_event(
                    EventRecord(
                        id=event_id,
                        title=draft_title,
                        summary=summary,
                        summary_zh=summary_zh,
                        dominant_topic_key=dom_key or primary.topic_key,
                        created_at=datetime.now(timezone.utc).isoformat(),
                    )
                )
                self.store.append_event_article_map(
                    [
                        {
                            "event_id": event_id,
                            "source_url": p.hit.url,
                            "resolved_url": p.final_url or "",
                            "role": "primary" if p is primary else "source",
                        }
                        for p in deduped
                    ]
                )
                if publish_to_wechat:
                    stats.published += 1
                else:
                    stats.staged_for_review += 1
            except Exception:
                logger.exception("发布失败: cluster primary=%s", cluster[0].hit.url if cluster else "")
                stats.failed += 1

        await self._run_mandatory_event_enhancement_post_pipeline()
        return stats

    def clean_library_strict(self) -> LibraryCleanStats:
        rows = self.store.list_all()
        stats = LibraryCleanStats(total=len(rows))
        if not rows:
            return stats
        cleaned: list[dict] = []
        for row in rows:
            if not isinstance(row, dict):
                stats.removed += 1
                continue
            title = str(row.get("title", "") or "").strip()
            text = str(row.get("extracted_text", "") or "").strip()
            summary = str(row.get("summary", "") or "").strip()
            source_url = str(row.get("resolved_url", "") or row.get("source_url", "") or "").strip()
            source_published_at = str(row.get("source_published_at", "") or "").strip()
            if not source_published_at:
                stats.removed += 1
                stats.removed_missing_time += 1
                continue
            if not self._published_at_within_window(
                source_published_at=source_published_at,
                max_hours=self.settings.max_article_age_hours,
                date_only_coarse=bool(row.get("source_published_at_date_only")),
            ):
                stats.removed += 1
                stats.removed_time_window += 1
                continue
            if self._blocked_ingest_host(source_url):
                stats.removed += 1
                stats.removed_policy += 1
                continue
            if self._is_low_signal_digest_column(title, text[:800]):
                stats.removed += 1
                stats.removed_digest += 1
                continue
            if self._is_news_brief_or_roundup(title=title, text=text, snippet=summary[:1000]):
                stats.removed += 1
                stats.removed_digest += 1
                continue
            if self._is_too_short(text, min_chars=400):
                stats.removed += 1
                stats.removed_too_short += 1
                continue
            if not self._is_low_altitude_relevant(title=title, text=text, snippet=summary[:300]):
                stats.removed += 1
                stats.removed_low_relevance += 1
                continue
            if self._is_scope_excluded(title=title, text=text, source_url=source_url):
                stats.removed += 1
                stats.removed_scope += 1
                continue
            if self._is_policy_blocked(title=title, text=text, source_url=source_url):
                stats.removed += 1
                stats.removed_policy += 1
                continue
            cleaned.append(row)
            stats.kept += 1
        if stats.removed:
            self.store._write(cleaned)
        return stats

    async def push_today_summaries_to_wechat(
        self, *, local_date: date | None = None
    ) -> TodayDraftPushStats:
        """
        从 ``articles.json`` 选出 ``created_at`` 落在指定本地日（默认：``SCHEDULE_TIMEZONE`` 的当天）
        且已有摘要的记录，调用 ``draft/add`` 写入草稿箱。成功后会写入 ``wechat_draft_pushed_at``，
        避免重复推送。
        """
        if not self.settings.wechat_ready():
            raise ValueError("微信公众号参数未配置完整（WECHAT_MP_APP_ID / WECHAT_MP_APP_SECRET）")

        tz = ZoneInfo(self.settings.schedule_timezone.strip() or "Asia/Shanghai")
        target_day = local_date or datetime.now(tz).date()

        thumb = self.settings.wechat_mp_thumb_media_id.strip()
        if not thumb:
            thumb = await self.wechat.upload_local_cover(self.settings.wechat_mp_thumb_local_path)

        rows = self.store.list_all()
        same_day: list[dict] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            created = self._parse_iso_datetime(str(row.get("created_at") or ""))
            if created is None:
                continue
            if created.astimezone(tz).date() != target_day:
                continue
            same_day.append(row)

        stats = TodayDraftPushStats()
        for row in same_day:
            if row.get("wechat_draft_pushed_at"):
                stats.skipped_already += 1
                continue
            source_published_at = str(row.get("source_published_at") or "").strip()
            if not source_published_at or not self._published_at_within_window(
                source_published_at=source_published_at,
                max_hours=self.settings.max_article_age_hours,
                date_only_coarse=bool(row.get("source_published_at_date_only")),
            ):
                stats.skipped_outdated += 1
                continue
            summary = (row.get("summary") or "").strip()
            source_url = (row.get("source_url") or "").strip()
            title = (row.get("title") or "").strip()
            if not summary or not source_url or not title:
                stats.skipped_empty += 1

        candidates = [
            r
            for r in same_day
            if not r.get("wechat_draft_pushed_at")
            and str(r.get("source_published_at") or "").strip()
            and self._published_at_within_window(
                source_published_at=str(r.get("source_published_at") or "").strip(),
                max_hours=self.settings.max_article_age_hours,
                date_only_coarse=bool(r.get("source_published_at_date_only")),
            )
            and (r.get("summary") or "").strip()
            and (r.get("source_url") or "").strip()
            and (r.get("title") or "").strip()
        ]
        candidates.sort(key=lambda r: str(r.get("created_at") or ""))
        remaining_slots = self._remaining_daily_publish_slots()
        if remaining_slots <= 0:
            logger.info("daily publish cap reached, skip push_today_drafts")
            candidates = []
        else:
            candidates = candidates[: min(self.settings.max_publish_per_run, remaining_slots)]
        stats.eligible = len(candidates)

        for row in candidates:
            aid = str(row.get("id") or "")
            title = (row.get("title") or "").strip()
            summary = (row.get("summary") or "").strip()
            source_url = (row.get("source_url") or "").strip()
            extracted_text = (row.get("extracted_text") or "").strip()
            source_published_at = str(row.get("source_published_at") or "").strip()
            if not self._passes_scope_gate(
                title=title,
                text=f"{extracted_text[:1800]}\n{summary[:1000]}",
                snippet="",
                source_url=str(row.get("resolved_url") or source_url),
            ):
                stats.skipped_qa += 1
                logger.info("push-today-drafts skip by scope gate: id=%s title=%s", aid, title[:40])
                continue
            qa = await self.summarizer.review_summary_for_publish(
                title=title,
                source_url=str(row.get("resolved_url") or source_url),
                source_published_at=source_published_at,
                source_text=extracted_text,
                summary=summary,
                max_article_age_hours=self.settings.max_article_age_hours,
                min_score=self.settings.summary_qa_min_score,
                enabled=self.settings.summary_qa_enabled,
                source_published_at_date_only=bool(row.get("source_published_at_date_only")),
                date_only_max_calendar_age_days=self.settings.date_only_max_calendar_age_days,
                schedule_timezone=self.settings.schedule_timezone,
            )
            if not qa.get("pass", False):
                stats.skipped_qa += 1
                logger.info(
                    "push-today-drafts skip by deepseek qa: id=%s score=%s hard_fails=%s",
                    aid,
                    qa.get("score", 0),
                    qa.get("hard_fail_items", []),
                )
                continue
            thumb_media_id = thumb
            try:
                try:
                    await self.wechat.add_draft(
                        title=title,
                        summary=summary,
                        source_url=source_url,
                        thumb_media_id=thumb_media_id,
                    )
                except RuntimeError as exc:
                    msg = str(exc)
                    if "53402" in msg and thumb_media_id != thumb:
                        logger.warning(
                            "draft add failed by cover crop (53402), retry with default thumb: id=%s",
                            aid,
                        )
                        await self.wechat.add_draft(
                            title=title,
                            summary=summary,
                            source_url=source_url,
                            thumb_media_id=thumb,
                        )
                    else:
                        raise
                pushed_at = datetime.now(timezone.utc).isoformat()
                if aid:
                    self.store.patch_article(aid, {"wechat_draft_pushed_at": pushed_at})
                stats.pushed += 1
                logger.info("push-today-drafts: pushed id=%s title=%s", aid, title[:40])
            except Exception:
                logger.exception("push-today-drafts failed: id=%s url=%s", aid, source_url[:80])
                stats.failed += 1
        return stats

    def _remaining_daily_publish_slots(self) -> int:
        """
        按 ``SCHEDULE_TIMEZONE`` 的本地自然日统计已推送草稿数，确保“每天最多N篇”是日总量而非单次任务上限。
        """
        cap = max(0, int(self.settings.max_publish_per_day))
        if cap <= 0:
            return 0
        tz = ZoneInfo(self.settings.schedule_timezone.strip() or "Asia/Shanghai")
        today = datetime.now(tz).date()
        pushed_today = 0
        for row in self.store.list_all():
            if not isinstance(row, dict):
                continue
            pushed_at = self._parse_iso_datetime(str(row.get("wechat_draft_pushed_at") or ""))
            if pushed_at is None:
                continue
            if pushed_at.astimezone(tz).date() == today:
                pushed_today += 1
        return max(0, cap - pushed_today)

    async def _push_draft(
        self,
        *,
        title: str,
        summary: str,
        source_url: str,
        thumb_media_id: str,
        default_thumb: str,
    ) -> None:
        try:
            await self.wechat.add_draft(
                title=title,
                summary=summary,
                source_url=source_url,
                thumb_media_id=thumb_media_id,
            )
        except RuntimeError as exc:
            msg = str(exc)
            if "53402" in msg and thumb_media_id != default_thumb:
                logger.warning("draft add failed by cover crop (53402), retry with default thumb: %s", source_url)
                await self.wechat.add_draft(
                    title=title,
                    summary=summary,
                    source_url=source_url,
                    thumb_media_id=default_thumb,
                )
            else:
                raise

    @staticmethod
    def _parse_iso_datetime(raw: str) -> datetime | None:
        s = (raw or "").strip()
        if not s:
            return None
        try:
            if s.endswith("Z"):
                s = s[:-1] + "+00:00"
            dt = datetime.fromisoformat(s)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except Exception:
            return None

    @staticmethod
    def _parse_published_raw_to_utc(raw: object) -> tuple[str, bool]:
        """解析单条时间候选为 UTC ISO；第二项为 True 表示仅日历日精度（用日历窗而非小时窗）。"""
        s = str(raw or "").strip()
        if not s:
            return "", False
        sh = ZoneInfo("Asia/Shanghai")
        if re.fullmatch(r"20\d{2}-\d{1,2}-\d{1,2}", s) or re.fullmatch(r"20\d{2}/\d{1,2}/\d{1,2}", s):
            try:
                sep = "-" if "-" in s else "/"
                y, mo, d = (int(x) for x in s.split(sep))
                dt = datetime(y, mo, d, 0, 0, 0, tzinfo=timezone.utc)
                return dt.isoformat(), True
            except Exception:
                pass
        try:
            probe = s.replace("Z", "+00:00")
            dt = datetime.fromisoformat(probe)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            iso = dt.astimezone(timezone.utc).isoformat()
            date_only = bool(re.search(r"T00:00:00(?:\.0+)?(?:\+00:00)?$", probe))
            return iso, date_only
        except Exception:
            pass
        try:
            dt = parsedate_to_datetime(s)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc).isoformat(), False
        except Exception:
            pass
        m_dt = re.search(r"(20\d{2})[-/](\d{1,2})[-/](\d{1,2})\s+(\d{1,2}):(\d{2})(?::(\d{2}))?", s)
        if m_dt:
            try:
                y, mo, d = int(m_dt.group(1)), int(m_dt.group(2)), int(m_dt.group(3))
                hh, mi, ss = int(m_dt.group(4)), int(m_dt.group(5)), int(m_dt.group(6) or 0)
                dt = datetime(y, mo, d, hh, mi, ss, tzinfo=sh)
                return dt.astimezone(timezone.utc).isoformat(), False
            except Exception:
                pass
        mcn = re.search(
            r"(20\d{2})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日(?:\s+(\d{1,2}):(\d{2}))?",
            s,
        )
        if mcn:
            try:
                y, mo, d = int(mcn.group(1)), int(mcn.group(2)), int(mcn.group(3))
                g4, g5 = mcn.group(4), mcn.group(5)
                hh = int(g4) if g4 is not None else 0
                mm = int(g5) if g5 is not None else 0
                dt = datetime(y, mo, d, hh, mm, 0, tzinfo=sh)
                date_only = g4 is None
                return dt.astimezone(timezone.utc).isoformat(), date_only
            except Exception:
                pass
        m_end = re.search(r"(20\d{2})[-/](\d{1,2})[-/](\d{1,2})\s*$", s.strip())
        if m_end and ":" not in s:
            try:
                dt = datetime(
                    year=int(m_end.group(1)),
                    month=int(m_end.group(2)),
                    day=int(m_end.group(3)),
                    tzinfo=timezone.utc,
                )
                return dt.isoformat(), True
            except Exception:
                pass
        m = re.search(r"(20\d{2})[-/](\d{1,2})[-/](\d{1,2})", s)
        if m:
            try:
                dt = datetime(
                    year=int(m.group(1)),
                    month=int(m.group(2)),
                    day=int(m.group(3)),
                    tzinfo=timezone.utc,
                )
                return dt.isoformat(), True
            except Exception:
                pass
        stripped = re.sub(r"^(published|posted|updated|release\s*date)\s*:?\s*", "", s, flags=re.I).strip()
        for probe in (s, stripped):
            probe = probe.strip()
            if not probe:
                continue
            for fmt in ("%A, %B %d, %Y", "%B %d, %Y", "%b %d, %Y", "%d %B %Y", "%d %b %Y"):
                try:
                    dt = datetime.strptime(probe, fmt)
                    dt = dt.replace(tzinfo=timezone.utc)
                    return dt.astimezone(timezone.utc).isoformat(), True
                except ValueError:
                    continue
        en_line = re.search(
            r"\b(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),\s+"
            r"(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+"
            r"\d{1,2},\s*20\d{2}\b",
            s,
            re.I,
        )
        if en_line:
            for fmt in ("%A, %B %d, %Y",):
                try:
                    dt = datetime.strptime(en_line.group(0), fmt)
                    dt = dt.replace(tzinfo=timezone.utc)
                    return dt.astimezone(timezone.utc).isoformat(), True
                except ValueError:
                    break
        en_short = re.search(
            r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+"
            r"\d{1,2},\s*20\d{2}\b",
            s,
            re.I,
        )
        if en_short:
            for fmt in ("%B %d, %Y",):
                try:
                    dt = datetime.strptime(en_short.group(0), fmt)
                    dt = dt.replace(tzinfo=timezone.utc)
                    return dt.astimezone(timezone.utc).isoformat(), True
                except ValueError:
                    break
        return "", False

    @staticmethod
    def _to_utc_iso_datetime(raw: object) -> str:
        return PipelineRunner._parse_published_raw_to_utc(raw)[0]

    _JSON_LD_TIME_KEYS = frozenset(
        {
            "datepublished",
            "datecreated",
            "datemodified",
            "uploaddate",
            "publishedat",
            "publishtime",
            "pubdate",
            "publicationdate",
            "datepublishedtime",
            "articledate",
            "createdat",
            "updatedat",
            "ptime",
        }
    )

    @classmethod
    def _norm_json_key(cls, key: str) -> str:
        return re.sub(r"[^a-z0-9]", "", (key or "").lower())

    @classmethod
    def _collect_datetime_fields(cls, payload: object) -> list[str]:
        out: list[str] = []
        if isinstance(payload, dict):
            if "@graph" in payload:
                out.extend(cls._collect_datetime_fields(payload.get("@graph")))
            for key, value in payload.items():
                if key == "@graph":
                    continue
                if isinstance(key, str):
                    nk = cls._norm_json_key(key)
                    if nk in cls._JSON_LD_TIME_KEYS:
                        if isinstance(value, str) and re.search(r"20\d{2}", value) and len(value) < 160:
                            out.append(value)
                        elif isinstance(value, (int, float)) and 1e9 < float(value) < 1e13:
                            try:
                                ts = float(value)
                                if ts > 1e12:
                                    ts /= 1000.0
                                out.append(datetime.fromtimestamp(ts, tz=timezone.utc).isoformat())
                            except Exception:
                                pass
                out.extend(cls._collect_datetime_fields(value))
        elif isinstance(payload, list):
            for item in payload:
                out.extend(cls._collect_datetime_fields(item))
        return out

    def _selectors_for_host(self, hostname: str) -> list[str]:
        h = (hostname or "").strip().lower()
        if h.startswith("www."):
            h = h[4:]
        if not h:
            return []
        acc: list[str] = []
        seen: set[str] = set()
        for dom, sels in self._published_css_by_host.items():
            if h == dom or h.endswith("." + dom):
                for s in sels:
                    if s not in seen:
                        seen.add(s)
                        acc.append(s)
        return acc

    @staticmethod
    def _script_embedded_time_candidates(soup: BeautifulSoup) -> list[str]:
        out: list[str] = []
        for script in soup.find_all("script"):
            sid = (script.get("id") or "").strip()
            raw = (script.string or script.get_text() or "").strip()
            if not raw:
                continue
            if len(raw) > 2_000_000:
                continue
            if sid == "__NEXT_DATA__":
                try:
                    payload = json.loads(raw)
                    out.extend(PipelineRunner._collect_datetime_fields(payload))
                except Exception:
                    pass
            if len(raw) < 800_000:
                for m in re.finditer(
                    r'"(?:published_at|publishTime|pub_time|ptime|article_publish_time)"\s*:\s*"([^"\\]{8,80})"',
                    raw,
                ):
                    out.append(m.group(1))
                for m in re.finditer(
                    r'"(?:published_at|publishTime|pub_time)"\s*:\s*(\d{10,13})',
                    raw,
                ):
                    try:
                        ts = int(m.group(1))
                        if ts > 1_000_000_000_000:
                            ts //= 1000
                        out.append(datetime.fromtimestamp(ts, tz=timezone.utc).isoformat())
                    except Exception:
                        continue
        return out

    def _extract_published_at(self, soup: BeautifulSoup, *, page_url: str) -> tuple[str, bool]:
        candidates: list[str] = []
        for attr, key in (
            ("property", "article:published_time"),
            ("property", "og:published_time"),
            ("property", "article:modified_time"),
            ("itemprop", "datePublished"),
            ("itemprop", "dateCreated"),
            ("name", "pubdate"),
            ("name", "publishdate"),
            ("name", "date"),
        ):
            node = soup.find("meta", attrs={attr: key})
            if node and node.get("content"):
                candidates.append(str(node.get("content") or "").strip())
        for node in soup.find_all("time"):
            if node.get("datetime"):
                candidates.append(str(node.get("datetime") or "").strip())
        for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
            raw = (script.string or script.get_text() or "").strip()
            if not raw:
                continue
            try:
                payload = json.loads(raw)
            except Exception:
                continue
            candidates.extend(self._collect_datetime_fields(payload))
        candidates.extend(self._script_embedded_time_candidates(soup))
        host = (urlparse(page_url).hostname or "").lower()
        for sel in self._selectors_for_host(host):
            try:
                node = soup.select_one(sel)
            except Exception:
                continue
            if node:
                txt = node.get_text(" ", strip=True)
                if txt and re.search(r"20\d{2}", txt):
                    candidates.append(txt)
        for sel in ("span.item-time", ".article-title-icon span.item-time", "span.title-icon-item.item-time"):
            node = soup.select_one(sel)
            if node:
                txt = node.get_text(" ", strip=True)
                if txt:
                    candidates.append(txt)
        for sel in ("div.time", ".time", ".pages-date", ".pubtime", "span.pub-time"):
            node = soup.select_one(sel)
            if not node:
                continue
            txt = node.get_text(" ", strip=True)
            if txt and re.search(r"20\d{2}", txt):
                candidates.append(txt)
        for node in soup.select("div.node__content > div.mb-4, .node__content > div.mb-4"):
            txt = node.get_text(" ", strip=True)
            if not txt or len(txt) > 120:
                continue
            if re.search(r"20\d{2}", txt):
                candidates.append(txt)
        for raw in candidates:
            iso, coarse = self._parse_published_raw_to_utc(raw)
            if iso:
                return iso, coarse
        region_chunks: list[str] = []
        for sel in ("main", "article", "[role='main']", ".node__content", "header", ".article-detail", ".article-content"):
            node = soup.select_one(sel)
            if node:
                region_chunks.append(node.get_text(" ", strip=True)[:16000])
        scoped = " ".join(region_chunks)[:48000]
        texts = [scoped] if scoped.strip() else []
        if not texts:
            texts = [soup.get_text(" ", strip=True)]
        for text in texts:
            if not text:
                continue
            for pat in (
                r"\b(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),\s+"
                r"(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+"
                r"\d{1,2},\s*20\d{2}\b",
                r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+"
                r"\d{1,2},\s*20\d{2}\b",
                r"(20\d{2}[-/年\.]\d{1,2}[-/月\.]\d{1,2}(?:日)?(?:\s+\d{1,2}:\d{2}(?::\d{2})?)?)",
                r"(20\d{2}\.\d{1,2}\.\d{1,2}\s+\d{1,2}:\d{2})",
            ):
                m = re.search(pat, text, re.I)
                if not m:
                    continue
                iso, coarse = self._parse_published_raw_to_utc(m.group(0))
                if iso:
                    return iso, coarse
        return "", False

    @staticmethod
    def _resolve_source_published_at(
        *, page_published_at: str, page_date_only_coarse: bool
    ) -> tuple[str, bool]:
        s = (page_published_at or "").strip()
        if not s:
            return "", False
        iso = PipelineRunner._to_utc_iso_datetime(s)
        if not iso:
            return "", False
        return iso, bool(page_date_only_coarse)

    def _published_at_within_window(
        self,
        *,
        source_published_at: str,
        max_hours: int,
        date_only_coarse: bool = False,
    ) -> bool:
        normalized = self._to_utc_iso_datetime(source_published_at)
        if not normalized:
            return False
        if max_hours <= 0:
            return True
        dt = self._parse_iso_datetime(normalized)
        if dt is None:
            return False
        if date_only_coarse:
            tz = ZoneInfo((self.settings.schedule_timezone or "Asia/Shanghai").strip() or "Asia/Shanghai")
            today = datetime.now(timezone.utc).astimezone(tz).date()
            art_day = dt.astimezone(tz).date()
            oldest = today - timedelta(days=max(1, int(self.settings.date_only_max_calendar_age_days)))
            if art_day < oldest or art_day > today + timedelta(days=1):
                return False
            return True
        cutoff = datetime.now(timezone.utc) - timedelta(hours=max_hours)
        return dt >= cutoff

    @staticmethod
    def _is_opinion_or_non_news(*, title: str, text: str) -> bool:
        blob = f"{title}\n{text[:1200]}".lower()
        blockers = (
            "导刊",
            "评论",
            "观点",
            "专栏",
            "圆桌",
            "深度解读",
            "社论",
            "编者按",
            "合集",
            "报告合集",
            "研报合集",
            "一文读懂",
            "强农考工谈",
        )
        whitelist = (
            "管理规定",
            "实施",
            "通告",
            "公告",
            "发布会",
            "国务院",
            "民航局",
            "发改委",
        )
        if any(w in blob for w in whitelist):
            return False
        return any(k in blob for k in blockers)

    @staticmethod
    def _is_scope_excluded(*, title: str, text: str, source_url: str) -> bool:
        blob = f"{title}\n{text[:3200]}".lower()
        host = (urlparse(source_url).hostname or "").lower()
        hard_block_hosts = (
            "apps.apple.com",
            "apps.microsoft.com",
            "xbox.com",
            "roblox.com",
            "now.gg",
            "baike.",
            "zhihu.com",
        )
        if any(h in host for h in hard_block_hosts):
            return True
        excluded_keywords = (
            "电视剧",
            "开播",
            "剧情",
            "演员",
            "优酷",
            "综艺",
            "电影",
            "roblox",
            "游戏下载",
            "app store",
            "百科",
            "词条",
            "深度科普",
            "科普",
            "科普教育",
            "入门指南",
            "选购指南",
            "关于我们",
            "企业简介",
            "产品中心",
            "联系我们",
            "版权所有",
            "copyright",
            "招商",
            "课程培训",
            "飞手培训",
        )
        if any(k in blob for k in excluded_keywords):
            return True
        company_tokens = ("有限公司", "股份有限公司", "集团", "公司简介")
        if any(k in title for k in company_tokens):
            news_tokens = ("政策", "监管", "发布", "通告", "公告", "规划", "战略", "试点", "民航局", "国务院")
            if not any(k in blob for k in news_tokens):
                return True
        shell_hits = sum(
            1
            for k in ("关于我们", "产品中心", "服务支持", "联系我们", "版权", "copyright", "招聘")
            if k in blob
        )
        if shell_hits >= 3:
            return True
        return False

    @classmethod
    def _passes_scope_gate(cls, *, title: str, text: str, snippet: str, source_url: str) -> bool:
        if cls._is_news_brief_or_roundup(title=title, text=text, snippet=snippet):
            logger.info("skip quick-news/roundup page: %s", source_url)
            return False
        if not cls._is_low_altitude_relevant(title=title, text=text, snippet=snippet):
            logger.info("skip low-relevance non low-altitude page: %s", source_url)
            return False
        if not cls._is_low_altitude_primary_focus(title=title, text=text, snippet=snippet):
            logger.info("skip non-primary low-altitude mixed-topic page: %s", source_url)
            return False
        if cls._is_scope_excluded(title=title, text=text, source_url=source_url):
            logger.info("skip scope-excluded page: %s", source_url)
            return False
        if cls._is_opinion_or_non_news(title=title, text=text):
            logger.info("skip opinion/non-news article: %s", source_url)
            return False
        return True

    @classmethod
    def _is_low_altitude_primary_focus(cls, *, title: str, text: str, snippet: str) -> bool:
        """
        避免“多领域新规合集”仅夹带一段无人机信息时被误判为目标领域稿件。
        """
        blob = f"{title}\n{snippet}\n{text[:2200]}"
        blob_l = blob.lower()

        low_count = 0
        for k in _LOW_ALTITUDE_RELEVANCE_CJK_KEYWORDS:
            low_count += blob.count(k)
        for k in _LOW_ALTITUDE_RELEVANCE_LATIN_KEYWORDS:
            low_count += len(re.findall(rf"\b{re.escape(k)}\b", blob_l))

        cross_domain_terms = (
            "食品安全",
            "药品",
            "殡葬",
            "渔业",
            "基金",
            "烟花爆竹",
            "通信短信息",
            "商事调解",
            "特种设备",
            "反腐",
            "鞋长",
            "咖啡机",
        )
        cross_count = sum(1 for t in cross_domain_terms if t in blob)
        if cross_count >= 4 and low_count <= 4:
            return False
        if re.search(r"涉及[^。]{0,30}多个领域", blob) and low_count <= 5:
            return False
        # 多领域术语远多于低空术语时，视为“夹带一段无人机信息”的汇总稿
        if cross_count >= 3 and low_count <= cross_count + 1:
            return False
        if blob.count("5月1日起") >= 3 and cross_count >= 3 and low_count <= cross_count + 1:
            return False
        return True

    @classmethod
    def _is_news_brief_or_roundup(cls, *, title: str, text: str, snippet: str) -> bool:
        """
        拦截新闻快讯和多领域“新规合集”稿，避免仅含一小段低空信息被放入主链路。
        """
        t = (title or "").strip()
        blob = f"{t}\n{snippet}\n{text[:2600]}"
        blob_l = blob.lower()
        for rx in _NEWS_ROUNDUP_TITLE_RES:
            if rx.search(t):
                return True
        # 常见“新规合集”文本特征
        if "一批涉及" in blob and "多个领域" in blob:
            return True
        if "新规" in t and ("施行" in t or "落地" in t) and ("、" in t or "：" in t):
            return True
        low_count = 0
        for k in _LOW_ALTITUDE_RELEVANCE_CJK_KEYWORDS:
            low_count += blob.count(k)
        for k in _LOW_ALTITUDE_RELEVANCE_LATIN_KEYWORDS:
            low_count += len(re.findall(rf"\b{re.escape(k)}\b", blob_l))
        cross_terms = (
            "反腐",
            "金融",
            "食品安全",
            "药品",
            "殡葬",
            "渔业",
            "基金",
            "烟花爆竹",
            "通信短信息",
            "商事调解",
            "特种设备",
            "经营主体登记",
        )
        cross_count = sum(1 for x in cross_terms if x in blob)
        if cross_count >= 4 and low_count <= cross_count + 1:
            return True
        return False

    @staticmethod
    def _host_matches_target_sites(*, url: str, target_sites: list[str]) -> bool:
        host = (urlparse(url).hostname or "").lower()
        if host.startswith("www."):
            host = host[4:]
        if not host:
            return False
        for site in target_sites:
            s = (site or "").strip().lower()
            if not s:
                continue
            if host == s or host.endswith("." + s):
                return True
        return False

    async def _fetch_text(
        self, url: str, fallback_title: str, fallback_snippet: str
    ) -> tuple[str, str, str | None, str, str, bool]:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            resp = await client.get(url, headers={"User-Agent": "Mozilla/5.0"})
            resp.raise_for_status()
        html_text = self._decode_html(resp)
        soup = BeautifulSoup(html_text, "html.parser")
        title = (soup.title.text.strip() if soup.title and soup.title.text else fallback_title).strip() or "来源文章"
        if title.lower() == "google news" and fallback_title.strip():
            title = fallback_title.strip()
        if self._looks_garbled_text(title) and fallback_title.strip():
            title = fallback_title.strip()
        title = normalize_title(title)
        final_url = str(resp.url)
        page_published_at, page_date_only = self._extract_published_at(soup, page_url=final_url)
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()

        def _legacy_paragraph_text() -> str:
            parts: list[str] = []
            for p in soup.find_all(["p", "li", "h2", "h3"]):
                txt = (p.get_text(" ", strip=True) or "").strip()
                if len(txt) >= 25:
                    parts.append(txt)
            return "\n".join(parts)[:20000].strip() or fallback_snippet

        text = main_text_with_trafilatura_fallback(
            html_text,
            page_url=final_url,
            min_chars=int(self.settings.trafilatura_min_chars),
            trafilatura_enabled=bool(self.settings.trafilatura_enabled),
            fallback=_legacy_paragraph_text,
        )
        if self._looks_garbled_text(text) and fallback_snippet.strip():
            text = fallback_snippet.strip()
        first_image_url = self._extract_first_image_url(soup, base_url=final_url)
        return title, text, first_image_url, final_url, page_published_at, page_date_only

    @staticmethod
    def _decode_html(resp: httpx.Response) -> str:
        return decode_http_html_bytes(
            resp.content or b"",
            content_type=str(resp.headers.get("content-type") or ""),
            httpx_encoding=str(resp.encoding or ""),
        )

    @staticmethod
    def _extract_first_image_url(soup: BeautifulSoup, base_url: str) -> str | None:
        article_scoped = soup.select(
            "article img, main img, [class*='content'] img, [class*='article'] img, [id*='content'] img, [id*='article'] img"
        )
        for img in article_scoped:
            candidate = PipelineRunner._normalize_img_src(str(img.get("src") or ""), base_url)
            if candidate and PipelineRunner._is_likely_content_image(img, candidate):
                return candidate

        og = soup.find("meta", attrs={"property": "og:image"})
        if og and og.get("content"):
            candidate = PipelineRunner._normalize_img_src(str(og.get("content") or ""), base_url)
            if candidate and PipelineRunner._is_likely_cover_url(candidate):
                return candidate
        tw = soup.find("meta", attrs={"name": "twitter:image"})
        if tw and tw.get("content"):
            candidate = PipelineRunner._normalize_img_src(str(tw.get("content") or ""), base_url)
            if candidate and PipelineRunner._is_likely_cover_url(candidate):
                return candidate

        for img in soup.find_all("img"):
            candidate = PipelineRunner._normalize_img_src(str(img.get("src") or ""), base_url)
            if candidate and PipelineRunner._is_likely_content_image(img, candidate):
                return candidate
        return None

    @staticmethod
    def _normalize_img_src(src: str, base_url: str) -> str:
        raw = (src or "").strip()
        if not raw or raw.startswith("data:"):
            return ""
        return urljoin(base_url, raw)

    @staticmethod
    def _is_likely_cover_url(image_url: str) -> bool:
        lowered = image_url.lower()
        bad_tokens = ("logo", "icon", "avatar", "sprite", "favicon")
        return not any(token in lowered for token in bad_tokens)

    @staticmethod
    def _is_likely_content_image(img_tag: BeautifulSoup, image_url: str) -> bool:
        if not PipelineRunner._is_likely_cover_url(image_url):
            return False
        width = PipelineRunner._to_int(img_tag.get("width"))
        height = PipelineRunner._to_int(img_tag.get("height"))
        # Skip tiny/static assets when dimensions are explicitly available.
        if width and width < 200:
            return False
        if height and height < 120:
            return False
        classes = " ".join(img_tag.get("class") or []).lower()
        alt = str(img_tag.get("alt") or "").lower()
        src_l = image_url.lower()
        if re.search(r"(logo|icon|avatar|qrcode|二维码)", f"{classes} {alt} {src_l}"):
            return False
        return True

    @staticmethod
    def _to_int(raw: object) -> int:
        if raw is None:
            return 0
        m = re.search(r"\d+", str(raw))
        return int(m.group(0)) if m else 0

    @staticmethod
    def _looks_garbled_text(text: str) -> bool:
        if not text:
            return False
        bad = len(re.findall(r"[�Ãâ¤ï¿½]", text))
        return bad >= 3

    @staticmethod
    def _is_low_signal_digest_column(title: str, snippet: str) -> bool:
        """过滤科技早报、多段合集标题等低信号快餐稿。"""
        t = (title or "").strip()
        s = (snippet or "").strip()
        bundle = f"{t}\n{s[:400]}"
        for rx in _DIGEST_TITLE_RES:
            if rx.search(t) or rx.search(bundle):
                return True
        if "早报" in t and ("；" in t or ";" in t) and len(t) < 120:
            return True
        return False

    @staticmethod
    def _is_low_altitude_relevant(*, title: str, text: str, snippet: str) -> bool:
        blob = f"{title}\n{snippet}\n{text[:3000]}"
        blob_l = blob.lower()
        if any(k in blob for k in _LOW_ALTITUDE_RELEVANCE_CJK_KEYWORDS):
            return True
        return any(re.search(rf"\b{re.escape(k)}\b", blob_l) for k in _LOW_ALTITUDE_RELEVANCE_LATIN_KEYWORDS)

    @staticmethod
    def _blocked_ingest_host(url: str) -> bool:
        """与 ``search.SEARCH_SOURCE_BLOCKLIST`` 对齐：抓取后二次拦截（书签/跳转落地）。"""
        try:
            host = (urlparse(url).hostname or "").lower()
        except Exception:
            host = ""
        return any(s in host for s in ("rfi.fr", "radiofrance.fr"))

    @staticmethod
    def _is_probable_charset_garbage(*, title: str, text: str) -> bool:
        """
        抓取结果疑似编码错乱或导航壳层（如 UTF-8 误读 Big5、整页语言菜单混入正文）。
        与政策无关，仅避免进入摘要与草稿箱。
        """
        t = title or ""
        head = f"{t}\n{(text or '')[:2000]}"
        if PipelineRunner._looks_garbled_text(t):
            return True
        if "\ufffd" in t:
            return True
        if len(t) >= 6 and len(re.findall(r"[銝鈭箸瘜蝳撠銵銋剖啣撅踹餃]", t)) >= 2:
            return True
        hl = head.lower()
        if "rfi" in hl and re.search(r"(?i)fran.{0,4}ais|espa.{0,4}ol", head):
            if not re.search(r"[a-zA-Z]{4,}", t):
                return True
        return False

    @staticmethod
    def _canonical_url(url: str) -> str:
        raw = (url or "").strip()
        if not raw:
            return ""
        try:
            p = urlparse(raw)
            host = (p.netloc or "").lower()
            path = (p.path or "").rstrip("/")
            if host.endswith("news.google.com") and path.startswith("/rss/articles/"):
                # Remove transient params (hl/gl/ceid/etc), keep article identity by path.
                return urlunparse((p.scheme.lower() or "https", host, path, "", "", ""))
            qs = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=False) if not k.lower().startswith("utm_")]
            query = urlencode(sorted(qs))
            return urlunparse((p.scheme.lower() or "https", host, path, "", query, "")).rstrip("/")
        except Exception:
            return raw.lower().rstrip("/")

    @staticmethod
    def _is_too_short(text: str, min_chars: int = 100) -> bool:
        plain = re.sub(r"\s+", "", text or "")
        return len(plain) < min_chars

    @staticmethod
    def _is_policy_blocked(*, title: str, text: str, source_url: str) -> bool:
        content = f"{title}\n{text}".lower()
        host = (urlparse(source_url).hostname or "").lower()

        # Source-level strictness: Taiwan-local news domains are treated as higher risk.
        taiwan_domain_hints = (
            ".tw",
            "udn.com",
            "ltn.com.tw",
            "setn.com",
            "ettoday.net",
            "storm.mg",
            "newtalk.tw",
            "cts.com.tw",
            "tvbs.com.tw",
            "epochtimes.com",
            "epochtimes.com.tw",
        )
        if any(h in host for h in taiwan_domain_hints):
            return True

        smear_markers = (
            "抹黑大陆",
            "唱衰中国",
            "中国崩溃",
            "大陆崩溃",
            "看衰中国",
            "中国威胁论",
            "中国渗透",
            "中共渗透",
            "大陆打压",
            "妖魔化中国",
        )
        separatist_markers = (
            "台独",
            "两国论",
            "一边一国",
            "台湾国",
            "去中国化",
            "中国入侵台湾",
            "大陆入侵台湾",
        )
        if any(k in content for k in smear_markers):
            return True
        if any(k in content for k in separatist_markers):
            return True

        # Combination rule: anti-mainland negative framing around China/Mainland.
        mainland_refs = ("中国大陆", "大陆", "中国", "内地")
        negative_refs = ("专制", "独裁", "打压", "迫害", "扩张", "威胁", "渗透", "封锁", "侵略")
        has_mainland_ref = any(k in content for k in mainland_refs)
        has_negative_ref = any(k in content for k in negative_refs)
        return has_mainland_ref and has_negative_ref
