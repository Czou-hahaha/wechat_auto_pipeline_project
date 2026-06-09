#!/usr/bin/env python3
"""按扩搜 pipeline 同一套 bge-m3 逻辑，回填 event 下扩搜稿相对种子稿 bank 的真实相似度。"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

_ROOT = Path(__file__).resolve().parents[1]
_REPO = _ROOT.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.config import Settings
from src.event_enhancement_workflow import _ensure_package_path
from src.storage import JsonStore

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DEFAULT_EVENT_ID = "8793ca48-2eba-43cc-ba51-1558028be79f"
MAX_INPUT_CHARS = 8000


def _max_cosine_vs_bank(candidate: np.ndarray, bank: np.ndarray) -> float:
    if bank.size == 0:
        return 0.0
    c = np.asarray(candidate, dtype=np.float32).reshape(-1)
    b = np.asarray(bank, dtype=np.float32)
    cn = c / (np.linalg.norm(c) + 1e-12)
    bn = b / (np.linalg.norm(b, axis=1, keepdims=True) + 1e-12)
    return float(np.max(bn @ cn))


def _text_blob(row: dict) -> str:
    title = str(row.get("title") or "").strip()
    body = str(row.get("extracted_text") or "").strip()
    return f"{title}\n{body}"[:MAX_INPUT_CHARS]


def _is_seed(row: dict) -> bool:
    status = str(row.get("status") or "").strip().lower()
    return status != "event_enhancement"


async def recompute_event(store: JsonStore, event_id: str, *, dry_run: bool = False) -> list[dict]:
    _ensure_package_path()
    from event_enhancement.embed import bge_m3

    settings = Settings()
    model_id = (settings.embedding_model or "BAAI/bge-m3").strip()

    members = store.articles_for_event(event_id)
    if not members:
        raise SystemExit(f"event {event_id} 无关联稿件")

    seeds = [m for m in members if _is_seed(m)]
    expansions = [m for m in members if not _is_seed(m)]
    if not seeds:
        raise SystemExit(f"event {event_id} 无种子稿")
    if not expansions:
        logger.info("event %s 无扩搜稿，跳过", event_id[:13])
        return []

    seed_texts = [_text_blob(m) for m in seeds]
    logger.info("preload embedding model=%s", model_id)
    await bge_m3.encode_texts(["preload"], model_id)

    seed_vecs = await bge_m3.encode_texts(seed_texts, model_id)
    bank = np.stack([np.asarray(v, dtype=np.float32).reshape(-1) for v in seed_vecs], axis=0)

    results: list[dict] = []
    for row in expansions:
        aid = str(row.get("id") or "")
        text = _text_blob(row)
        vecs = await bge_m3.encode_texts([text], model_id)
        sim = _max_cosine_vs_bank(np.asarray(vecs[0], dtype=np.float32), bank)
        sim_r = round(float(sim), 4)
        old = row.get("expansion_similarity")
        results.append(
            {
                "id": aid,
                "title": str(row.get("title") or "")[:80],
                "url": str(row.get("resolved_url") or row.get("source_url") or ""),
                "similarity": sim_r,
                "previous": old,
            }
        )
        logger.info(
            "sim=%.4f (was %s) | %s",
            sim_r,
            old,
            results[-1]["title"],
        )
        if not dry_run and aid:
            store.patch_article(aid, {"expansion_similarity": sim_r})

    if dry_run:
        return results

    _update_enhancement_log(store.data_dir, event_id, results)
    return results


def _update_enhancement_log(data_dir: Path, event_id: str, results: list[dict]) -> None:
    path = data_dir / "event_enhancement_last_run.json"
    payload: dict = {}
    if path.is_file():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            payload = {}
    if not isinstance(payload, dict):
        payload = {}

    passed = [
        {
            "url": r["url"],
            "similarity": r["similarity"],
            "title": r["title"][:160],
        }
        for r in results
        if r.get("url")
    ]
    events = [e for e in (payload.get("events") or []) if str(e.get("event_id") or "") != event_id]
    events.insert(
        0,
        {
            "event_id": event_id,
            "status": "success",
            "similarity_threshold": 0.7,
            "urls_passed_similarity": passed,
            "urls_added_to_store": [p["url"] for p in passed],
            "articles_inserted": len(passed),
            "reason": "similarity_backfill",
        },
    )
    payload["events"] = events
    payload["generated_at"] = datetime.now(timezone.utc).isoformat()
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("updated %s", path)


def _backup(data_dir: Path) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    for name in ("articles.json", "event_enhancement_last_run.json"):
        src = data_dir / name
        if src.is_file():
            shutil.copy2(src, data_dir / f"{name}.bak.{ts}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Recompute expansion_similarity for an event")
    parser.add_argument("--event-id", default=DEFAULT_EVENT_ID)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    settings = Settings()
    store = JsonStore(Path(settings.data_dir))
    if not args.dry_run:
        _backup(store.data_dir)
    results = asyncio.run(recompute_event(store, args.event_id.strip(), dry_run=args.dry_run))
    if results:
        logger.info("backfill done count=%d", len(results))
    else:
        logger.info("nothing to backfill")


if __name__ == "__main__":
    main()
