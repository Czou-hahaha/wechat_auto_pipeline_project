"""
阶段三：事件增强 — ``run_once`` **必选**环节。

在「检索 → 聚类/成稿 → 落 JSON」之后**始终**执行事件增强，分两种存储后端：

1. **未配置** ``EVENT_ENHANCEMENT_DATABASE_URL``：**JSON 模式** — 不经过 PostgreSQL；GDELT 扩搜 + 向量门槛通过后直接追加
   ``articles.json`` / ``event_article_map.json``；运行摘要写入 ``<DATA_DIR>/event_enhancement_last_run.json``（仍须 ``expansion.yaml`` 与向量/GDELT 依赖）。
2. **已配置** ``EVENT_ENHANCEMENT_DATABASE_URL``：**PG 模式** — 将三份 JSON 同步到 PostgreSQL（表结构见 ``V3/docs/数据库结构_事件增强.md``），扩搜写 PG，再把 PG 独有 URL 合并回 JSON。

**未安装** Python 依赖时，``run_once`` 会失败（显式错误信息）。
"""
from __future__ import annotations

import logging
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.config import Settings
    from src.storage import JsonStore

logger = logging.getLogger(__name__)


def _repo_root() -> Path:
    """``V3/src/foo.py`` → 仓库根（与 ``event_enhancement/`` 同级）。"""
    return Path(__file__).resolve().parents[2]


def _event_enhancement_src_path() -> Path:
    """仓库内 ``event_enhancement`` 子项目根（其下为可导入包 ``event_enhancement/``）。"""
    return _repo_root() / "event_enhancement"


def _ensure_package_path() -> None:
    """将 ``…/event_enhancement`` 加入 ``sys.path``，以便 ``import event_enhancement.*``。"""
    root = str(_event_enhancement_src_path())
    if root not in sys.path:
        sys.path.insert(0, root)


def _parse_iso_dt(raw: str) -> datetime | None:
    s = (raw or "").strip()
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def _enhancement_config_path(settings: "Settings") -> Path:
    raw = (settings.event_enhancement_config_path or "").strip()
    if raw:
        p = Path(raw).expanduser()
        return p if p.is_absolute() else (Path.cwd() / p)
    return _repo_root() / "event_enhancement" / "config" / "expansion.yaml"


def _require_database_url(settings: "Settings") -> str:
    url = (settings.event_enhancement_database_url or "").strip()
    if not url:
        raise RuntimeError(
            "事件增强为必选阶段：请在运行目录的 .env 中配置 EVENT_ENHANCEMENT_DATABASE_URL="
            "'postgresql+asyncpg://用户:密码@主机:端口/库名'；并在库上执行 "
            "`event_enhancement/alembic` 迁移（至少 revision 002）。说明见 V3/docs/数据库结构_事件增强.md"
        )
    return url


def _build_enhancement_settings(settings: "Settings"):
    _ensure_package_path()
    from event_enhancement.settings import Settings as EnhancementSettings

    return EnhancementSettings.model_validate(
        {
            "DATABASE_URL": _require_database_url(settings),
            "EXPANSION_CONFIG_PATH": str(_enhancement_config_path(settings)),
            "EMBEDDING_MODEL_ID": (settings.embedding_model or "BAAI/bge-m3").strip(),
            "GDELT_BASE_URL": (settings.gdelt_base_url or "").strip()
            or "https://api.gdeltproject.org/api/v2/doc/doc",
        }
    )


