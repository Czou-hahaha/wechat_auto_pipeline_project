#!/usr/bin/env python3
"""
对已落盘的搜索测试结果 JSON 做：全文拉取 →（可选）向量转载合并 + 同事件聚类，输出结构化报告。

默认读 ``tests/data/search/test_search_results.json``（与 ``run_search_flow`` 输出格式一致），写入
``tests/data/search/dedupe_report_from_saved_search.json``，并额外写 **Markdown 阅读摘要**
``tests/data/search/dedupe_report_from_saved_search_阅读摘要.md``（与 ``--output`` 同主文件名加 ``_阅读摘要``）。

本机向量（``EMBEDDING_BACKEND=local``，默认 ``BAAI/bge-m3``）**无需** ``EMBEDDING_API_KEY``；若
``EMBEDDING_BACKEND=http`` 则需配置 KEY。本脚本会临时打开 ``EMBEDDING_CLUSTER_ENABLED`` 仅用于本次报告。

用法（在 ``V3/`` 目录）::

    python tests/integration/run_saved_search_dedupe_report.py
    python tests/integration/run_saved_search_dedupe_report.py --input tests/data/search/test_search_results.json --output tests/data/search/my_dedupe_report.json
    python tests/integration/run_saved_search_dedupe_report.py --summary-out tests/data/search/my_摘要.md --no-print-summary
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from time import perf_counter
from typing import Any
from urllib.parse import urlparse

_V3_ROOT = Path(__file__).resolve().parents[2]
if str(_V3_ROOT) not in sys.path:
    sys.path.insert(0, str(_V3_ROOT))

os.environ.setdefault("LOG_LEVEL", "INFO")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-5s %(name)s - %(message)s",
)
logging.getLogger("httpx").setLevel(logging.WARNING)

from src.config import Settings
from src.ingest_cluster import build_embedding_event_clusters_with_report
from src.pipeline import PipelineRunner, PreparedArticle
from src.search import SearchHit
from src.storage import JsonStore


def _host(url: str) -> str:
    try:
        h = (urlparse(url).hostname or "").lower()
        if h.startswith("www."):
            h = h[4:]
        return h
    except Exception:
        return ""


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
                "published_at": hit.published_at,
                "ok": False,
                "error": f"{type(exc).__name__}: {exc}"[:500],
                "elapsed_sec": round(perf_counter() - t0, 3),
            }
    return {
        "url": hit.url,
        "title": title,
        "published_at": hit.published_at,
        "page_published_at": page_published_at,
        "page_date_only": page_date_only,
        "final_url": final_url,
        "text_chars": len(text or ""),
        "text_preview": (text or "")[:500],
        "ok": True,
        "elapsed_sec": round(perf_counter() - t0, 3),
        "first_image_url": first_image_url or "",
        "_text_full": text or "",
    }


def _row_to_hit(row: dict[str, Any]) -> SearchHit | None:
    url = str(row.get("url") or "").strip()
    if not url:
        return None
    return SearchHit(
        title=str(row.get("title") or ""),
        url=url,
        snippet=str(row.get("snippet") or ""),
        published_at=str(row.get("published_at") or ""),
        from_rss=bool(row.get("from_rss", False)),
    )


def legacy_batch_pair_preview(ok_rows: list[dict[str, Any]], *, body_ratio: float = 0.88) -> list[dict[str, Any]]:
    """
    无向量时的本批两两预览：与 ``PipelineRunner._prepared_near_duplicate`` 同口径的标题/正文近重复。
    仅用于报告，不入库。
    """
    out: list[dict[str, Any]] = []
    n = len(ok_rows)
    for i in range(n):
        for j in range(i + 1, n):
            a, b = ok_rows[i], ok_rows[j]
            ua, ub = str(a.get("url") or ""), str(b.get("url") or "")
            ta = JsonStore._norm_text(str(a.get("title") or ""))
            tb = JsonStore._norm_text(str(b.get("title") or ""))
            if ta and tb and JsonStore.titles_duplicated(ta, tb):
                out.append(
                    {
                        "kind": "title_duplicate",
                        "url_a": ua,
                        "url_b": ub,
                        "title_a": (str(a.get("title") or ""))[:160],
                        "title_b": (str(b.get("title") or ""))[:160],
                    }
                )
                continue
            xa = JsonStore._norm_text(str(a.get("_text_full") or ""))[:3000]
            xb = JsonStore._norm_text(str(b.get("_text_full") or ""))[:3000]
            if len(xa) >= 200 and len(xb) >= 200:
                r = SequenceMatcher(None, xa, xb).ratio()
                if r >= body_ratio:
                    out.append(
                        {
                            "kind": "body_high_similarity",
                            "sequence_ratio": round(r, 4),
                            "url_a": ua,
                            "url_b": ub,
                            "title_a": (str(a.get("title") or ""))[:120],
                            "title_b": (str(b.get("title") or ""))[:120],
                        }
                    )
    return out


def render_human_summary(report: dict[str, Any]) -> str:
    """生成给人看的 Markdown，便于核对「是否去重、谁和谁并在一起」。"""
    lines: list[str] = []
    meta = report.get("meta") or {}
    lines.append("# 搜索存档 → 抓取 → 向量去重 / 事件聚类 — 阅读摘要\n")
    lines.append(f"- 生成时间（UTC）：`{meta.get('generated_at', '')}`")
    lines.append(f"- 输入文件：`{meta.get('input_path', '')}`")
    lines.append(f"- 输入条数：**{meta.get('input_hits', 0)}**")
    lines.append(f"- 全文抓取成功：**{meta.get('fetch_ok', 0)}**  失败：**{meta.get('fetch_fail', 0)}**")
    lines.append(f"- 向量后端：**{meta.get('embedding_backend', '')}**  模型：`{meta.get('embedding_model', '')}`\n")

    lines.append("## 1. 抓取成功条目（去重前）\n")
    lines.append("| # | 标题（截断） | URL | 正文字数 |")
    lines.append("|---|--------------|-----|----------|")
    for i, row in enumerate(report.get("fetch_success") or [], start=1):
        t = str(row.get("title") or "")[:60].replace("|", "\\|")
        u = str(row.get("url") or "")
        tc = row.get("text_chars", "")
        lines.append(f"| {i} | {t} | {u} | {tc} |")
    lines.append("")

    dc = report.get("dedupe_and_cluster") or {}
    mode = dc.get("mode", "none")
    lines.append("## 2. 向量去重 / 事件聚类结果\n")
    lines.append(f"- **模式**：`{mode}`")
    if dc.get("reason"):
        lines.append(f"- **说明**：{dc.get('reason')}")
    if mode == "embedding_reprint_plus_event":
        lines.append(f"- **向量耗时（秒）**：{dc.get('embedding_elapsed_sec', '')}")
        rep_thr = (dc.get("report") or {}).get("reprint_threshold", "")
        lines.append(f"- **转载合并去掉条数**（余弦 ≥ {rep_thr}）：**{dc.get('reprint_dropped_count', 0)}**")
        lines.append(f"- **事件簇个数**：**{dc.get('event_cluster_count', 0)}**")
        lines.append("")

        rm = (dc.get("report") or {}).get("reprint_merges") or []
        lines.append("### 2.1 转载级去重（被去掉的 URL → 保留的 canonical）\n")
        if not rm:
            lines.append("*本批没有出现「转载级」合并（没有两条同时达到转载余弦阈值）。*\n")
        else:
            for k, it in enumerate(rm, start=1):
                lines.append(f"{k}. **去掉** `{it.get('dropped_url', '')}`")
                lines.append(f"   - **并入** `{it.get('kept_url', '')}`  （余弦 {it.get('cosine')}）")
                lines.append(f"   - 去掉稿标题：{str(it.get('dropped_title', ''))[:120]}")
            lines.append("")

        evh = dc.get("events_human") or []
        lines.append("### 2.2 事件簇（每簇 = 同一事件；簇内多篇会进同一 `summarize_cluster`）\n")
        for ev in evh:
            idx = ev.get("event_index", 0)
            urls = ev.get("urls") or []
            titles = ev.get("titles") or []
            lines.append(f"**事件 {idx}**（{len(urls)} 篇）")
            for j, u in enumerate(urls):
                tit = titles[j] if j < len(titles) else ""
                lines.append(f"- {j + 1}. {tit}")
                lines.append(f"  - `{u}`")
            lines.append("")

        pairs = (dc.get("report") or {}).get("similarity_pairs") or []
        if pairs:
            lines.append("### 2.3 高相似对 Top20（仅预览；未达转载阈值则不会合并）\n")
            sp = sorted(pairs, key=lambda x: float(x.get("cosine") or 0), reverse=True)[:20]
            for it in sp:
                lines.append(
                    f"- **{it.get('cosine')}**  `{it.get('url_a', '')}` ⟷ `{it.get('url_b', '')}`"
                )
            lines.append("")

    ob = dc.get("offline_batch_preview") or {}
    op = ob.get("pairs") or []
    lines.append("## 3. 无向量时的正文/标题近重复预览（SequenceMatcher）\n")
    if not op:
        lines.append("*无命中对。*\n")
    else:
        for it in op:
            lines.append(f"- **{it.get('kind')}** `{it.get('url_a')}` ⟷ `{it.get('url_b')}`")
            if it.get("sequence_ratio") is not None:
                lines.append(f"  - 比例：{it.get('sequence_ratio')}")
        lines.append("")

    lines.append("## 4. 原始机器报告\n")
    lines.append(f"完整 JSON：`{meta.get('output_path', '')}`\n")
    return "\n".join(lines)


async def main_async() -> int:
    ap = argparse.ArgumentParser(description="Saved search JSON → fetch → embedding dedupe report")
    ap.add_argument("--input", type=str, default="tests/data/search/test_search_results.json")
    ap.add_argument("--output", type=str, default="tests/data/search/dedupe_report_from_saved_search.json")
    ap.add_argument(
        "--summary-out",
        type=str,
        default="",
        help="人类可读 Markdown 摘要路径；默认与 --output 同主文件名加 _阅读摘要.md",
    )
    ap.add_argument("--no-print-summary", action="store_true", help="不在终端打印摘要（仍会写入摘要文件）")
    ap.add_argument("--concurrency", type=int, default=4)
    args = ap.parse_args()

    in_path = Path(args.input).expanduser()
    if not in_path.is_absolute():
        in_path = Path.cwd() / in_path
    out_path = Path(args.output).expanduser()
    if not out_path.is_absolute():
        out_path = Path.cwd() / out_path

    if not in_path.is_file():
        logging.error("input not found: %s", in_path)
        return 2

    raw = in_path.read_text(encoding="utf-8")
    try:
        rows = json.loads(raw)
    except json.JSONDecodeError as e:
        logging.error("invalid JSON in %s: %s", in_path, e)
        return 2
    if not isinstance(rows, list):
        logging.error("expected JSON array in %s", in_path)
        return 2

    hits: list[SearchHit] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        h = _row_to_hit(row)
        if h:
            hits.append(h)

    settings = Settings()
    embed_key = (settings.embedding_api_key or "").strip()
    backend = (settings.embedding_backend or "local").strip().lower()
    # 报告脚本：默认打开聚类 + 向量（本机 bge-m3 免 KEY；http 模式仍依赖 KEY）
    report_settings = settings.model_copy(
        update={
            "embedding_cluster_enabled": True,
            "embedding_enabled": True,
        }
    )

    runner = PipelineRunner(settings)
    sem = asyncio.Semaphore(max(1, min(12, max(1, int(args.concurrency)))))
    t_fetch = perf_counter()
    fetched = await asyncio.gather(*[_fetch_one(runner, h, sem) for h in hits])
    fetch_elapsed = round(perf_counter() - t_fetch, 2)

    ok_rows = [r for r in fetched if r.get("ok")]
    fail_rows = [r for r in fetched if not r.get("ok")]

    prepared: list[PreparedArticle] = []
    for r in ok_rows:
        hit = SearchHit(
            title=str(r.get("title") or ""),
            url=str(r.get("url") or ""),
            snippet="",
            published_at=str(r.get("page_published_at") or r.get("published_at") or ""),
            from_rss=True,
        )
        fu = str(r.get("final_url") or hit.url)
        prepared.append(
            PreparedArticle(
                hit=hit,
                title=str(r.get("title") or ""),
                text=str(r.get("_text_full") or ""),
                final_url=fu,
                first_image_url=str(r.get("first_image_url") or "") or None,
                source_host=_host(fu),
                source_published_at=str(r.get("page_published_at") or r.get("published_at") or ""),
                source_published_at_date_only=bool(r.get("page_date_only", False)),
                topic_is_important=False,
                topic_category="other",
                topic_key="",
                deepseek_semantic_decision="",
                novelty_passed=True,
            )
        )

    cluster_block: dict[str, Any] = {
        "mode": "none",
        "reason": "",
        "embedding_backend": backend,
        "embedding_model": (settings.embedding_model or "").strip(),
        "embedding_cluster_enabled_effective": bool(report_settings.embedding_cluster_enabled),
        "embedding_api_configured": bool(embed_key),
    }

    if report_settings.embedding_cluster_enabled and prepared:
        t_emb = perf_counter()
        out = await build_embedding_event_clusters_with_report(prepared, report_settings)
        cluster_block["embedding_elapsed_sec"] = round(perf_counter() - t_emb, 2)
        if out is None:
            cluster_block["reason"] = (
                "embedding_cluster returned None (local: pip install sentence-transformers 且需首次联网下模型；"
                "http: 检查 EMBEDDING_API_KEY/BASE_URL/MODEL 或网络错误)"
            )
        else:
            clusters, dropped, detail = out
            cluster_block["mode"] = "embedding_reprint_plus_event"
            cluster_block["reprint_dropped_count"] = dropped
            cluster_block["event_cluster_count"] = len(clusters)
            cluster_block["report"] = detail.as_dict()
            cluster_block["events_human"] = [
                {
                    "event_index": i,
                    "urls": [_article_url_dict(p) for p in cl],
                    "titles": [(_article_title_dict(p) or "")[:100] for p in cl],
                }
                for i, cl in enumerate(clusters)
            ]
    elif not prepared:
        cluster_block["reason"] = "无成功抓取的正文条目，跳过向量聚类"
    elif backend == "http" and not embed_key:
        cluster_block["reason"] = "EMBEDDING_BACKEND=http 但 EMBEDDING_API_KEY 为空 — 已跳过向量聚类"
    elif not report_settings.embedding_enabled:
        cluster_block["reason"] = "EMBEDDING_ENABLED 为 false — 已跳过向量聚类"

    cluster_block["offline_batch_preview"] = {
        "description": "无向量时的本批两两检测（标题重复或正文前3000字规范化后 SequenceMatcher 比例）",
        "body_ratio_threshold": 0.88,
        "pairs": legacy_batch_pair_preview(ok_rows),
    }

    report: dict[str, Any] = {
        "meta": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "input_path": str(in_path),
            "output_path": str(out_path),
            "input_hits": len(hits),
            "fetch_ok": len(ok_rows),
            "fetch_fail": len(fail_rows),
            "fetch_elapsed_sec": fetch_elapsed,
            "trafilatura_enabled": bool(settings.trafilatura_enabled),
            "embedding_backend": backend,
            "embedding_model": (settings.embedding_model or "").strip(),
            "note": "默认本机向量：EMBEDDING_BACKEND=local + BAAI/bge-m3，无需 API KEY；远程 OpenAI 兼容接口请设 EMBEDDING_BACKEND=http 并配置 KEY。",
        },
        "fetch_failures": fail_rows,
        "fetch_success": [
            {
                "url": r.get("url"),
                "title": r.get("title"),
                "final_url": r.get("final_url"),
                "published_at": r.get("published_at"),
                "page_published_at": r.get("page_published_at"),
                "text_chars": r.get("text_chars"),
                "text_preview": r.get("text_preview"),
                "elapsed_sec": r.get("elapsed_sec"),
            }
            for r in ok_rows
        ],
        "dedupe_and_cluster": cluster_block,
    }

    summary_path = Path(args.summary_out).expanduser() if (args.summary_out or "").strip() else None
    if summary_path is None:
        summary_path = out_path.with_name(out_path.stem + "_阅读摘要.md")
    elif not summary_path.is_absolute():
        summary_path = Path.cwd() / summary_path

    report["meta"]["summary_markdown_path"] = str(summary_path)
    summary_md = render_human_summary(report)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    summary_path.write_text(summary_md, encoding="utf-8")
    logging.info("wrote %s", out_path)
    logging.info("wrote human summary %s", summary_path)
    if not args.no_print_summary:
        print("\n" + "=" * 72 + "\n" + summary_md + "\n" + "=" * 72 + "\n")
    return 0


def _article_url_dict(p: PreparedArticle) -> str:
    return p.hit.url


def _article_title_dict(p: PreparedArticle) -> str:
    return p.title


def main() -> None:
    raise SystemExit(asyncio.run(main_async()))


if __name__ == "__main__":
    main()
