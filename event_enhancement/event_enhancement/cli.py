"""CLI：seed-demo | scan | expand-batch。"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import uuid
from datetime import datetime, timezone

from event_enhancement.config_expansion import ExpansionConfig
from event_enhancement.db.models import Article, Event, EventArticleMap
from event_enhancement.db.session import async_session_factory, create_async_engine_from_settings
from event_enhancement.logging_config import setup_logging
from event_enhancement.pipeline.expansion import refresh_importance_scores, run_expansion_batch, select_events_for_expansion
from event_enhancement.settings import Settings


async def cmd_seed_demo() -> None:
    settings = Settings()
    exp = ExpansionConfig.from_path(settings.expansion_config_absolute())
    engine = create_async_engine_from_settings(settings)
    factory = async_session_factory(engine)
    now = datetime.now(timezone.utc)
    async with factory() as session:
        a1 = Article(
            id=uuid.uuid4(),
            url=f"https://demo.invalid/seed/{uuid.uuid4().hex[:8]}-a1",
            title="北京加强低空飞行管理（路透）",
            published_at=now,
            body_text="这是一条用于事件增强演示的正文，长度满足 trafilatura 最小字符门槛。" * 3,
            source_host="reuters.com",
        )
        a2 = Article(
            id=uuid.uuid4(),
            url=f"https://demo.invalid/seed/{uuid.uuid4().hex[:8]}-a2",
            title="地方政府发布无人机新规征求意见",
            published_at=now,
            body_text="另一条演示正文，用于构成事件簇与 importance 计算。" * 3,
            source_host="example.com",
        )
        ev = Event(
            id=uuid.uuid4(),
            title="北京低空与无人机监管动态",
            dominant_topic_key="local_policy",
            first_seen_at=now,
            created_at=now,
            updated_at=now,
        )
        session.add_all([a1, a2, ev])
        await session.flush()
        session.add_all(
            [
                EventArticleMap(event_id=ev.id, article_id=a1.id, role="canonical"),
                EventArticleMap(event_id=ev.id, article_id=a2.id, role="support"),
            ]
        )
        await session.commit()
        ev_id = ev.id
        a1_id, a2_id = a1.id, a2.id
    logging.getLogger(__name__).info(
        "seed-demo ok event_id=%s articles=%s,%s (请运行 scan / expand-batch)",
        ev_id,
        a1_id,
        a2_id,
    )
    await engine.dispose()


async def cmd_scan() -> None:
    from sqlalchemy import func, select

    from event_enhancement.db.models import Event
    from event_enhancement.pipeline.expansion import _ranking_cutoff

    settings = Settings()
    exp = ExpansionConfig.from_path(settings.expansion_config_absolute())
    engine = create_async_engine_from_settings(settings)
    factory = async_session_factory(engine)
    async with factory() as session:
        await refresh_importance_scores(session, exp)
        await session.commit()
        top_ids = set(
            await select_events_for_expansion(session, exp, limit=exp.max_events_per_run)
        )
        cutoff = _ranking_cutoff(exp)
        stmt_all = (
            select(Event)
            .where(func.coalesce(Event.first_seen_at, Event.created_at) >= cutoff)
            .order_by(Event.importance_score.desc())
        )
        ranked = list((await session.execute(stmt_all)).scalars().all())
    print("--- 最近窗口内事件（importance 降序）---")
    for i, e in enumerate(ranked, 1):
        mark = " <-- 本轮扩搜" if e.id in top_ids else ""
        print(f"{i}. score={e.importance_score} articles={e.article_count} id={e.id}{mark}\n   {e.title[:80]}")
    await engine.dispose()


async def cmd_expand_batch() -> None:
    settings = Settings()
    exp = ExpansionConfig.from_path(settings.expansion_config_absolute())
    engine = create_async_engine_from_settings(settings)
    factory = async_session_factory(engine)
    async with factory() as session:
        logs = await run_expansion_batch(session, settings=settings, exp=exp)
    for lg in logs:
        print(
            f"log id={lg.id} event={lg.event_id} status={lg.status} "
            f"fetched={lg.candidates_fetched} passed_sim={lg.candidates_passed_similarity} "
            f"inserted={lg.articles_inserted} reason={lg.reason!r}"
        )
    await engine.dispose()


def main(argv: list[str] | None = None) -> int:
    setup_logging()
    p = argparse.ArgumentParser(description="事件增强 Event Enhancement CLI")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("seed-demo", help="写入演示事件+文章（需已迁移数据库）")
    sub.add_parser("scan", help="刷新 importance 并打印最近窗口排行与 topN")
    sub.add_parser("expand-batch", help="对 topN 执行一轮扩搜")
    args = p.parse_args(argv)
    if args.cmd == "seed-demo":
        asyncio.run(cmd_seed_demo())
    elif args.cmd == "scan":
        asyncio.run(cmd_scan())
    elif args.cmd == "expand-batch":
        asyncio.run(cmd_expand_batch())
    else:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
