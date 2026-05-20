#!/usr/bin/env python3
"""恢复英国无人机事件数据并重跑簇摘要 + 微信草稿推送。"""
from __future__ import annotations

import asyncio
import json
import logging
import sys
from pathlib import Path

_V3_ROOT = Path(__file__).resolve().parents[2]
_REPO_ROOT = _V3_ROOT.parent
if str(_V3_ROOT) not in sys.path:
    sys.path.insert(0, str(_V3_ROOT))
sys.path.insert(0, str(_REPO_ROOT / "event_enhancement"))

from src.config import Settings
from src.pipeline import PipelineRunner

UK_EVENT_ID = "31f4616f-3664-48b4-ad8d-84b85527d525"
BACKUP_DIR = _V3_ROOT / "data" / "backup_before_zh_html_20260519T154255"


def _load_json(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, list) else []


def _merge_rows(current: list[dict], incoming: list[dict], *, key: str) -> list[dict]:
    by_key = {str(r.get(key) or "").strip(): r for r in current if isinstance(r, dict)}
    for row in incoming:
        if not isinstance(row, dict):
            continue
        kid = str(row.get(key) or "").strip()
        if not kid:
            continue
        by_key[kid] = row
    return list(by_key.values())


def _merge_map(current: list[dict], incoming: list[dict]) -> list[dict]:
    seen: set[tuple[str, str]] = set()
    out: list[dict] = []
    for row in current + incoming:
        if not isinstance(row, dict):
            continue
        eid = str(row.get("event_id") or "").strip()
        url = str(row.get("resolved_url") or row.get("source_url") or "").strip()
        if not eid or not url:
            continue
        key = (eid, url)
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


def restore_uk_from_backup(store) -> None:
    """将备份中的 UK 事件、文章与映射合并进当前 data/。"""
    articles = _load_json(store.data_dir / "articles.json")
    events = _load_json(store.data_dir / "events.json")
    maps = _load_json(store.data_dir / "event_article_map.json")

    bak_articles = [r for r in _load_json(BACKUP_DIR / "articles.json") if str(r.get("event_id") or "") == UK_EVENT_ID]
    bak_events = [r for r in _load_json(BACKUP_DIR / "events.json") if str(r.get("id") or "") == UK_EVENT_ID]
    bak_maps = [r for r in _load_json(BACKUP_DIR / "event_article_map.json") if str(r.get("event_id") or "") == UK_EVENT_ID]

    if not bak_articles or not bak_events:
        raise SystemExit(f"backup missing UK event data under {BACKUP_DIR}")

    for row in bak_articles:
        row["summary"] = ""
        row["summary_zh"] = ""
        row["wechat_draft_pushed_at"] = ""
        row["published_at"] = ""
        if str(row.get("status") or "") == "published":
            row["status"] = "pending_summary"
        if str(row.get("summary") or "").startswith("【事件增强"):
            row["summary"] = ""

    for ev in bak_events:
        ev["summary"] = ""
        ev["summary_zh"] = ""

    articles = _merge_rows(articles, bak_articles, key="id")
    events = _merge_rows(events, bak_events, key="id")
    maps = _merge_map(maps, bak_maps)

    (store.data_dir / "articles.json").write_text(
        json.dumps(articles, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (store.data_dir / "events.json").write_text(
        json.dumps(events, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (store.data_dir / "event_article_map.json").write_text(
        json.dumps(maps, ensure_ascii=False, indent=2), encoding="utf-8"
    )


async def refresh_uk_published_at(runner: PipelineRunner) -> None:
    """从落地页重新解析发布时间并写回库。"""
    for row in runner.store.articles_for_event(UK_EVENT_ID):
        url = str(row.get("resolved_url") or row.get("source_url") or "").strip()
        aid = str(row.get("id") or "").strip()
        if not url or not aid:
            continue
        title, text, _, final_url, page_published_at, page_date_only = await runner._fetch_text(
            url,
            fallback_title=str(row.get("title") or ""),
            fallback_snippet=str(row.get("extracted_text") or "")[:500],
        )
        resolved, date_only = runner._resolve_source_published_at(
            page_published_at=page_published_at,
            page_date_only_coarse=page_date_only,
        )
        updates: dict = {}
        if text and len(text) >= 200:
            updates["extracted_text"] = text
        if title:
            updates["title"] = title
        if final_url:
            updates["resolved_url"] = final_url
        if resolved:
            updates["source_published_at"] = resolved
            updates["source_published_at_date_only"] = date_only
        if updates:
            runner.store.patch_article(aid, updates)
            logging.info(
                "refreshed article %s published_at=%s date_only=%s url=%s",
                aid[:8],
                resolved or "(missing)",
                date_only,
                final_url or url,
            )
        else:
            logging.warning("no published_at from page: %s", url)


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s - %(message)s")
    settings = Settings()
    runner = PipelineRunner(settings)
    restore_uk_from_backup(runner.store)
    await refresh_uk_published_at(runner)
    publish = bool(settings.run_once_push_to_wechat)
    stats = await runner._finalize_event_summaries_and_publish(
        [UK_EVENT_ID],
        publish_to_wechat=publish,
    )
    logging.info("resummarize_uk_event done publish=%s stats=%s", publish, stats)
    ev = runner.store.get_event(UK_EVENT_ID)
    if ev:
        summary = str(ev.get("summary") or "")
        logging.info("event title: %s", ev.get("title"))
        logging.info("summary preview (500 chars): %s", summary[:500])
        if "<strong>" in summary:
            logging.info("summary contains <strong> highlights")
        if "口径不一致" in summary:
            logging.warning("summary still mentions 口径不一致")
    if stats.get("published", 0) == 0 and publish:
        logging.warning("wechat push did not publish; check QA / cooldown / token")


if __name__ == "__main__":
    asyncio.run(main())
