"""阶段四 → 阶段五 承接：mock DeepSeek，验证落库字段。"""
from __future__ import annotations

import asyncio
import json
import os
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

from src.config import Settings
from src.event_press_workflow import run_event_press_generation
from src.services.qa_rewrite.pipeline import PressQualityResult
from src.services.qa_rewrite.qa_service import QAResult
from src.storage import JsonStore


def _write_fixture_store(data_dir: Path) -> None:
    eid = "ev-test-qa-chain"
    articles = [
        {
            "id": "a1",
            "title": "政策稿一",
            "source_url": "https://gov.example.com/1",
            "resolved_url": "https://gov.example.com/1",
            "extracted_text": "市交通局今日公开征求意见，公众可在30日内反馈。",
            "event_id": eid,
        },
        {
            "id": "a2",
            "title": "政策稿二",
            "source_url": "https://media.example.com/2",
            "resolved_url": "https://media.example.com/2",
            "extracted_text": "行业协会召开座谈会，讨论航线规划与应急处置。",
            "event_id": eid,
        },
    ]
    events = [
        {
            "id": eid,
            "title": "低空管理征求意见",
            "summary": "",
            "summary_zh": "",
            "dominant_topic_key": "低空经济",
            "created_at": "2026-05-16T00:00:00+00:00",
        }
    ]
    (data_dir / "articles.json").write_text(json.dumps(articles, ensure_ascii=False), encoding="utf-8")
    (data_dir / "events.json").write_text(json.dumps(events, ensure_ascii=False), encoding="utf-8")
    (data_dir / "event_article_map.json").write_text("[]", encoding="utf-8")


def test_event_press_chains_to_qa_and_persists_metadata() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        data_dir = Path(tmp)
        _write_fixture_store(data_dir)
        os.environ["DATA_DIR"] = str(data_dir)
        os.environ["DEEPSEEK_API_KEY"] = "sk-test"
        os.environ["QA_REWRITE_ENABLED"] = "true"
        os.environ["EVENT_AI_PRESS_MIN_ARTICLES"] = "2"
        os.environ["EVENT_AI_PRESS_SKIP_IF_EXISTS"] = "false"

        settings = Settings()
        store = JsonStore(data_dir)

        draft = "初稿含预测性表述，分析人士认为三季度将落地。"
        final = "终稿仅保留材料事实，市交通局公开征求意见。"

        async def _run() -> None:
            with (
                patch(
                    "src.services.ai_press_writer.ai_writer_service.EventPressWriterService.generate_press_for_event",
                    new_callable=AsyncMock,
                    return_value=draft,
                ),
                patch(
                    "src.services.qa_rewrite.pipeline.run_press_quality_pipeline",
                    new_callable=AsyncMock,
                ) as mock_qa,
            ):
                mock_qa.return_value = PressQualityResult(
                    final_article=final,
                    last_qa=QAResult(
                        score=88,
                        approved=True,
                        hallucination=False,
                        rewrite_suggestions=[],
                    ),
                    rewrite_attempts=1,
                    stopped_reason="passed_threshold",
                )
                await run_event_press_generation(store, settings, force=True)

        asyncio.run(_run())

        ev = next(e for e in store.list_events() if e.get("id") == "ev-test-qa-chain")
        assert ev.get("event_press_zh") == final
        assert ev.get("event_press_qa_score") == 88
        assert ev.get("event_press_qa_rewrite_attempts") == 1
        assert ev.get("event_press_qa_stopped_reason") == "passed_threshold"
        assert str(ev.get("event_press_qa_at") or "").strip()


def test_event_press_skips_qa_when_disabled() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        data_dir = Path(tmp)
        _write_fixture_store(data_dir)
        os.environ["DATA_DIR"] = str(data_dir)
        os.environ["DEEPSEEK_API_KEY"] = "sk-test"
        os.environ["QA_REWRITE_ENABLED"] = "false"
        os.environ["EVENT_AI_PRESS_SKIP_IF_EXISTS"] = "false"

        settings = Settings()
        store = JsonStore(data_dir)
        draft = "仅阶段四初稿。"

        async def _run() -> None:
            with (
                patch(
                    "src.services.ai_press_writer.ai_writer_service.EventPressWriterService.generate_press_for_event",
                    new_callable=AsyncMock,
                    return_value=draft,
                ),
                patch(
                    "src.services.qa_rewrite.pipeline.run_press_quality_pipeline",
                    new_callable=AsyncMock,
                ) as mock_qa,
            ):
                await run_event_press_generation(store, settings, force=True)
                mock_qa.assert_not_called()

        asyncio.run(_run())
        ev = store.list_events()[0]
        assert ev.get("event_press_zh") == draft
        assert not ev.get("event_press_qa_at")
