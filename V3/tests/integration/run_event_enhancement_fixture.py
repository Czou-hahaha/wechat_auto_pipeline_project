"""
用「历史向量聚类落库」目录（articles + events + event_article_map）跑阶段三事件增强。

默认 ``tests/data/dedupe_runs/beijing``。原始 fixture 不改动：复制到工作目录 → hydrate → 刷新时间窗 →
``run_event_enhancement_post_pipeline``。

存储后端：

- **``EVENT_ENHANCEMENT_DATABASE_URL`` 留空**：**JSON 模式** — 无 PostgreSQL；GDELT+向量通过后直接写工作目录下
  ``articles.json`` / ``event_article_map.json``，摘要 ``event_enhancement_last_run.json``。
- **已配置 URL**：**PG 模式** — JSON→PostgreSQL→扩搜→再合并回 JSON（须 Alembic）。

依赖：``pip install -r requirements.txt``（向量与 httpx；PG 模式另需 sqlalchemy/asyncpg）。

用法（在 ``V3/`` 下）::

    unset EVENT_ENHANCEMENT_DATABASE_URL   # JSON 模式
    python tests/integration/run_event_enhancement_fixture.py

    export EVENT_ENHANCEMENT_DATABASE_URL='postgresql+asyncpg://…'  # PG 模式
    python tests/integration/run_event_enhancement_fixture.py
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import shutil
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

_V3_ROOT = Path(__file__).resolve().parents[2]
if str(_V3_ROOT) not in sys.path:
    sys.path.insert(0, str(_V3_ROOT))


logger = logging.getLogger(__name__)


def _article_url_set(rows: list[dict]) -> set[str]:
    out: set[str] = set()
    for a in rows:
        if not isinstance(a, dict):
            continue
        for k in ("source_url", "resolved_url"):
            v = str(a.get(k) or "").strip()
            if v:
                out.add(v)
    return out


def _host_label(url: str) -> str:
    try:
        host = (urlparse(url).hostname or "").lower()
        return host or "unknown"
    except Exception:
        return "unknown"


def hydrate_articles_from_event_map(data_dir: Path) -> int:
    """
    ``run_embedding_urls_ingest`` 等脚本可能只把「代表稿」写入 ``articles.json``，而 ``event_article_map.json``
    仍含多源 URL。同步 PG 时 ``url_to_uuid`` 只来自 articles，缺行会导致 map 无法关联。
    本函数为 map 中尚未出现在 articles 的 URL 追加最小可嵌入正文占位行（同一 ``event_id``）。
    """
    articles_path = data_dir / "articles.json"
    map_path = data_dir / "event_article_map.json"
    events_path = data_dir / "events.json"

    articles: list[dict] = json.loads(articles_path.read_text(encoding="utf-8"))
    maps: list[dict] = json.loads(map_path.read_text(encoding="utf-8"))
    events: list[dict] = json.loads(events_path.read_text(encoding="utf-8"))

    urls = _article_url_set(articles)
    ev_by_id = {str(e.get("id") or ""): e for e in events if isinstance(e, dict)}

    now = datetime.now(timezone.utc).isoformat()
    stub_body = (
        "【历史聚类测试占位正文】与北京市无人驾驶航空器管理、禁飞禁售等主题相关的同簇成员稿；"
        "用于事件增强管线嵌入与 GDELT 相似度门槛，非生产摘要。"
        * 6
    )

    added = 0
    for m in maps:
        if not isinstance(m, dict):
            continue
        eid = str(m.get("event_id") or "").strip()
        su = str(m.get("source_url") or "").strip()
        ru = str(m.get("resolved_url") or "").strip() or su
        if not eid or not su:
            continue
        if su in urls or ru in urls:
            continue
        ev = ev_by_id.get(eid, {})
        title_hint = str(ev.get("title") or "同题簇成员").strip()[:80]
        art_id = str(uuid.uuid4())
        host = _host_label(su)
        row = {
            "id": art_id,
            "title": f"[聚类成员·{host}] {title_hint}",
            "source_url": su,
            "source_published_at": now,
            "extracted_text": stub_body,
            "summary": "【fixture 占位摘要】同簇成员，待扩搜或人工复核。",
            "status": "dedupe_test_stub",
            "created_at": now,
            "published_at": "",
            "source_published_at_date_only": True,
            "resolved_url": ru,
            "source_host": host.split(":")[0] if host else "",
            "topic_key": str(ev.get("dominant_topic_key") or "").strip(),
            "topic_category": "other",
            "topic_is_important": False,
            "topic_source_count": 1,
            "deepseek_semantic_decision": "fixture_hydrate",
            "novelty_passed": True,
            "wechat_draft_pushed_at": "",
            "cluster_size": 1,
            "synthesis_multi_source": False,
            "event_id": eid,
            "summary_zh": "",
        }
        articles.append(row)
        urls.add(su)
        if ru:
            urls.add(ru)
        added += 1
        logger.info("hydrate: added article id=%s url=%s", art_id[:8], su[:72])

    if added:
        articles_path.write_text(json.dumps(articles, ensure_ascii=False, indent=2), encoding="utf-8")
    return added


def touch_event_ranking_timestamps(data_dir: Path) -> None:
    """将事件与稿件时间戳拨到「现在」，避免 fixture 日期落后于 expansion 排名窗。"""
    now = datetime.now(timezone.utc).isoformat()
    for name in ("articles.json", "events.json"):
        p = data_dir / name
        rows = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(rows, list):
            continue
        for row in rows:
            if isinstance(row, dict):
                row["created_at"] = now
                if name == "articles.json":
                    row.setdefault("source_published_at", now)
        p.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("touch: refreshed created_at (and article source_published_at) to %s", now)


def prepare_work_dir(*, fixture_dir: Path, work_dir: Path, clean: bool) -> None:
    if not fixture_dir.is_dir():
        raise FileNotFoundError(f"fixture-dir 不是目录: {fixture_dir}")
    for name in ("articles.json", "events.json", "event_article_map.json"):
        if not (fixture_dir / name).is_file():
            raise FileNotFoundError(f"fixture 缺少 {name}: {fixture_dir}")

    if work_dir.exists() and clean:
        shutil.rmtree(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    for name in ("articles.json", "events.json", "event_article_map.json"):
        shutil.copy2(fixture_dir / name, work_dir / name)
    logger.info("copied fixture %s -> %s", fixture_dir, work_dir)


async def _async_main(work_dir: Path) -> None:
    from src.config import Settings
    from src.event_enhancement_workflow import run_event_enhancement_post_pipeline
    from src.storage import JsonStore

    # Settings 从 V3/.env 加载；工作库路径仅影响 JsonStore
    settings = Settings()
    store = JsonStore(work_dir)
    await run_event_enhancement_post_pipeline(store, settings)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="用历史聚类 fixture 跑事件增强（阶段三）")
    parser.add_argument(
        "--fixture-dir",
        type=Path,
        default=Path("tests/data/dedupe_runs/beijing"),
        help="含 articles.json / events.json / event_article_map.json 的目录（相对 V3 或绝对）",
    )
    parser.add_argument(
        "--work-dir",
        type=Path,
        default=Path("tests/data/event_enhancement_runs/last_fixture_run"),
        help="可写工作目录（默认相对 V3）；--clean 时会删除后重建",
    )
    parser.set_defaults(clean=True)
    parser.add_argument(
        "--no-clean",
        action="store_false",
        dest="clean",
        help="不删除 work-dir：在原目录上覆盖三份 JSON（慎用）",
    )
    parser.add_argument(
        "--no-hydrate",
        action="store_true",
        help="不根据 event_article_map 补齐 articles（仅当 fixture 已含全部成员时使用）",
    )
    parser.add_argument(
        "--no-touch-time",
        action="store_true",
        help="不刷新 created_at（仅当事件仍在 ranking 窗口内时使用）",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-5s %(name)s - %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)

    os_cwd = Path.cwd()
    try:
        # 保证 .env / config 相对路径与生产一致
        import os

        os.chdir(_V3_ROOT)

        fixture_dir = args.fixture_dir.expanduser()
        if not fixture_dir.is_absolute():
            fixture_dir = (_V3_ROOT / fixture_dir).resolve()

        work_dir = args.work_dir.expanduser()
        if not work_dir.is_absolute():
            work_dir = (_V3_ROOT / work_dir).resolve()

        prepare_work_dir(fixture_dir=fixture_dir, work_dir=work_dir, clean=args.clean)
        if not args.no_hydrate:
            n = hydrate_articles_from_event_map(work_dir)
            logger.info("hydrate: appended %d stub article(s)", n)
        if not args.no_touch_time:
            touch_event_ranking_timestamps(work_dir)

        asyncio.run(_async_main(work_dir))
    finally:
        import os

        os.chdir(os_cwd)

    logger.info("done. work_dir=%s (articles/events/map 可能已被阶段三回写)", work_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
