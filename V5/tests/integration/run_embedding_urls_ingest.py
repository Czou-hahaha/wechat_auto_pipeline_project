#!/usr/bin/env python3
"""
对固定 URL 列表：全文抓取 → 与 ``ingest_cluster`` 相同的向量转载合并 + 事件聚类 →
写入独立目录下的 ``articles.json`` / ``events.json`` / ``event_article_map.json``。

不调用大模型写簇摘要（避免依赖 API）；每条入库稿的 ``summary`` 为说明性占位文本，
结构与生产 ``PipelineRunner.run_once`` 落库一致，便于核对去重/聚类结果。

用法（在 ``V3/`` 目录）::

    python tests/integration/run_embedding_urls_ingest.py
    python tests/integration/run_embedding_urls_ingest.py --input tests/data/fixtures/beijing_drone_dedupe_test_input.json \\
        --data-dir tests/data/dedupe_runs/beijing
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

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
from src.storage import ArticleRecord, EventRecord, JsonStore

import importlib.util

_int_dir = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location(
    "_saved_dedupe_helpers",
    _int_dir / "run_saved_search_dedupe_report.py",
)
assert _spec and _spec.loader
_sdr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_sdr)


def _host(url: str) -> str:
    try:
        h = (urlparse(url).hostname or "").lower()
        if h.startswith("www."):
            h = h[4:]
        return h
    except Exception:
        return ""


def _pick_primary(cluster: list[PreparedArticle]) -> PreparedArticle:
    imp = [p for p in cluster if p.topic_is_important]
    pool = imp or cluster
    return sorted(pool, key=lambda p: p.source_published_at or "")[0]


def _stub_summary(cluster: list[PreparedArticle], primary: PreparedArticle) -> str:
    lines = [
        "【向量去重测试占位摘要，未调用大模型】",
        f"本事件簇共 {len(cluster)} 篇，代表稿：{primary.title}",
        "成员标题：",
    ]
    for i, p in enumerate(cluster, start=1):
        lines.append(f"  {i}. {p.title[:120]}")
    lines.append("")
    lines.append("代表稿正文开头：")
    lines.append((primary.text or "")[:1200])
    return "\n".join(lines)


def _render_ingest_md(
    *,
    input_path: Path,
    data_dir: Path,
    ok_rows: list[dict[str, Any]],
    fail_rows: list[dict[str, Any]],
    detail: Any | None,
    clusters: list[list[PreparedArticle]],
    reprint_dropped: int,
    articles_written: int,
) -> str:
    lines: list[str] = []
    lines.append("# 向量去重 + 事件聚类 + 测试落库\n")
    lines.append(f"- 时间（UTC）：`{datetime.now(timezone.utc).isoformat()}`")
    lines.append(f"- 输入：`{input_path}`")
    lines.append(f"- 落库目录：`{data_dir.resolve()}`")
    lines.append(f"- 抓取成功：**{len(ok_rows)}** 失败：**{len(fail_rows)}**")
    lines.append(f"- 转载合并去掉条数：**{reprint_dropped}**")
    lines.append(f"- 事件簇数：**{len(clusters)}**")
    lines.append(f"- 写入 ``ArticleRecord`` 条数：**{articles_written}**（每簇一条代表稿）\n")

    merges = list(getattr(detail, "reprint_merges", None) or [])
    edges = list(getattr(detail, "event_link_edges", None) or [])
    pairs_all = list(getattr(detail, "similarity_pairs", None) or [])

    lines.append("## 转载级合并（余弦 ≥ 阈值）\n")
    for i, m in enumerate(merges, start=1):
        lines.append(f"{i}. 去掉 `{m.get('dropped_url')}` → 保留 `{m.get('kept_url')}` （cos={m.get('cosine')}）")
    if not merges:
        lines.append("*无转载级合并。*")
    lines.append("")

    lines.append("## 事件簇（并查集事件边）\n")
    for ci, cl in enumerate(clusters):
        lines.append(f"### 簇 {ci}（{len(cl)} 篇 canonical）\n")
        for j, p in enumerate(cl, start=1):
            lines.append(f"{j}. {p.title[:100]}")
            lines.append(f"   - `{p.hit.url}`")
        lines.append("")

    lines.append("## 事件连边预览\n")
    for e in edges[:30]:
        lines.append(
            f"- cos={e.get('cosine')} `{e.get('url_a')}` ⟷ `{e.get('url_b')}`"
        )
    if not edges:
        lines.append("*无事件边。*")
    lines.append("")

    lines.append("## 高相似对（预览）\n")
    pairs = sorted(pairs_all, key=lambda x: float(x.get("cosine") or 0), reverse=True)[:25]
    for it in pairs:
        lines.append(f"- **{it.get('cosine')}** `{it.get('url_a')}` ⟷ `{it.get('url_b')}`")
    lines.append("")
    return "\n".join(lines)


async def main_async() -> int:
    ap = argparse.ArgumentParser(description="URL 列表 → 向量聚类 → 测试目录落库")
    ap.add_argument("--input", type=str, default="tests/data/fixtures/beijing_drone_dedupe_test_input.json")
    ap.add_argument(
        "--data-dir",
        type=str,
        default="tests/data/dedupe_runs/beijing",
        help="写入 articles/events/event_article_map 的目录（运行前会清空该目录下这三个文件）",
    )
    ap.add_argument("--concurrency", type=int, default=4)
    args = ap.parse_args()

    in_path = Path(args.input).expanduser()
    if not in_path.is_absolute():
        in_path = Path.cwd() / in_path
    data_dir = Path(args.data_dir).expanduser()
    if not data_dir.is_absolute():
        data_dir = Path.cwd() / data_dir

    if not in_path.is_file():
        logging.error("input not found: %s", in_path)
        return 2

    raw = in_path.read_text(encoding="utf-8")
    rows = json.loads(raw)
    if not isinstance(rows, list):
        logging.error("expected JSON array")
        return 2

    hits: list[SearchHit] = []
    for row in rows:
        if isinstance(row, dict):
            h = _sdr._row_to_hit(row)
            if h:
                hits.append(h)

    settings = Settings()
    report_settings = settings.model_copy(
        update={
            "embedding_cluster_enabled": True,
            "embedding_enabled": True,
        }
    )

    runner = PipelineRunner(settings)
    sem = asyncio.Semaphore(max(1, min(12, max(1, int(args.concurrency)))))
    t0 = perf_counter()
    fetched = await asyncio.gather(*[_sdr._fetch_one(runner, h, sem) for h in hits])
    logging.info("fetch done in %.2fs", perf_counter() - t0)

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

    data_dir.mkdir(parents=True, exist_ok=True)
    for name in ("articles.json", "events.json", "event_article_map.json"):
        p = data_dir / name
        if p.exists():
            p.unlink()
    store = JsonStore(data_dir)

    clusters: list[list[PreparedArticle]] = []
    detail = None
    reprint_dropped = 0

    if not prepared:
        logging.error("no successful fetches; skip clustering and ingest")
    else:
        out = await build_embedding_event_clusters_with_report(prepared, report_settings)
        if out is None:
            logging.error("embedding cluster returned None (check local model / deps)")
            clusters = [[p] for p in prepared]
            reprint_dropped = 0
        else:
            clusters, reprint_dropped, detail = out

        for cl in clusters:
            primary = _pick_primary(cl)
            event_id = str(uuid4())
            stub = _stub_summary(cl, primary)
            draft_title = primary.title
            unique_hosts = {p.source_host for p in cl if p.source_host}
            topic_src = len(unique_hosts)
            rec = ArticleRecord(
                id=str(uuid4()),
                title=draft_title,
                source_url=primary.hit.url,
                source_published_at=primary.source_published_at,
                source_published_at_date_only=primary.source_published_at_date_only,
                extracted_text=primary.text,
                summary=stub,
                status="dedupe_test_stub",
                created_at=datetime.now(timezone.utc).isoformat(),
                published_at="",
                resolved_url=primary.final_url,
                source_host=primary.source_host,
                topic_key=primary.topic_key,
                topic_category=primary.topic_category,
                topic_is_important=any(p.topic_is_important for p in cl),
                topic_source_count=topic_src,
                deepseek_semantic_decision="embedding_cluster_test",
                novelty_passed=True,
                wechat_draft_pushed_at="",
                cluster_size=len(cl),
                synthesis_multi_source=len(cl) > 1,
                event_id=event_id,
                summary_zh="",
            )
            store.add(rec)
            store.append_event(
                EventRecord(
                    id=event_id,
                    title=draft_title,
                    summary=stub,
                    summary_zh="",
                    dominant_topic_key=primary.topic_key,
                    created_at=datetime.now(timezone.utc).isoformat(),
                )
            )
            store.append_event_article_map(
                [
                    {
                        "event_id": event_id,
                        "source_url": p.hit.url,
                        "resolved_url": p.final_url or "",
                        "role": "primary" if p is primary else "source",
                    }
                    for p in cl
                ]
            )

    md = _render_ingest_md(
        input_path=in_path,
        data_dir=data_dir,
        ok_rows=ok_rows,
        fail_rows=fail_rows,
        detail=detail,
        clusters=clusters,
        reprint_dropped=reprint_dropped,
        articles_written=len(clusters),
    )
    md_path = data_dir / "dedupe_ingest_result.md"
    md_path.write_text(md, encoding="utf-8")
    json_path = data_dir / "dedupe_ingest_detail.json"
    detail_dict = detail.as_dict() if detail is not None else {}
    json_path.write_text(
        json.dumps(
            {
                "input": str(in_path),
                "data_dir": str(data_dir.resolve()),
                "fetch_ok": len(ok_rows),
                "fetch_fail": len(fail_rows),
                "failures": fail_rows,
                "reprint_dropped": reprint_dropped,
                "event_cluster_count": len(clusters),
                "cluster_report": detail_dict,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    logging.info("wrote %s", md_path)
    logging.info("wrote %s", json_path)
    print("\n" + "=" * 72 + "\n" + md + "\n" + "=" * 72 + "\n")
    return 0 if ok_rows else 1


def main() -> None:
    raise SystemExit(asyncio.run(main_async()))


if __name__ == "__main__":
    main()
