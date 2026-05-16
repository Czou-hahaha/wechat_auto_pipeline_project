"""Load ``config/expansion.yaml`` into a typed accessor."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class GdeltSection:
    timespan: str
    max_records: int
    max_concurrent: int
    min_interval_sec: float
    backoff_base_sec: float
    backoff_max_sec: float
    jitter_sec: float
    max_retries: int


@dataclass(frozen=True)
class ExpansionConfig:
    important_hosts: list[str]
    keywords: list[str]
    anchor_terms: list[str]
    max_events_per_run: int
    expansion_ranking_window_hours: int
    expansion_ranking_timezone: str
    expansion_min_interval_hours: float
    gdelt: GdeltSection
    similarity_threshold: float
    embedding_max_input_chars: int
    http_fetch_timeout_sec: float
    trafilatura_min_chars: int
    user_agents: list[str]
    expansion_domains: list[str]
    # 单事件关联稿件上限（含 JSON 同步进 PG 的 seed）；超出则不再插入新扩搜稿，不删除历史 Article
    max_articles_per_event: int
    # GDELT：用于拼 query 的事件标题最大字符数（Unicode 字符）；None 表示不截断
    gdelt_event_title_max_chars: int | None
    gdelt_query_include_member_titles: bool
    gdelt_query_max_or_terms: int
    # ``gdelt`` | ``ddgs`` — 仅当 ``expansion_search_cascade: false`` 时生效（单后端）
    web_search_backend: str
    # 覆盖主锚词；空则取 anchor_terms 中首条含中文，否则首条
    gdelt_primary_anchor: str | None
    # true：GDELT（中文）→ Google News RSS → DDGS，每源独立重试；有入库则不再试后续源
    expansion_search_cascade: bool
    # 单源在「始终空结果」时的最大轮询次数（每轮内 GDELT 仍有 HTTP 级重试）
    search_attempts_per_source: int

    @staticmethod
    def from_path(path: Path) -> "ExpansionConfig":
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError(f"Invalid YAML in {path}")
        g = data.get("gdelt") or {}
        if not isinstance(g, dict):
            g = {}
        gdelt = GdeltSection(
            timespan=str(g.get("timespan", "12h")),
            max_records=int(g.get("max_records", 40)),
            max_concurrent=max(1, int(g.get("max_concurrent", 2))),
            min_interval_sec=float(g.get("min_interval_sec", 1.5)),
            backoff_base_sec=float(g.get("backoff_base_sec", 2.0)),
            backoff_max_sec=float(g.get("backoff_max_sec", 60.0)),
            jitter_sec=float(g.get("jitter_sec", 1.0)),
            max_retries=max(1, int(g.get("max_retries", 3))),
        )
        raw_title_cap = data.get("gdelt_event_title_max_chars")
        if raw_title_cap is None or str(raw_title_cap).strip().lower() in ("", "null", "none"):
            title_cap: int | None = 15
        else:
            v = int(raw_title_cap)
            title_cap = None if v <= 0 else min(200, v)
        raw_backend = str(data.get("web_search_backend") or "gdelt").strip().lower()
        if raw_backend not in ("gdelt", "ddgs"):
            raw_backend = "gdelt"
        raw_pa = data.get("gdelt_primary_anchor")
        primary_anchor = str(raw_pa).strip() if raw_pa not in (None, "") else None
        expansion_search_cascade = bool(data.get("expansion_search_cascade", True))
        search_attempts_per_source = max(1, min(10, int(data.get("search_attempts_per_source", 3))))
        return ExpansionConfig(
            important_hosts=list(data.get("important_hosts") or []),
            keywords=list(data.get("keywords") or []),
            anchor_terms=list(data.get("anchor_terms") or []),
            max_events_per_run=max(1, int(data.get("max_events_per_run", 3))),
            expansion_ranking_window_hours=max(1, int(data.get("expansion_ranking_window_hours", 48))),
            expansion_ranking_timezone=str(data.get("expansion_ranking_timezone", "Asia/Shanghai")),
            expansion_min_interval_hours=float(data.get("expansion_min_interval_hours", 0.0)),
            gdelt=gdelt,
            similarity_threshold=float(data.get("similarity_threshold", 0.7)),
            embedding_max_input_chars=int(data.get("embedding_max_input_chars", 8000)),
            http_fetch_timeout_sec=float(data.get("http_fetch_timeout_sec", 45.0)),
            trafilatura_min_chars=int(data.get("trafilatura_min_chars", 80)),
            user_agents=list(data.get("user_agents") or ["Mozilla/5.0 (compatible; EventEnhancement/1.0)"]),
            expansion_domains=list(data.get("expansion_domains") or []),
            max_articles_per_event=max(1, min(50, int(data.get("max_articles_per_event", 5)))),
            gdelt_event_title_max_chars=title_cap,
            gdelt_query_include_member_titles=bool(data.get("gdelt_query_include_member_titles", False)),
            gdelt_query_max_or_terms=max(1, min(12, int(data.get("gdelt_query_max_or_terms", 4)))),
            web_search_backend=raw_backend,
            gdelt_primary_anchor=primary_anchor,
            expansion_search_cascade=expansion_search_cascade,
            search_attempts_per_source=search_attempts_per_source,
        )
