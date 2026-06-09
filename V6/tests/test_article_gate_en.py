"""英文 LLM 单篇领域门禁测试。"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

from src.config import Settings
from src.services.zh_ingest.article_gate import assess_en_article


def test_gujarat_iti_llm_rejects_vocational_expansion() -> None:
    async def _run() -> None:
        summarizer = MagicMock()
        summarizer._api_key = "test-key"
        summarizer._chat_json = AsyncMock(
            return_value={
                "keep": False,
                "is_domain_relevant": False,
                "is_political_sensitive": False,
                "is_anti_china_smear": False,
                "category": "other",
                "reason": "职教离题",
            }
        )
        title = (
            "Gujarat to expand ITI courses with Drone Courses among 12 new vocational programs"
        )
        gate = await assess_en_article(
            summarizer,
            Settings(),
            title=title,
            text=title + " Skills training and welding also included.",
            snippet=title,
            url="https://example.com/gujarat-iti",
        )
        assert gate.keep is False
        assert "职教" in gate.reason or gate.reason == "职教离题"

    asyncio.run(_run())


def test_en_drone_policy_llm_keeps() -> None:
    async def _run() -> None:
        summarizer = MagicMock()
        summarizer._api_key = "test-key"
        summarizer._chat_json = AsyncMock(
            return_value={
                "keep": True,
                "is_domain_relevant": True,
                "is_political_sensitive": False,
                "is_anti_china_smear": False,
                "category": "policy",
                "reason": "低空政策",
            }
        )
        title = "FAA publishes new BVLOS drone rules for commercial operators"
        gate = await assess_en_article(
            summarizer,
            Settings(),
            title=title,
            text=title,
            snippet=title,
            url="https://www.faa.gov/newsroom/bvlos",
        )
        assert gate.keep is True
        assert gate.category == "policy"

    asyncio.run(_run())
