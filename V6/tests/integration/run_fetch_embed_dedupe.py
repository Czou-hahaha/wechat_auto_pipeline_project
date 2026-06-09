#!/usr/bin/env python3
"""
检索 → ``MAX_ARTICLE_AGE_HOURS`` 时间窗 → 全文拉取 →（可选）embedding 去重，输出报告 JSON。

与 ``run_once`` 一致：候选集先 ``filter_by_age(..., settings.max_article_age_hours)``，
即「历史窗口」由环境变量 ``MAX_ARTICLE_AGE_HOURS`` 控制（常见为 12 或 14），非写死 12。

用法（在 ``V3/`` 目录）::

    python tests/integration/run_fetch_embed_dedupe.py --max-fetch 30

需向量去重时配置 ``.env``：``EMBEDDING_ENABLED=true``；本机免 KEY 时 ``EMBEDDING_BACKEND=local``（默认 ``BAAI/bge-m3``，见 ``requirements.txt`` 的 ``sentence-transformers``）；远程接口设 ``EMBEDDING_BACKEND=http`` 并配 ``EMBEDDING_API_KEY``。
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from pathlib import Path
from time import perf_counter
from typing import Any

_V3_ROOT = Path(__file__).resolve().parents[2]
if str(_V3_ROOT) not in sys.path:
    sys.path.insert(0, str(_V3_ROOT))

os.environ.setdefault("LOG_LEVEL", "INFO")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-5s %(name)s - %(message)s",
)
logging.getLogger("httpx").setLevel(logging.WARNING)

import httpx

from src.config import Settings
from src.embed_dedupe import dedupe_by_embedding_greedy, fetch_embeddings_batch, truncate_for_embedding
from src.pipeline import PipelineRunner
from src.rss_aggregate import aggregate_rss_from_data_sources
from src.search import SearchHit, filter_by_age, merge_search_hits, search_gdelt_topics_bilingual


async def _fetch_one(
    runner: PipelineRunner,
    hit: SearchHit,
    sem: asyncio.Semaphore,
) -> dict[str, Any]:
    async with sem:
        t0 = perf_counter()
        try:
            title, text, first_image_url, final_url, page_published_at, page_date_only = await runner._fetch_text(
                hit.url,
                fallback_title=hit.title,
                fallback_snippet=hit.snippet,
            )
        except Exception as exc:
            return {
                "url": hit.url,
                "title": hit.title,
                "search_published_at": hit.published_at,
                "ok": False,
                "error": f"{type(exc).__name__}: {exc}"[:400],
                "elapsed_sec": round(perf_counter() - t0, 3),
            }
    return {
        "url": hit.url,
        "title": title,
        "search_published_at": hit.published_at,
        "page_published_at": page_published_at,
        "page_date_only": page_date_only,
        "final_url": final_url,
        "text_chars": len(text or ""),
        "text_preview": (text or "")[:400],
        "ok": True,
        "elapsed_sec": round(perf_counter() - t0, 3),
        "_text_full": text or "",
        "first_image_url": first_image_url or "",
    }


async def main_async() -> int:
    ap = argparse.ArgumentParser(description="Search → age window → full fetch → optional embedding dedupe")
    ap.add_argument("--max-fetch", type=int, default=35, help="最多全文拉取条数（避免一次跑过多外站）")
    args = ap.parse_args()

    s = Settings()
    window_h = s.max_article_age_hours
    t_search = perf_counter()
    rss_hits = await aggregate_rss_from_data_sources(s)
    gdelt_hits, gdelt_http = await search_gdelt_topics_bilingual(s)
    merged = merge_search_hits(rss_hits, gdelt_hits, max_total=1500)
    unique: dict[str, SearchHit] = {}
    for h in merged:
        key = PipelineRunner._canonical_url(h.url)
        if key and key not in unique:
            unique[key] = h
    aged = filter_by_age(list(unique.values()), window_h)
    candidates = aged[: max(1, args.max_fetch)]

    report: dict[str, Any] = {
        "max_article_age_hours": window_h,
        "note_age_window": "与 run_once 相同：filter_by_age(..., MAX_ARTICLE_AGE_HOURS)；无 published_at 或不可解析者不进候选。",
        "rss_raw": len(rss_hits),
        "gdelt_rows": len(gdelt_hits),
        "gdelt_http_requests": gdelt_http,
        "merged_unique": len(unique),
        "after_age_filter": len(aged),
        "fetch_cap": len(candidates),
        "search_elapsed_sec": round(perf_counter() - t_search, 2),
        "embedding_enabled": bool(s.embedding_enabled),
        "embedding_backend": (s.embedding_backend or "local").strip().lower(),
        "embedding_model": s.embedding_model,
        "embedding_dedupe_threshold": s.embedding_dedupe_threshold,
    }

    runner = PipelineRunner(s)
    sem = asyncio.Semaphore(4)
    t_fetch = perf_counter()
    fetched = await asyncio.gather(*[_fetch_one(runner, h, sem) for h in candidates])
    report["fetch_elapsed_sec"] = round(perf_counter() - t_fetch, 2)
    ok_rows = [r for r in fetched if r.get("ok")]
    report["fetch_ok"] = len(ok_rows)
    report["fetch_failed"] = len(fetched) - len(ok_rows)

    backend = (s.embedding_backend or "local").strip().lower()
    embed_active = bool(
        s.embedding_enabled
        and (backend == "local" or (backend == "http" and (s.embedding_api_key or "").strip()))
    )
    embeddings: list[list[float] | None] = [None for _ in ok_rows]
    if embed_active and ok_rows:
        inputs = [
            truncate_for_embedding(
                f"{(r.get('title') or '')}\n{(r.get('_text_full') or '')}",
                s.embedding_max_input_chars,
            )
            for r in ok_rows
        ]
        bs = max(1, int(s.embedding_batch_size))
        t_emb = perf_counter()
        async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as client:
            pos = 0
            while pos < len(inputs):
                chunk = inputs[pos : pos + bs]
                sub_client = client if backend == "http" else None
                part = await fetch_embeddings_batch(
                    settings=s,
                    inputs=chunk,
                    client=sub_client,
                )
                for j, vec in enumerate(part):
                    if pos + j < len(embeddings):
                        embeddings[pos + j] = vec
                pos += bs
        report["embedding_elapsed_sec"] = round(perf_counter() - t_emb, 2)
        report["embedding_none_count"] = sum(1 for e in embeddings if e is None)
        kept_idx, dropped_pairs = dedupe_by_embedding_greedy(
            embeddings,
            threshold=float(s.embedding_dedupe_threshold),
        )
        report["after_embedding_dedupe"] = len(kept_idx)
        report["embedding_dropped_pairs"] = [
            {"drop": ok_rows[i]["url"], "keep": ok_rows[j]["url"], "cosine": sim} for i, j, sim in dropped_pairs
        ]
        kept_set = set(kept_idx)
        ok_rows = [ok_rows[i] for i in range(len(ok_rows)) if i in kept_set]
    else:
        report["after_embedding_dedupe"] = len(ok_rows)
        report["embedding_dropped_pairs"] = []
        if not embed_active:
            report["embedding_skip_reason"] = (
                "EMBEDDING_ENABLED=false，或 EMBEDDING_BACKEND=http 但未配置 EMBEDDING_API_KEY — 仅全文拉取，未做向量去重。"
            )

    for r in ok_rows:
        r.pop("_text_full", None)

    report["articles"] = ok_rows + [r for r in fetched if not r.get("ok")]
    out_path = os.environ.get("FETCH_EMBED_DEDUPE_OUT", "tests/data/search/fetch_embed_dedupe_report.json")
    os.makedirs(str(Path(out_path).parent), exist_ok=True)
    Path(out_path).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    logging.getLogger("test_fetch_embed_dedupe").info("report written %s", out_path)
    print(json.dumps({k: report[k] for k in report if k != "articles"}, ensure_ascii=False, indent=2))
    print(f"\n全文条目数: {len(report['articles'])}  报告: {out_path}")
    return 0


def main() -> None:
    raise SystemExit(asyncio.run(main_async()))


if __name__ == "__main__":
    main()
