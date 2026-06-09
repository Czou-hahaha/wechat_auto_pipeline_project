#!/usr/bin/env python3
"""上线验收冒烟：不跑完整 run_once，检查配置与 BFF 契约。"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.config import Settings  # noqa: E402
from src.bff.enhancement_loader import load_enhancement_runs_by_event  # noqa: E402
from src.storage import JsonStore  # noqa: E402


def _get(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=5) as resp:
        return json.loads(resp.read().decode())


def main() -> int:
    s = Settings()
    store = JsonStore(Path(s.data_dir))
    rows: list[tuple[str, bool, str]] = []

    def check(name: str, ok: bool, detail: str) -> None:
        rows.append((name, ok, detail))

    # 1 配置
    check(
        "EMBEDDING_ENABLED",
        bool(s.embedding_enabled),
        f"embedding_enabled={s.embedding_enabled}",
    )
    check(
        "EMBEDDING_CLUSTER_ENABLED",
        bool(s.embedding_cluster_enabled),
        f"embedding_cluster_enabled={s.embedding_cluster_enabled}",
    )
    check(
        "EVENT_AI_PRESS",
        bool(s.event_ai_press_enabled),
        f"event_ai_press_enabled={s.event_ai_press_enabled}",
    )
    check(
        "QA_REWRITE",
        bool(getattr(s, "qa_rewrite_enabled", False)),
        f"qa_rewrite_enabled={getattr(s, 'qa_rewrite_enabled', False)}",
    )

    # 2 数据
    events = store.list_events()
    articles = store.list_all()
    check("events.json", len(events) > 0, f"events={len(events)}")
    check("articles.json", len(articles) > 0, f"articles={len(articles)}")
    enh_idx = load_enhancement_runs_by_event(Path(s.data_dir))
    check(
        "event_enhancement_last_run",
        len(enh_idx) > 0,
        f"enhancement_log_events={len(enh_idx)}",
    )

    # 3 BFF（V6 默认 8788）
    port = int(getattr(s, "bff_port", None) or 8788)
    bff = f"http://127.0.0.1:{port}"
    try:
        health = _get(f"{bff}/health")
        check("BFF /health", health.get("status") == "ok", str(health))
        lst = _get(f"{bff}/api/events")
        check(
            "BFF /api/events",
            isinstance(lst.get("items"), list),
            f"total={lst.get('total')} (V6 列表仅含主稿事件)",
        )
        eid = ""
        for row in articles:
            if isinstance(row, dict):
                eid = str(row.get("event_id") or "").strip()
                if eid:
                    break
        if not eid and events:
            eid = str(events[0].get("id") or "")
        if eid:
            detail = _get(f"{bff}/api/events/{eid}")
            enh = detail.get("enhancement") or {}
            art_rows = detail.get("articles") or []
            has_kind = any(a.get("sourceKind") for a in art_rows)
            check(
                "BFF enhancement DTO",
                bool(enh.get("ran")) or enh.get("status") == "not_run",
                f"ran={enh.get('ran')} expansion={detail.get('expansion_article_count')}",
            )
            if art_rows:
                check("BFF article sourceKind", has_kind, f"articles={len(art_rows)}")
            else:
                check("BFF article sourceKind SKIP", True, "event 无关联稿")
            graph = _get(f"{bff}/api/events/{eid}/graph")
            check(
                "BFF event graph",
                graph.get("eventId") == eid,
                f"nodes={len((graph.get('eventGraph') or {}).get('nodes') or [])}",
            )
        dash = _get(f"{bff}/api/dashboard")
        trend = dash.get("topicTrend") or []
        fake_faa = any(isinstance(r, dict) and "FAA" in r for r in trend)
        check("Dashboard topicTrend 非占位 FAA", not fake_faa, f"rows={len(trend)}")
    except urllib.error.URLError as e:
        check("BFF reachable", False, str(e))

    failed = [r for r in rows if not r[1]]
    print("\n=== 上线验收冒烟 ===\n")
    for name, ok, detail in rows:
        mark = "PASS" if ok else "FAIL"
        print(f"[{mark}] {name}: {detail}")
    print(f"\n合计 {len(rows) - len(failed)}/{len(rows)} 通过")
    if failed:
        print("\n未通过项需处理后再跑完整 run-once E2E。")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
