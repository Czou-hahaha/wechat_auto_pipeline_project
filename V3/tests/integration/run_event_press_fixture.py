"""
用北京同题 fixture 跑阶段四「AI 事件通稿」：复制 → hydrate 成员稿 → 差异化占位正文（避免选文去重为一条）→ DeepSeek。

用法（在 ``V3/`` 下）::

    export PYTHONPATH=.
    export DEEPSEEK_API_KEY=…
    python tests/integration/run_event_press_fixture.py

默认工作目录：``tests/data/event_press_runs/last_fixture_run``（``--clean`` 时重建）。
"""
from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import logging
import os
import sys
from pathlib import Path

_V3_ROOT = Path(__file__).resolve().parents[2]
if str(_V3_ROOT) not in sys.path:
    sys.path.insert(0, str(_V3_ROOT))

logger = logging.getLogger(__name__)


def _apply_env_files() -> None:
    """
    若 shell 未 export，则按顺序从 .env 补全（不覆盖已有环境变量）。

    优先 ``V3/.env``，其次仓库内 ``V1/.env``（便于本机只在 V1 配过 DeepSeek 时跑 V3 脚本）。
    """
    candidates = [
        _V3_ROOT / ".env",
        _V3_ROOT.parent / "V1" / ".env",
    ]
    for path in candidates:
        if not path.is_file():
            continue
        try:
            raw = path.read_text(encoding="utf-8")
        except OSError:
            continue
        for line in raw.splitlines():
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            if s.startswith("export "):
                s = s[7:].strip()
            if "=" not in s:
                continue
            key, _, val = s.partition("=")
            key = key.strip()
            if not key or key in os.environ:
                continue
            val = val.strip()
            if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
                val = val[1:-1]
            os.environ[key] = val


def _load_eef_module():
    path = _V3_ROOT / "tests/integration/run_event_enhancement_fixture.py"
    spec = importlib.util.spec_from_file_location("event_enhancement_fixture", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load run_event_enhancement_fixture")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def diversify_stub_bodies(data_dir: Path) -> int:
    """为 fixture_hydrate 占位稿追加互不相同的段落，降低正文前缀相似度去重。"""
    p = data_dir / "articles.json"
    rows: list[dict] = json.loads(p.read_text(encoding="utf-8"))
    changed = 0
    for row in rows:
        if not isinstance(row, dict):
            continue
        if str(row.get("deepseek_semantic_decision") or "") != "fixture_hydrate":
            continue
        host = str(row.get("source_host") or "unknown")
        tail = (
            f"\n\n【角度区分·{host}】本条为聚类测试占位扩展，避免与簇内其它稿摘录开头完全一致。"
            f"来源侧重：{host} 对北京无人驾驶航空器立法与监管口径的转述角度，与人大网长文不逐字重复。"
        )
        body = str(row.get("extracted_text") or "")
        if tail.strip() not in body:
            row["extracted_text"] = body + tail
            changed += 1
    if changed:
        p.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    return changed


async def _async_press(work_dir: Path) -> None:
    os.environ["DATA_DIR"] = str(work_dir)
    # 与生产一致：至少 2 篇才生成
    os.environ.setdefault("EVENT_AI_PRESS_MIN_ARTICLES", "2")
    os.environ.setdefault("EVENT_AI_PRESS_SKIP_IF_EXISTS", "false")
    os.environ.setdefault("QA_REWRITE_ENABLED", "true")
    _apply_env_files()

    from src.config import Settings
    from src.event_press_workflow import run_event_press_generation
    from src.storage import JsonStore

    settings = Settings()
    store = JsonStore(work_dir)
    await run_event_press_generation(store, settings, force=True)

    for ev in store.list_events():
        if not isinstance(ev, dict):
            continue
        body = str(ev.get("event_press_zh") or "").strip()
        if not body:
            continue
        eid = str(ev.get("id") or "")[:13]
        qa_score = ev.get("event_press_qa_score", "n/a")
        qa_rw = ev.get("event_press_qa_rewrite_attempts", "n/a")
        qa_stop = ev.get("event_press_qa_stopped_reason", "")
        logger.info(
            "=== event_press_zh (event=%s…) len=%d qa_score=%s rewrites=%s stop=%s ===",
            eid,
            len(body),
            qa_score,
            qa_rw,
            qa_stop,
        )
        preview = body[:1200] + ("…" if len(body) > 1200 else "")
        print(preview)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="fixture + 阶段四 AI 事件通稿")
    parser.add_argument(
        "--fixture-dir",
        type=Path,
        default=Path("tests/data/dedupe_runs/beijing"),
    )
    parser.add_argument(
        "--work-dir",
        type=Path,
        default=Path("tests/data/event_press_runs/last_fixture_run"),
    )
    parser.add_argument("--no-clean", action="store_true", help="不删除 work-dir")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-5s %(name)s - %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)

    eef = _load_eef_module()
    os_cwd = Path.cwd()
    try:
        os.chdir(_V3_ROOT)
        fixture_dir = args.fixture_dir.expanduser()
        if not fixture_dir.is_absolute():
            fixture_dir = (_V3_ROOT / fixture_dir).resolve()
        work_dir = args.work_dir.expanduser()
        if not work_dir.is_absolute():
            work_dir = (_V3_ROOT / work_dir).resolve()

        eef.prepare_work_dir(fixture_dir=fixture_dir, work_dir=work_dir, clean=not args.no_clean)
        n = eef.hydrate_articles_from_event_map(work_dir)
        logger.info("hydrate: added %d article(s)", n)
        eef.touch_event_ranking_timestamps(work_dir)
        d = diversify_stub_bodies(work_dir)
        logger.info("diversify_stub_bodies: patched %d row(s)", d)

        asyncio.run(_async_press(work_dir))
    finally:
        os.chdir(os_cwd)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