async def sync_json_store_to_postgres(store: "JsonStore", settings: "Settings") -> None:
    """把当前 JSON 中的事件与关联稿件 upsert 到 PG（与 V3 字段对齐）。"""
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession

    from event_enhancement.db.models import Article, Event, EventArticleMap
    from event_enhancement.db.session import async_session_factory, create_async_engine_from_settings

    enh_settings = _build_enhancement_settings(settings)
    engine = create_async_engine_from_settings(enh_settings)
    factory = async_session_factory(engine)
    articles_rows = store.list_all()
    events_rows = store._read_events()  # noqa: SLF001
    map_rows = store._read_event_map()  # noqa: SLF001

    url_to_uuid: dict[str, uuid.UUID] = {}
    for row in articles_rows:
        if not isinstance(row, dict):
            continue
        eid = str(row.get("event_id") or "").strip()
        if not eid:
            continue
        aid = str(row.get("id") or "").strip()
        url = str(row.get("resolved_url") or row.get("source_url") or "").strip()
        if not aid or not url:
            continue
        try:
            uid = uuid.UUID(aid)
            url_to_uuid[url] = uid
            su = str(row.get("source_url") or "").strip()
            ru = str(row.get("resolved_url") or "").strip()
            if su:
                url_to_uuid[su] = uid
            if ru:
                url_to_uuid[ru] = uid
        except ValueError:
            logger.warning("skip article invalid uuid id=%s", aid[:16])

    async with factory() as session:
        assert isinstance(session, AsyncSession)
        for ev in events_rows:
            if not isinstance(ev, dict):
                continue
            eid_raw = str(ev.get("id") or "").strip()
            if not eid_raw:
                continue
            try:
                eid = uuid.UUID(eid_raw)
            except ValueError:
                continue
            title = str(ev.get("title") or "").strip() or "未命名"
            dom = str(ev.get("dominant_topic_key") or "").strip() or None
            summ = str(ev.get("summary") or "").strip() or None
            summ_zh = str(ev.get("summary_zh") or "").strip() or None
            created = _parse_iso_dt(str(ev.get("created_at") or "")) or datetime.now(timezone.utc)
            existing = await session.get(Event, eid)
            if existing is None:
                session.add(
                    Event(
                        id=eid,
                        title=title,
                        dominant_topic_key=dom,
                        created_at=created,
                        updated_at=created,
                        first_seen_at=created,
                        importance_score=0,
                        article_count=0,
                        summary=summ,
                        summary_zh=summ_zh,
                    )
                )
            else:
                existing.title = title
                existing.dominant_topic_key = dom
                existing.summary = summ
                existing.summary_zh = summ_zh
                existing.updated_at = datetime.now(timezone.utc)

        for row in articles_rows:
            if not isinstance(row, dict):
                continue
            eid_str = str(row.get("event_id") or "").strip()
            if not eid_str:
                continue
            aid_raw = str(row.get("id") or "").strip()
            url = str(row.get("resolved_url") or row.get("source_url") or "").strip()
            if not aid_raw or not url:
                continue
            try:
                aid = uuid.UUID(aid_raw)
            except ValueError:
                continue
            title = str(row.get("title") or "").strip() or "未命名"
            body = str(row.get("extracted_text") or "")
            host = str(row.get("source_host") or "").strip()
            pub = _parse_iso_dt(str(row.get("source_published_at") or ""))
            su = str(row.get("source_url") or "").strip() or None
            ru = str(row.get("resolved_url") or "").strip() or None
            summary = str(row.get("summary") or "").strip() or None
            summary_zh = str(row.get("summary_zh") or "").strip() or None
            status = str(row.get("status") or "").strip() or None
            topic_key = str(row.get("topic_key") or "").strip() or None
            res = await session.execute(select(Article).where(Article.url == url))
            existing = res.scalar_one_or_none()
            if existing is None:
                session.add(
                    Article(
                        id=aid,
                        url=url,
                        title=title,
                        published_at=pub,
                        body_text=body or None,
                        source_host=host,
                        source_tier="",
                        embedding=None,
                        source_url=su,
                        resolved_url=ru,
                        summary=summary,
                        summary_zh=summary_zh,
                        status=status,
                        topic_key=topic_key,
                    )
                )
            else:
                existing.title = title
                existing.body_text = body or existing.body_text
                existing.source_host = host or existing.source_host
                if pub is not None:
                    existing.published_at = pub
                existing.source_url = su or existing.source_url
                existing.resolved_url = ru or existing.resolved_url
                existing.summary = summary if summary is not None else existing.summary
                existing.summary_zh = summary_zh if summary_zh is not None else existing.summary_zh
                existing.status = status or existing.status
                existing.topic_key = topic_key or existing.topic_key

        for m in map_rows:
            if not isinstance(m, dict):
                continue
            eid_raw = str(m.get("event_id") or "").strip()
            su = str(m.get("source_url") or "").strip()
            ru = str(m.get("resolved_url") or "").strip()
            if not eid_raw or not su:
                continue
            try:
                eid = uuid.UUID(eid_raw)
            except ValueError:
                continue
            art_url = ru or su
            aid = url_to_uuid.get(su) or url_to_uuid.get(ru) or url_to_uuid.get(art_url)
            if aid is None:
                logger.debug("map row skip no article match event=%s url=%s", eid_raw[:8], su[:60])
                continue
            res = await session.execute(
                select(EventArticleMap).where(
                    EventArticleMap.event_id == eid,
                    EventArticleMap.article_id == aid,
                )
            )
            if res.scalar_one_or_none() is None:
                role = str(m.get("role") or "source").strip() or "source"
                session.add(
                    EventArticleMap(
                        id=uuid.uuid4(),
                        event_id=eid,
                        article_id=aid,
                        role=role,
                        similarity_to_centroid=None,
                    )
                )
        await session.commit()
    await engine.dispose()


