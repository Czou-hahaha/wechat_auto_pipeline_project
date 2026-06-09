#!/usr/bin/env python3
"""清理事件低质量扩搜稿，并手工追加指定 URL（美团无人机示例）。"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import shutil
import sys
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

import httpx

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.config import Settings
from src.event_enhancement_workflow import _ensure_package_path
from src.storage import ArticleRecord, JsonStore

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

MEITUAN_EVENT_ID = "8793ca48-2eba-43cc-ba51-1558028be79f"
MEITUAN_SEED_URL = "https://www.yicai.com/news/103195055.html"
MEITUAN_ADD_URLS = [
    "https://www.stdaily.com/web/gdxw/2026-05/21/content_520368.html",
    "https://www.stcn.com/article/detail/3923677.html",
]


def _norm_url(url: str) -> str:
    return (url or "").strip().rstrip("/")


def _is_seed(row: dict) -> bool:
    status = str(row.get("status") or "").strip().lower()
    url = _norm_url(str(row.get("resolved_url") or row.get("source_url") or ""))
    if url and url == _norm_url(MEITUAN_SEED_URL):
        return True
    return status in {"pending_summary", "ready_for_review", "published"}


async def _fetch_article(url: str, *, timeout: float = 45.0) -> tuple[str, str, str]:
    _ensure_package_path()
    from event_enhancement.extract.article_body import (
        extract_body_trafilatura,
        fetch_html_text_with_effective_url,
    )
    from event_enhancement.scoring.importance import host_from_url

    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True, trust_env=True) as client:
        html, page_eff = await fetch_html_text_with_effective_url(client, url, timeout_sec=timeout)
    store_url = (page_eff or url).strip()
    body = extract_body_trafilatura(html, page_url=store_url, min_chars=80)
    if not body:
        raise RuntimeError(f"正文提取失败: {url}")
    title = ""
    if "<title" in html.lower():
        import re

        m = re.search(r"<title[^>]*>([^<]+)</title>", html, re.I)
        if m:
            title = m.group(1).strip()
    if not title:
        title = body.split("\n", 1)[0].strip()[:120] or "未命名"
    host = host_from_url(store_url)
    return store_url, title, body


def _backup(data_dir: Path) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    for name in ("articles.json", "event_article_map.json", "event_enhancement_last_run.json"):
        src = data_dir / name
        if src.is_file():
            shutil.copy2(src, data_dir / f"{name}.bak.{ts}")


def _update_enhancement_log(data_dir: Path, event_id: str, passed: list[dict]) -> None:
    path = data_dir / "event_enhancement_last_run.json"
    payload: dict = {}
    if path.is_file():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            payload = {}
    if not isinstance(payload, dict):
        payload = {}
    events = [e for e in (payload.get("events") or []) if str(e.get("event_id") or "") != event_id]
    events.insert(
        0,
        {
            "event_id": event_id,
            "event_title": "美团无人机宣布低空航网常态化运营并招募服务商",
            "status": "success",
            "articles_inserted": len(passed),
            "similarity_threshold": 0.7,
            "urls_passed_similarity": passed,
            "urls_added_to_store": [p["url"] for p in passed],
            "reason": "manual_repair",
        },
    )
    payload["events"] = events
    payload["generated_at"] = datetime.now(timezone.utc).isoformat()
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


async def repair_meituan(*, dry_run: bool = False) -> None:
    settings = Settings()
    data_dir = Path(settings.data_dir)
    store = JsonStore(data_dir)
    event_id = MEITUAN_EVENT_ID

    articles = store._read()
    event_rows = [a for a in articles if str(a.get("event_id") or "") == event_id]
    if not event_rows:
        raise SystemExit(f"未找到 event_id={event_id} 的稿件")

    seeds = [a for a in event_rows if _is_seed(a)]
    if len(seeds) != 1:
        logger.warning("种子稿数量=%d，将保留全部非 event_enhancement 稿", len(seeds))
    seed_ids = {str(a.get("id") or "") for a in seeds}

    remove_ids = {
        str(a.get("id") or "")
        for a in event_rows
        if str(a.get("id") or "") not in seed_ids
    }
    logger.info("将删除扩搜稿 %d 篇，保留种子 %d 篇", len(remove_ids), len(seed_ids))
    for aid in remove_ids:
        row = next(a for a in event_rows if str(a.get("id") or "") == aid)
        logger.info("  删除: %s", (row.get("title") or "")[:70])

    new_rows: list[dict] = []
    passed_detail: list[dict] = []
    now_iso = datetime.now(timezone.utc).isoformat()

    for url in MEITUAN_ADD_URLS:
        store_url, title, body = await _fetch_article(url)
        logger.info("抓取成功: %s | %s", title[:60], store_url)
        art_id = str(uuid.uuid4())
        rec = ArticleRecord(
            id=art_id,
            title=title,
            source_url=url,
            source_published_at="",
            extracted_text=body,
            summary="【事件增强·手工追加】美团低空航网相关报道。",
            status="event_enhancement",
            created_at=now_iso,
            published_at="",
            source_published_at_date_only=False,
            resolved_url=store_url,
            source_host=__import__("urllib.parse").urlparse(store_url).netloc,
            topic_key="",
            topic_category="",
            topic_is_important=False,
            topic_source_count=0,
            deepseek_semantic_decision="",
            novelty_passed=False,
            wechat_draft_pushed_at="",
            cluster_size=0,
            synthesis_multi_source=True,
            event_id=event_id,
            summary_zh="",
            expansion_similarity=0.95,
        )
        new_rows.append(rec)
        passed_detail.append(
            {
                "url": store_url,
                "source_hit": url,
                "similarity": 0.95,
                "title": title[:160],
            }
        )

    if dry_run:
        logger.info("dry-run: 未写入数据库")
        return

    _backup(data_dir)

    kept = [a for a in articles if str(a.get("id") or "") not in remove_ids]
    for rec in new_rows:
        kept.append(asdict(rec))
    store._write(kept)

    # 重建 event_article_map（该事件）
    maps = [m for m in store._read_event_map() if str(m.get("event_id") or "") != event_id]
    for seed in seeds:
        su = str(seed.get("source_url") or "")
        ru = str(seed.get("resolved_url") or su)
        maps.append({"event_id": event_id, "source_url": su, "resolved_url": ru, "role": "primary"})
    for rec in new_rows:
        maps.append(
            {
                "event_id": event_id,
                "source_url": rec.source_url,
                "resolved_url": rec.resolved_url,
                "role": "support",
            }
        )
    store._write_event_map(maps)
    _update_enhancement_log(data_dir, event_id, passed_detail)

    final = store.articles_for_event(event_id)
    logger.info(
        "repair done event=%s articles=%d (seed=%d expansion=%d)",
        event_id[:13],
        len(final),
        sum(1 for a in final if str(a.get("status") or "") != "event_enhancement"),
        sum(1 for a in final if str(a.get("status") or "") == "event_enhancement"),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Repair Meituan drone event expansion articles")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    asyncio.run(repair_meituan(dry_run=args.dry_run))


if __name__ == "__main__":
    main()
