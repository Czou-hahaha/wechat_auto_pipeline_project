#!/usr/bin/env python3
"""
验证「模块一：检索」与「模块二：全文 + 向量聚类报告」的 JSON 契约是否衔接。

不发起网络请求：只检查 ``tests/data/search/test_search_results.json``（或 ``--fixture``）
是否为 ``run_search_flow`` 写入、``run_saved_search_dedupe_report`` 读取的数组格式。

在 ``V3/`` 目录执行::

    python tests/integration/verify_search_dedupe_chain.py
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


def _v3_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _validate_rows(rows: object) -> tuple[bool, str]:
    if not isinstance(rows, list):
        return False, "root JSON must be an array"
    for i, row in enumerate(rows):
        if not isinstance(row, dict):
            return False, f"row {i} must be object"
        if not str(row.get("url") or "").strip().startswith("http"):
            return False, f"row {i} missing valid url"
        if "title" not in row:
            return False, f"row {i} missing title key"
    return True, f"ok, {len(rows)} hits"


def main() -> int:
    ap = argparse.ArgumentParser(description="Validate search JSON → dedupe report contract")
    ap.add_argument(
        "--fixture",
        type=str,
        default="",
        help="Override path (default: tests/data/search/test_search_results.json under V3)",
    )
    args = ap.parse_args()

    root = _v3_root()
    os.chdir(root)

    path = Path(args.fixture).expanduser() if args.fixture else root / "tests/data/search/test_search_results.json"
    if not path.is_absolute():
        path = root / path
    if not path.is_file():
        print(f"SKIP: fixture not found: {path}")
        print("  Run first: python tests/integration/run_search_flow.py")
        return 0

    raw = path.read_text(encoding="utf-8")
    rows = json.loads(raw)
    ok, msg = _validate_rows(rows)
    if not ok:
        print(f"FAIL: {msg}")
        return 1
    print(f"PASS: {path.relative_to(root)} — {msg}")
    print("  Next: python tests/integration/run_saved_search_dedupe_report.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