async def merge_postgres_articles_into_json(store: "JsonStore", settings: "Settings") -> int:
    """将 PG 中存在、但 JSON 中尚无 URL 的稿件追加到 ``articles.json`` / ``event_article_map.json``。"""
    from collections import defaultdict

    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession

    from event_enhancement.config_expansion import ExpansionConfig
    from event_enhancement.db.models import Article, Event, EventArticleMap
    from event_enhancement.db.session import async_session_factory, create_async_engine_from_settings
    from src.storage import ArticleRecord

    cfg_path = _enhancement_config_path(settings)
    cap = (
        ExpansionConfig.from_path(cfg_path).max_articles_per_event
        if cfg_path.is_file()
        else 5
    )

    enh_settings = _build_enhancement_settings(settings)
    engine = create_async_engine_from_settings(enh_settings)
    factory = async_session_factory(engine)

    known: set[str] = set()
    json_count_by_event: dict[str, int] = defaultdict(int)
    for row in store.list_all():
        if isinstance(row, dict):
            for k in ("resolved_url", "source_url"):
                u = str(row.get(k) or "").strip()
                if u:
                    known.add(u)
            eid = str(row.get("event_id") or "").strip()
            if eid:
                json_count_by_event[eid] += 1

    added = 0
    async with factory() as session:
        assert isinstance(session, AsyncSession)
        stmt = (
            select(Article, EventArticleMap.event_id, Event.dominant_topic_key)
            .join(EventArticleMap, EventArticleMap.article_id == Article.id)
            .join(Event, Event.id == EventArticleMap.event_id)
        )
        rows = (await session.execute(stmt)).all()
        now_iso = datetime.now(timezone.utc).isoformat()
        for art, eid, dom_key in rows:
            if art.url in known:
                continue
            eid_s = str(eid)
            if json_count_by_event[eid_s] >= cap:
                logger.info(
                    "merge PG→JSON skip cap: event=%s url=%s… json_articles=%d max=%d (不删 JSON 既有行)",
                    eid_s[:13],
                    art.url[:72],
                    json_count_by_event[eid_s],
                    cap,
                )
                continue
            known.add(art.url)
            src_u = (art.source_url or art.url).strip()
            res_u = (art.resolved_url or art.url).strip()
            rec = ArticleRecord(
                id=str(art.id),
                title=art.title or "未命名",
                source_url=src_u,
                source_published_at=art.published_at.isoformat() if art.published_at else "",
                extracted_text=art.body_text or "",
                summary=(art.summary or "").strip() or "【事件增强】补充来源，待人工复核或重新摘要。",
                status=(art.status or "ready_for_review").strip() or "ready_for_review",
                created_at=now_iso,
                published_at="",
                source_published_at_date_only=False,
                resolved_url=res_u,
                source_host=art.source_host or "",
                topic_key=str(art.topic_key or dom_key or "").strip(),
                topic_category="",
                topic_is_important=False,
                topic_source_count=0,
                deepseek_semantic_decision="",
                novelty_passed=False,
                wechat_draft_pushed_at="",
                cluster_size=0,
                synthesis_multi_source=True,
                event_id=eid_s,
                summary_zh=(art.summary_zh or "").strip(),
            )
            store.add(rec)
            store.append_event_article_map(
                [
                    {
                        "event_id": eid_s,
                        "source_url": src_u,
                        "resolved_url": res_u,
                        "role": "support",
                    }
                ]
            )
            json_count_by_event[eid_s] += 1
            added += 1
    await engine.dispose()
    return added


