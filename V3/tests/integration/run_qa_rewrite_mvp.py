"""
阶段五 MVP：原始素材 + 初稿 → QA →（未达标则重写）→ 终稿。

用法（在 ``V3/`` 下，需 ``DEEPSEEK_API_KEY``）::

    export PYTHONPATH=.
    python tests/integration/run_qa_rewrite_mvp.py

仅跑解析/打包逻辑（不调 API）::

    python tests/integration/run_qa_rewrite_mvp.py --dry-run
"""
from __future__ import annotations

import argparse
import asyncio
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
    candidates = [_V3_ROOT / ".env", _V3_ROOT.parent / "V1" / ".env"]
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


def _stub_articles() -> list[dict[str, str]]:
    return [
        {
            "title": "某市发布低空飞行管理征求意见稿",
            "url": "https://example.com/a",
            "body": "市交通局今日就《低空飞行活动管理办法（征求意见稿）》公开征求意见，草案提出对无人机实名登记与空域申请流程进行细化，公众可在30日内反馈。",
        },
        {
            "title": "行业协会召开低空安全专题座谈会",
            "url": "https://example.com/b",
            "body": "与会代表讨论了城市复杂环境下的航线规划与应急处置协同机制，强调以数据共享提升监管效率。",
        },
    ]


def _stub_draft() -> str:
    return (
        "市交通局今日就低空飞行管理公开征求意见，草案提出实名登记与空域申请细化，公众可在30日内反馈。"
        "行业协会同日召开座谈会，讨论航线规划与应急处置协同，并强调数据共享提升监管效率。"
        "分析人士预测，相关细则可能在三季度落地，将显著刺激产业链投资。"
    )


async def _run_live() -> None:
    from src.config import Settings
    from src.services.qa_rewrite.pipeline import run_press_quality_pipeline

    _apply_env_files()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    articles = _stub_articles()
    draft = _stub_draft()
    res = await run_press_quality_pipeline(
        event_articles=articles,
        draft=draft,
        settings=Settings(),
        max_event_articles_chars=24_000,
    )
    print(json.dumps(res.to_log_dict(), ensure_ascii=False, indent=2))
    print("\n--- final_article ---\n")
    print(res.final_article)


def _run_dry() -> None:
    from src.services.qa_rewrite.context_pack import format_event_articles_block
    from src.services.qa_rewrite.qa_service import parse_qa_payload

    block, meta = format_event_articles_block(_stub_articles(), max_chars=500)
    assert "…" in block or len(block) <= 500
    r = parse_qa_payload(
        {
            "score": 72,
            "approved": False,
            "hallucination": False,
            "issues": [{"type": "speculation", "severity": "high", "description": "含预测性表述"}],
            "missing_points": [],
            "rewrite_suggestions": ["删除预测句，仅保留材料事实"],
        }
    )
    print(json.dumps({"packed_meta": meta, "qa": r.to_public_dict()}, ensure_ascii=False, indent=2))


def main() -> None:
    ap = argparse.ArgumentParser(description="阶段五 QA + 条件重写 MVP")
    ap.add_argument("--dry-run", action="store_true", help="不调 DeepSeek，仅校验打包与 JSON 解析")
    args = ap.parse_args()
    if args.dry_run:
        _run_dry()
        return
    asyncio.run(_run_live())


if __name__ == "__main__":
    main()
