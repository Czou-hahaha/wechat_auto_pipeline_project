from __future__ import annotations

import json
import logging
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

_KEYWORD_CATEGORY_ORDER = (
    "national_policy",
    "local_policy",
    "intl_coopcomp",
    "frontier_tech",
)
_SITE_KEYWORD_KEYS = (
    "site_core_keywords",
    "professional_site_keywords",
)
# 与分类键并列：中英检索词表（供全域 + 站点阶段合并使用）
_EXTRA_QUERY_KEYS = (
    "english_keywords",
    "chinese_keywords",
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    deepseek_api_key: str = Field(default="", alias="DEEPSEEK_API_KEY")
    deepseek_base_url: str = Field(default="https://api.deepseek.com", alias="DEEPSEEK_BASE_URL")
    deepseek_model: str = Field(default="deepseek-chat", alias="DEEPSEEK_MODEL")

    wechat_mp_app_id: str = Field(default="", alias="WECHAT_MP_APP_ID")
    wechat_mp_app_secret: str = Field(default="", alias="WECHAT_MP_APP_SECRET")
    wechat_mp_author: str = Field(default="小编", alias="WECHAT_MP_AUTHOR")
    wechat_mp_thumb_media_id: str = Field(default="", alias="WECHAT_MP_THUMB_MEDIA_ID")
    wechat_mp_thumb_local_path: str = Field(default="", alias="WECHAT_MP_THUMB_LOCAL_PATH")

    schedule_enabled: bool = Field(default=False, alias="SCHEDULE_ENABLED")
    schedule_timezone: str = Field(default="Asia/Shanghai", alias="SCHEDULE_TIMEZONE")
    schedule_morning_hour: int = Field(default=8, ge=0, le=23, alias="SCHEDULE_MORNING_HOUR")
    schedule_evening_hour: int = Field(default=20, ge=0, le=23, alias="SCHEDULE_EVENING_HOUR")

    search_queries: str = Field(default="低空经济,无人机,eVTOL", alias="SEARCH_QUERIES")
    # 相对运行目录（一般为 V1/）或绝对路径；存在且为合法 JSON 时优先于 SEARCH_QUERIES
    search_keywords_path: str = Field(default="config/search_keywords.json", alias="SEARCH_KEYWORDS_PATH")
    # 目标站点（逗号分隔域名），搜索时优先按 site:domain 检索，再做全域检索
    search_target_sites: str = Field(default="", alias="SEARCH_TARGET_SITES")
    # 读取 V1 内置的高质量站点清单（config/data_sources.json）
    search_load_his_data_sources: bool = Field(default=True, alias="SEARCH_LOAD_HIS_DATA_SOURCES")
    his_data_sources_path: str = Field(default="config/data_sources.json", alias="HIS_DATA_SOURCES_PATH")
    # 兼容根目录旧字段
    schedule_search_site_domain: str = Field(default="", alias="SCHEDULE_SEARCH_SITE_DOMAIN")
    search_max_results: int = Field(default=20, ge=1, le=100, alias="SEARCH_MAX_RESULTS")
    max_article_age_hours: int = Field(default=14, ge=0, le=8760, alias="MAX_ARTICLE_AGE_HOURS")
    # 仅解析到「日历日」无可靠时刻时：按上海日历日与「今天」相差不超过该天数则视为在窗内；仍依赖 URL/标题历史去重
    date_only_max_calendar_age_days: int = Field(default=3, ge=1, le=14, alias="DATE_ONLY_MAX_CALENDAR_AGE_DAYS")
    max_publish_per_run: int = Field(default=21, ge=1, le=100, alias="MAX_PUBLISH_PER_RUN")
    max_publish_per_day: int = Field(default=10, ge=1, le=200, alias="MAX_PUBLISH_PER_DAY")
    # 摘要/推送：按 importance 取前 N 个事件；不足 N 则有几个处理几个
    wechat_publish_top_n: int = Field(default=3, ge=1, le=10, alias="WECHAT_PUBLISH_TOP_N")
    # 同一 topic/标题指纹在冷却期内已推过公众号则跳过
    wechat_publish_cooldown_days: int = Field(default=3, ge=0, le=30, alias="WECHAT_PUBLISH_COOLDOWN_DAYS")
    # 主题聚类：同窗内政策相关稿（如禁飞/禁售）软合并的最大时间跨度（小时）
    cluster_merge_hours: int = Field(default=72, ge=1, le=168, alias="CLUSTER_MERGE_HOURS")
    # false: run-once 仅入库待抽检，不自动推送公众号；true: 自动推送
    run_once_push_to_wechat: bool = Field(default=False, alias="RUN_ONCE_PUSH_TO_WECHAT")
    # true: 规则门禁后再走 DeepSeek 自动复核；不通过直接拦截发布
    summary_qa_enabled: bool = Field(default=True, alias="SUMMARY_QA_ENABLED")
    # DeepSeek 复核最低分（0-100），低于阈值视为不通过
    summary_qa_min_score: int = Field(default=80, ge=0, le=100, alias="SUMMARY_QA_MIN_SCORE")
    news_search_fallback: str = Field(default="off", alias="NEWS_SEARCH_FALLBACK")

    rss_aggregate_enabled: bool = Field(default=True, alias="RSS_AGGREGATE_ENABLED")
    rss_per_feed_max: int = Field(default=30, ge=1, le=200, alias="RSS_PER_FEED_MAX")
    rss_total_max: int = Field(default=500, ge=10, le=5000, alias="RSS_TOTAL_MAX")
    rss_timeout_sec: float = Field(default=25.0, ge=5.0, le=120.0, alias="RSS_TIMEOUT_SEC")
    html_list_timeout_sec: float = Field(default=20.0, ge=5.0, le=120.0, alias="HTML_LIST_TIMEOUT_SEC")

    # 抓正文前：标题+摘要轻量过滤（GDELT 误召回）
    search_prefilter_enabled: bool = Field(default=True, alias="SEARCH_PREFILTER_ENABLED")
    # 簇摘要+QA 并行度（DeepSeek 限速下 2–3；推送微信时建议 1）
    deepseek_cluster_concurrency: int = Field(default=3, ge=1, le=8, alias="DEEPSEEK_CLUSTER_CONCURRENCY")
    cluster_summary_min_chars: int = Field(default=800, ge=800, le=2000, alias="CLUSTER_SUMMARY_MIN_CHARS")
    cluster_summary_max_chars: int = Field(default=1500, ge=800, le=2500, alias="CLUSTER_SUMMARY_MAX_CHARS")
    # 簇摘要 prompt 最多几篇素材；每篇摘录上限（须给摘录，不能只给链接）
    cluster_summary_max_sources: int = Field(default=5, ge=1, le=10, alias="CLUSTER_SUMMARY_MAX_SOURCES")
    cluster_summary_excerpt_chars: int = Field(
        default=1500, ge=400, le=4000, alias="CLUSTER_SUMMARY_EXCERPT_CHARS"
    )
    # true：仅抓 data_sources 里中文 html_list（见 ingest_zh_html_source_ids）
    ingest_zh_html_only: bool = Field(default=False, alias="INGEST_ZH_HTML_ONLY")
    # 逗号分隔 source id；空且 INGEST_ZH_HTML_ONLY=true 时取全部中文 html_list
    ingest_zh_html_source_ids: str = Field(default="", alias="INGEST_ZH_HTML_SOURCE_IDS")
    # 逗号分隔 URL：本轮强制纳入候选（如 FCC 稿），仍走正文抓取与后续流程
    ingest_pin_urls: str = Field(default="", alias="INGEST_PIN_URLS")

    gdelt_base_url: str = Field(
        default="https://api.gdeltproject.org/api/v2/doc/doc",
        alias="GDELT_BASE_URL",
    )
    gdelt_timeout_sec: float = Field(default=45.0, ge=10.0, le=180.0, alias="GDELT_TIMEOUT_SEC")
    # 第 2、3 次重试的单次 HTTP 超时（避免 ConnectTimeout 卡满 45s 像死机）
    gdelt_retry_timeout_sec: float = Field(default=15.0, ge=5.0, le=60.0, alias="GDELT_RETRY_TIMEOUT_SEC")
    gdelt_max_records: int = Field(default=50, ge=1, le=75, alias="GDELT_MAX_RECORDS")
    # GDELT DOC timespan（推荐 1h；勿用 7d/30d，年龄过滤在本地 filter_by_age）
    gdelt_timespan: str = Field(default="1h", alias="GDELT_TIMESPAN")
    gdelt_max_retries: int = Field(default=3, ge=1, le=5, alias="GDELT_MAX_RETRIES")
    gdelt_cache_ttl_min: int = Field(default=30, ge=1, le=240, alias="GDELT_CACHE_TTL_MIN")
    # 主题级 GDELT：一词一请求、串行；全进程共享间隔（实际 max(5, 配置值) 秒）
    gdelt_max_concurrent: int = Field(default=1, ge=1, le=1, alias="GDELT_MAX_CONCURRENT")
    gdelt_min_interval_sec: float = Field(default=5.0, ge=5.0, le=60.0, alias="GDELT_MIN_INTERVAL_SEC")
    gdelt_or_max_terms_per_query: int = Field(default=14, ge=3, le=25, alias="GDELT_OR_MAX_TERMS_PER_QUERY")
    # false=主链路 GDELT 仅搜 english_keywords（推荐）；true=追加 chinese_keywords
    gdelt_chinese_enabled: bool = Field(default=False, alias="GDELT_CHINESE_ENABLED")
    # 检索阶段：RSS/HTML 缺 published_at 时抓落地页补全（与 tests/integration/run_search_flow 一致）
    search_article_page_backfill: bool = Field(default=True, alias="SEARCH_ARTICLE_PAGE_BACKFILL")
    search_article_page_backfill_max_concurrent: int = Field(
        default=4, ge=1, le=16, alias="SEARCH_ARTICLE_PAGE_BACKFILL_MAX_CONCURRENT"
    )
    search_article_page_fetch_timeout_sec: float = Field(
        default=35.0, ge=10.0, le=120.0, alias="SEARCH_ARTICLE_PAGE_FETCH_TIMEOUT_SEC"
    )
    # true=恢复旧版 (query) domain:site 扇出（不推荐）
    gdelt_site_scoped_enabled: bool = Field(default=False, alias="GDELT_SITE_SCOPED_ENABLED")

    rss_relevance_filter_enabled: bool = Field(default=True, alias="RSS_RELEVANCE_FILTER_ENABLED")
    # true：摘要成功写入公众号草稿箱后，清空 articles.json 中对应条目的 extracted_text（仅保留 summary）
    strip_extracted_text_after_wechat_draft: bool = Field(
        default=True, alias="STRIP_EXTRACTED_TEXT_AFTER_WECHAT_DRAFT"
    )

    # 可选：全文向量去重。embedding_backend=local 时用本机 sentence-transformers（免 KEY）；http 时用 OpenAI 兼容 /v1/embeddings
    embedding_enabled: bool = Field(default=False, alias="EMBEDDING_ENABLED")
    # local = 本机 BAAI/bge-m3 等；http = 需 EMBEDDING_API_KEY 的远程服务
    embedding_backend: str = Field(default="local", alias="EMBEDDING_BACKEND")
    embedding_api_key: str = Field(default="", alias="EMBEDDING_API_KEY")
    embedding_base_url: str = Field(default="https://api.openai.com/v1", alias="EMBEDDING_BASE_URL")
    embedding_model: str = Field(default="BAAI/bge-m3", alias="EMBEDDING_MODEL")
    embedding_dedupe_threshold: float = Field(default=0.92, ge=0.5, le=0.999, alias="EMBEDDING_DEDUPE_THRESHOLD")
    embedding_max_input_chars: int = Field(default=8000, ge=500, le=32000, alias="EMBEDDING_MAX_INPUT_CHARS")
    embedding_batch_size: int = Field(default=16, ge=1, le=64, alias="EMBEDDING_BATCH_SIZE")
    # true：用向量 + 双阈值做批内「转载合并 + 同事件聚类」，替代 _global_dedupe_prepared + topic_key 聚类（需 EMBEDDING_* 可用）
    embedding_cluster_enabled: bool = Field(default=False, alias="EMBEDDING_CLUSTER_ENABLED")
    # 转载合并：余弦 ≥ 该值视为同一正文（只保留一条 canonical）
    embedding_reprint_threshold: float = Field(default=0.9, ge=0.5, le=0.999, alias="EMBEDDING_REPRINT_THRESHOLD")
    # 同事件边：余弦 ∈ [min, reprint) 时连边（并查集传递）
    embedding_event_link_min: float = Field(default=0.75, ge=0.5, le=0.999, alias="EMBEDDING_EVENT_LINK_MIN")

    # 落地页 HTML 正文：优先 trafilatura，失败或过短回退原 BeautifulSoup 段落拼接
    trafilatura_enabled: bool = Field(default=True, alias="TRAFILATURA_ENABLED")
    trafilatura_min_chars: int = Field(default=200, ge=50, le=2000, alias="TRAFILATURA_MIN_CHARS")

    # 事件摘要为英文主导时，仅译标题+摘要为中文（article 仍存原文）
    event_translate_summary_enabled: bool = Field(default=True, alias="EVENT_TRANSLATE_SUMMARY_ENABLED")

    # ----- 阶段三：事件增强（run_once 必选；JSON ↔ PostgreSQL ↔ GDELT 扩搜） -----
    # 未配置时 ``run_once`` 会在阶段三抛出明确错误（须先 ``alembic upgrade head``）
    event_enhancement_database_url: str = Field(default="", alias="EVENT_ENHANCEMENT_DATABASE_URL")
    event_enhancement_config_path: str = Field(default="", alias="EVENT_ENHANCEMENT_CONFIG_PATH")

    # ----- 阶段四：事件级中文通稿（DeepSeek；可选，在阶段三之后） -----
    event_ai_press_enabled: bool = Field(default=False, alias="EVENT_AI_PRESS_ENABLED")
    # 至少 N 篇关联 article 才生成（融合多源；1 则单篇也允许）
    event_ai_press_min_articles: int = Field(default=2, ge=1, le=30, alias="EVENT_AI_PRESS_MIN_ARTICLES")
    event_ai_press_skip_if_exists: bool = Field(default=True, alias="EVENT_AI_PRESS_SKIP_IF_EXISTS")
    # 选文模式：top_k_dedupe=默认（top_k+转载去重）；all_by_tier=同事件尽量多篇按来源排序进 prompt，仅去重同 URL
    event_ai_press_selection_mode: str = Field(default="all_by_tier", alias="EVENT_AI_PRESS_SELECTION_MODE")
    event_ai_press_max_articles_in_prompt: int = Field(
        default=20, ge=1, le=60, alias="EVENT_AI_PRESS_MAX_ARTICLES_IN_PROMPT"
    )
    # 0 = 每篇不截断，全文进 prompt；>0 为单篇最大字符数
    event_ai_press_per_article_max_chars: int = Field(
        default=0, ge=0, le=400_000, alias="EVENT_AI_PRESS_PER_ARTICLE_MAX_CHARS"
    )
    # 0 = 不截断整段 user；>0 为 user prompt 最大字符硬帽
    event_ai_press_max_user_chars: int = Field(default=0, ge=0, le=2_000_000, alias="EVENT_AI_PRESS_MAX_USER_CHARS")
    # 0 = 关闭自动按估 token 缩短单篇；>0 且 PER_ARTICLE>0 时超预算才逐步缩短
    event_ai_press_soft_token_budget: int = Field(
        default=0, ge=0, le=500_000, alias="EVENT_AI_PRESS_SOFT_TOKEN_BUDGET"
    )
    event_ai_press_timeout_sec: float = Field(default=180.0, ge=30.0, le=600.0, alias="EVENT_AI_PRESS_TIMEOUT_SEC")

    # ----- 阶段五：通稿质量控制 + 条件重写（阶段四生成后自动执行；DeepSeek） -----
    # false：仅写阶段四初稿，不跑 QA/重写
    qa_rewrite_enabled: bool = Field(default=True, alias="QA_REWRITE_ENABLED")
    # 达标线：score>=阈值且 hallucination=false 视为通过，不再重写
    qa_rewrite_pass_threshold: int = Field(default=80, ge=0, le=100, alias="QA_REWRITE_PASS_THRESHOLD")
    # 未达标时最多重写几次（每次重写后会再跑一轮 QA）
    qa_rewrite_max_rounds: int = Field(default=2, ge=0, le=8, alias="QA_REWRITE_MAX_ROUNDS")
    qa_rewrite_qa_timeout_sec: float = Field(default=120.0, ge=15.0, le=600.0, alias="QA_REWRITE_QA_TIMEOUT_SEC")
    qa_rewrite_rewrite_timeout_sec: float = Field(default=180.0, ge=30.0, le=600.0, alias="QA_REWRITE_REWRITE_TIMEOUT_SEC")
    # 原始 event articles 打包进 prompt 的最大字符数（>0；粗估 token 控制）
    qa_rewrite_max_event_chars: int = Field(default=120_000, ge=2_000, le=2_000_000, alias="QA_REWRITE_MAX_EVENT_CHARS")
    qa_rewrite_max_retries: int = Field(default=3, ge=1, le=10, alias="QA_REWRITE_MAX_RETRIES")
    qa_rewrite_retry_backoff_sec: float = Field(default=1.6, ge=0.2, le=30.0, alias="QA_REWRITE_RETRY_BACKOFF_SEC")

    data_dir: str = Field(default="./data", alias="DATA_DIR")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    def _search_keywords_file(self) -> Path:
        raw = (self.search_keywords_path or "").strip()
        if raw:
            p = Path(raw).expanduser()
            if not p.is_absolute():
                p = Path.cwd() / p
            return p
        return Path(__file__).resolve().parent.parent / "config" / "search_keywords.json"

    def parsed_queries(self) -> list[str]:
        """优先读取 ``config/search_keywords.json``（分类词 + english/chinese_keywords）；缺失时回退 ``SEARCH_QUERIES``。"""
        return self.parsed_global_queries()

    def _load_keywords_json(self) -> dict[str, object]:
        path = self._search_keywords_file()
        if path.is_file():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    return data
            except Exception:
                logger.warning("failed to load %s, fallback to SEARCH_QUERIES", path, exc_info=True)
        return {}

    @staticmethod
    def _dedupe_queries(items: list[object]) -> list[str]:
        out: list[str] = []
        seen: set[str] = set()
        for item in items:
            q = str(item).strip()
            if not q:
                continue
            low = q.lower()
            if low in seen:
                continue
            seen.add(low)
            out.append(q)
        return out

    def parsed_global_queries(self) -> list[str]:
        data = self._load_keywords_json()
        if data:
            merged: list[object] = []
            for key in _KEYWORD_CATEGORY_ORDER:
                chunk = data.get(key)
                if isinstance(chunk, list):
                    merged.extend(chunk)
            for key in _EXTRA_QUERY_KEYS:
                chunk = data.get(key)
                if isinstance(chunk, list):
                    merged.extend(chunk)
            out = self._dedupe_queries(merged)
            if out:
                logger.info("global search queries loaded from %s count=%d", self._search_keywords_file(), len(out))
                return out
        raw = self.search_queries.strip()
        if not raw:
            return []
        return [x.strip() for x in raw.replace("，", ",").split(",") if x.strip()]

    def parsed_chinese_keywords(self) -> list[str]:
        data = self._load_keywords_json()
        chunk = data.get("chinese_keywords")
        if isinstance(chunk, list):
            out = self._dedupe_queries(chunk)
            if out:
                return out
        return []

    def parsed_english_keywords(self) -> list[str]:
        data = self._load_keywords_json()
        chunk = data.get("english_keywords")
        if isinstance(chunk, list):
            out = self._dedupe_queries(chunk)
            if out:
                return out
        return []

    def parsed_ingest_pin_urls(self) -> list[str]:
        raw = (self.ingest_pin_urls or "").strip()
        if not raw:
            return []
        return [u.strip() for u in raw.replace("，", ",").split(",") if u.strip().startswith("http")]

    def parsed_ingest_zh_html_source_ids(self) -> list[str]:
        raw = (self.ingest_zh_html_source_ids or "").strip()
        if not raw:
            return []
        return [x.strip() for x in raw.replace("，", ",").split(",") if x.strip()]

    def parsed_gdelt_english_keywords(self) -> list[str]:
        """主链路 GDELT 专用词表；未配置 ``gdelt_english_keywords`` 时回退 ``english_keywords``。"""
        data = self._load_keywords_json()
        chunk = data.get("gdelt_english_keywords")
        if isinstance(chunk, list):
            out = self._dedupe_queries(chunk)
            if out:
                return out
        return self.parsed_english_keywords()

    def parsed_site_queries(self) -> list[str]:
        """兼容旧逻辑：合并站点/分类/中英词。主链路 ingest 已改用主题级 GDELT，仅在为 True 时使用。"""
        data = self._load_keywords_json()
        merged: list[object] = []
        for key in _SITE_KEYWORD_KEYS:
            chunk = data.get(key, [])
            if isinstance(chunk, list):
                merged.extend(chunk)
        for key in _EXTRA_QUERY_KEYS:
            chunk = data.get(key)
            if isinstance(chunk, list):
                merged.extend(chunk)
        out = self._dedupe_queries(merged)
        if out:
            logger.info("site-core queries loaded from %s count=%d", self._search_keywords_file(), len(out))
            return out
        return [
            "无人机",
            "eVTOL",
            "低空经济",
            "飞行汽车",
            "城市空中交通",
            "通用航空",
            "电动垂直起降",
        ]

    def parsed_target_sites(self) -> list[str]:
        raw = self.search_target_sites.strip()
        if not raw:
            raw = self.schedule_search_site_domain.strip()
        parts = [x.strip() for x in raw.replace("，", ",").split(",") if x.strip()]
        if self.search_load_his_data_sources:
            parts.extend(self._load_his_data_source_sites())
        out: list[str] = []
        seen: set[str] = set()
        for p in parts:
            site = p.lower().replace("https://", "").replace("http://", "").strip().strip("/")
            if "/" in site:
                site = site.split("/", 1)[0]
            if site.startswith("www."):
                site = site[4:]
            if site and site not in seen:
                seen.add(site)
                out.append(site)
        return out

    def _load_his_data_source_sites(self) -> list[str]:
        path = Path((self.his_data_sources_path or "").strip()).expanduser()
        if not path.is_absolute():
            path = Path.cwd() / path
        if not path.is_file():
            return []
        try:
            rows = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            logger.warning("failed to parse his data sources: %s", path, exc_info=True)
            return []
        if not isinstance(rows, list):
            return []
        out: list[str] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            if str(row.get("kind", "")).strip().lower() != "web":
                continue
            value = str(row.get("value", "")).strip()
            if not value:
                continue
            out.append(value)
        if out:
            logger.info("loaded high-quality sites from %s count=%d", path, len(out))
        return out

    def data_path(self) -> Path:
        p = Path(self.data_dir).expanduser().resolve()
        p.mkdir(parents=True, exist_ok=True)
        return p

    def wechat_ready(self) -> bool:
        return bool(self.wechat_mp_app_id.strip() and self.wechat_mp_app_secret.strip())