async def run_event_enhancement_post_pipeline(store: "JsonStore", settings: "Settings") -> None:
    """由 ``run_once`` 末尾调用。无 ``EVENT_ENHANCEMENT_DATABASE_URL`` 时走 JSON 扩搜；有则走 PG。"""
    _ensure_package_path()
    try:
        from event_enhancement.config_expansion import ExpansionConfig
    except ImportError as e:
        raise RuntimeError(
            "事件增强依赖未安装：请在 V3 环境执行 pip install -r requirements.txt "
            "（需 numpy、faiss-cpu、pyyaml、httpx、sentence-transformers 等）"
        ) from e

    cfg_path = _enhancement_config_path(settings)
    if not cfg_path.is_file():
        raise RuntimeError(f"事件增强配置缺失（必选）：{cfg_path}")

    db_url = (settings.event_enhancement_database_url or "").strip()
    if not db_url:
        try:
            from src.event_enhancement_json import run_event_enhancement_json_pipeline
        except ImportError as e:
            raise RuntimeError(
                "事件增强 JSON 模式依赖未安装：pip install -r requirements.txt"
            ) from e
        logger.info("event enhancement: JSON storage mode (EVENT_ENHANCEMENT_DATABASE_URL empty)")
        logs = await run_event_enhancement_json_pipeline(store, settings)
        for row in logs:
            logger.info(
                "event enhancement json summary: event=%s status=%s inserted=%s fetched=%s",
                row.get("event_id"),
                row.get("status"),
                row.get("articles_inserted"),
                row.get("candidates_fetched"),
            )
        return

    try:
        from event_enhancement.db.session import async_session_factory, create_async_engine_from_settings
        from event_enhancement.pipeline.expansion import run_expansion_batch
    except ImportError as e:
        raise RuntimeError(
            "事件增强 PG 模式依赖未安装：pip install -r requirements.txt "
            "（含 sqlalchemy[asyncio]、asyncpg 等）"
        ) from e

    _require_database_url(settings)
    enh_settings = _build_enhancement_settings(settings)
    exp = ExpansionConfig.from_path(cfg_path)
    logger.info("event enhancement: syncing JSON → PostgreSQL")
    await sync_json_store_to_postgres(store, settings)

    engine = create_async_engine_from_settings(enh_settings)
    factory = async_session_factory(engine)
    async with factory() as session:
        logs = await run_expansion_batch(session, settings=enh_settings, exp=exp)
        await session.commit()
    await engine.dispose()

    for lg in logs:
        logger.info(
            "event enhancement run: event=%s status=%s inserted=%s fetched=%s",
            lg.event_id,
            lg.status,
            lg.articles_inserted,
            lg.candidates_fetched,
        )

    n = await merge_postgres_articles_into_json(store, settings)
    if n:
        logger.info("event enhancement: merged %d new articles into articles.json", n)
