#!/usr/bin/env python3
"""Platform 前端按钮 → API 端到端验收（经 Next :3000 代理到 BFF）。

用法:
  cd V3 && python scripts/platform_frontend_e2e.py
  python scripts/platform_frontend_e2e.py --skip-mutations
  python scripts/platform_frontend_e2e.py --test-wechat-push
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

PLATFORM_BASE = os.environ.get("PLATFORM_BASE", "http://127.0.0.1:3000").rstrip("/")
BFF_BASE = os.environ.get("BFF_BASE", "http://127.0.0.1:8787").rstrip("/")

UI_MATRIX: list[tuple[str, str, str, str]] = [
    ("导航", "Dashboard", "GET", "/api/dashboard"),
    ("导航", "Events 列表", "GET", "/api/events"),
    ("导航", "Search 检索", "GET", "/api/search?q=..."),
    ("导航", "QA Review", "GET", "/api/qa"),
    ("导航", "采集配置", "GET/PUT", "/api/config/*"),
    ("Dashboard", "开始采集搜索", "POST", "/api/pipeline/run-once"),
    ("Dashboard", "采集状态轮询", "GET", "/api/pipeline/status"),
    ("Events", "筛选/排序", "GET", "/api/events?sort=&keyword=&minImportance="),
    ("Events", "分段 Tab", "—", "前端 tags 筛选"),
    ("Events", "分页", "—", "前端 slice"),
    ("Search", "搜索", "GET", "/api/search?q=..."),
    ("QA", "分数滑块", "—", "前端 filter"),
    ("事件详情", "保存通稿", "PUT", "/api/events/{id}/press"),
    ("事件详情", "推送草稿箱", "POST", "/api/events/{id}/push-draft"),
    ("事件详情", "标记草稿已推", "POST", "/api/events/{id}/mark-draft-pushed"),
    ("设置", "保存配置", "PUT", "/api/config/data-sources|keywords|schedule"),
]


class Checker:
    def __init__(self) -> None:
        self.rows: list[tuple[str, bool, str]] = []

    def ok(self, name: str, detail: str = "ok") -> None:
        self.rows.append((name, True, detail))

    def fail(self, name: str, detail: str) -> None:
        self.rows.append((name, False, detail))

    def http(
        self,
        name: str,
        method: str,
        url: str,
        *,
        body: dict | list | None = None,
        expect: int | tuple[int, ...] = 200,
    ) -> dict[str, Any] | None:
        data = None
        if body is not None:
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            method=method.upper(),
            headers={"Content-Type": "application/json"} if data else {},
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read().decode()
                code = resp.status
                parsed = json.loads(raw) if raw.strip() else {}
        except urllib.error.HTTPError as e:
            code = e.code
            try:
                parsed = json.loads(e.read().decode())
            except Exception:
                parsed = {"detail": str(e)}
        except urllib.error.URLError as e:
            self.fail(name, f"unreachable: {e}")
            return None

        expected = (expect,) if isinstance(expect, int) else expect
        if code not in expected:
            detail = parsed.get("detail") if isinstance(parsed, dict) else parsed
            self.fail(name, f"HTTP {code} expected {expected}: {detail}")
            return parsed if isinstance(parsed, dict) else None
        self.ok(name, f"HTTP {code}")
        return parsed if isinstance(parsed, dict) else {}


def _pick_event(items: list[dict]) -> dict | None:
    for pref in ("可推送", "草稿已推", "待扩搜"):
        for row in items:
            if pref in (row.get("tags") or []):
                return row
    return items[0] if items else None


def execute(c: Checker, skip_mutations: bool, test_wechat_push: bool) -> int:
    c.http("BFF /health", "GET", f"{BFF_BASE}/health")
    plat = c.http("Platform /api/health", "GET", f"{PLATFORM_BASE}/api/health")
    if plat and not plat.get("connected"):
        c.fail("Platform→BFF 代理", str(plat))
    elif plat:
        c.ok("Platform→BFF 代理", str(plat.get("service") or "connected"))

    base = PLATFORM_BASE
    dash = c.http("Dashboard 数据", "GET", f"{base}/api/dashboard")
    if dash:
        for key in (
            "todayNewEvents",
            "totalEvents",
            "topicTrend",
            "highImportanceEvents",
            "hotKeywords",
        ):
            if key not in dash:
                c.fail(f"Dashboard 字段 {key}", "missing")

    c.http("采集状态", "GET", f"{base}/api/pipeline/status")
    if not skip_mutations:
        c.http(
            "开始采集搜索 (POST)",
            "POST",
            f"{base}/api/pipeline/run-once",
            expect=(200, 409),
        )

    lst = c.http("Events 列表", "GET", f"{base}/api/events?sort=importance")
    kw_q = urllib.parse.urlencode({"keyword": "无人机"})
    c.http("Events 关键词筛选", "GET", f"{base}/api/events?{kw_q}")
    c.http("Events QA 排序", "GET", f"{base}/api/events?sort=qa")
    c.http("Events 重要性阈值", "GET", f"{base}/api/events?minImportance=20")

    items = (lst or {}).get("items") or []
    if not items:
        c.fail("Events 非空", "items=0，请先采集或恢复 demo")
        event_id = ""
    else:
        c.ok("Events 非空", f"total={len(items)}")
        pick = _pick_event(items)
        event_id = str((pick or items[0]).get("id") or "")

    c.http(
        "Search 检索",
        "GET",
        f"{base}/api/search?{urllib.parse.urlencode({'q': 'eVTOL'})}",
    )
    c.http("QA 列表", "GET", f"{base}/api/qa?min_score=0&max_score=100")

    ds = c.http("配置·数据源 GET", "GET", f"{base}/api/config/data-sources")
    kw = c.http("配置·关键词 GET", "GET", f"{base}/api/config/keywords")
    sch = c.http("配置·定时 GET", "GET", f"{base}/api/config/schedule")

    if skip_mutations:
        if event_id:
            c.http("事件详情 GET", "GET", f"{base}/api/events/{event_id}")
        return 1 if any(not r[1] for r in c.rows) else 0

    if ds and isinstance(ds.get("items"), list):
        c.http("配置·数据源 PUT 回写", "PUT", f"{base}/api/config/data-sources", body=ds["items"])
    if kw and isinstance(kw.get("data"), dict):
        c.http("配置·关键词 PUT 回写", "PUT", f"{base}/api/config/keywords", body=kw["data"])
    if sch:
        c.http(
            "配置·定时 PUT 回写",
            "PUT",
            f"{base}/api/config/schedule",
            body={
                "enabled": sch.get("enabled", False),
                "timezone": sch.get("timezone", "Asia/Shanghai"),
                "jobs": sch.get("jobs") or [],
                "article_age": sch.get("article_age") or {"unit": "hours", "value": 14},
                "article_age_limit_enabled": sch.get("article_age_limit_enabled", True),
            },
        )

    if not event_id:
        return 1 if any(not r[1] for r in c.rows) else 0

    detail = c.http("事件详情 GET", "GET", f"{base}/api/events/{event_id}")
    if not detail:
        return 1 if any(not r[1] for r in c.rows) else 0

    title = str(detail.get("title") or "")
    summary = str(detail.get("summary") or "")
    pushed = bool(detail.get("wechatDraftPushedAt"))

    if summary:
        marker = "\n<!-- e2e-probe -->"
        probe = summary if marker in summary else summary.rstrip() + marker
        if c.http(
            "保存通稿 PUT",
            "PUT",
            f"{base}/api/events/{event_id}/press",
            body={"title": title, "summary": probe},
        ):
            c.http(
                "保存通稿·还原",
                "PUT",
                f"{base}/api/events/{event_id}/press",
                body={"title": title, "summary": summary},
            )
    else:
        c.ok("保存通稿 SKIP", "无通稿正文")

    if not pushed and summary.strip():
        c.http(
            "标记草稿已推 POST",
            "POST",
            f"{base}/api/events/{event_id}/mark-draft-pushed",
            body={},
        )
    else:
        c.ok("标记草稿已推 SKIP", "已推送或无正文")

    if test_wechat_push and summary.strip():
        c.http(
            "推送草稿箱 POST",
            "POST",
            f"{base}/api/events/{event_id}/push-draft",
            body={"title": title, "summary": summary},
            expect=(200, 400, 502),
        )
    else:
        c.ok("推送草稿箱 SKIP", "默认跳过；--test-wechat-push 可测")

    return 1 if any(not r[1] for r in c.rows) else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Platform 前端 E2E API 验收")
    parser.add_argument("--skip-mutations", action="store_true")
    parser.add_argument("--test-wechat-push", action="store_true")
    args = parser.parse_args()

    c = Checker()
    code = execute(c, args.skip_mutations, args.test_wechat_push)
    failed = [r for r in c.rows if not r[1]]
    print("\n=== Platform 前端 E2E（API 层）===\n")
    print(f"PLATFORM={PLATFORM_BASE}  BFF={BFF_BASE}\n")
    for name, ok, detail in c.rows:
        print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}")
    print(f"\n合计 {len(c.rows) - len(failed)}/{len(c.rows)} 通过")
    if failed:
        print("\n失败项请检查 BFF :8787 与 Platform :3000")
    print("\n--- UI → API 对照 ---")
    for page, ctrl, method, api in UI_MATRIX:
        print(f"  [{page}] {ctrl}: {method} {api}")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
