"""中文 LLM 单篇入库门禁测试。"""

from __future__ import annotations

import asyncio

from src.ai import SummaryService
from src.config import Settings
from src.services.zh_ingest.article_gate import assess_zh_article


def test_sanxia_drone_inspection_short_brief_kept_by_fallback() -> None:
    """界面快讯：三峡无人机巡检 — 短正文仍应保留（无 API key 走 fallback）。"""

    async def _run() -> None:
        svc = SummaryService(api_key="", base_url="https://api.deepseek.com", model="deepseek-chat")
        settings = Settings()
        title = "三峡集团首个无人机智能巡检管理体系投入运行"
        text = (
            "近日，三峡集团首个无人机智能巡检管理体系在内蒙古投入运行，"
            "首批覆盖12座新能源场站，实现无人机统一管控与智能诊断。"
        )
        out = await assess_zh_article(
            svc,
            settings,
            title=title,
            text=text,
            snippet="界面快报",
            url="https://www.jiemian.com/article/14546638.html",
        )
        assert out.keep is True
        assert out.is_domain_relevant is True
        assert out.is_political_sensitive is False
        assert out.is_anti_china_smear is False

    asyncio.run(_run())


def test_football_rejected_by_fallback() -> None:
    async def _run() -> None:
        svc = SummaryService(api_key="", base_url="https://api.deepseek.com", model="deepseek-chat")
        settings = Settings()
        out = await assess_zh_article(
            svc,
            settings,
            title="今日足球联赛战报",
            text="某队获胜。",
            snippet="",
            url="https://www.jiemian.com/article/1.html",
        )
        assert out.keep is False

    asyncio.run(_run())


def test_war_drone_rejected_deterministic() -> None:
    async def _run() -> None:
        svc = SummaryService(api_key="", base_url="https://api.deepseek.com", model="deepseek-chat")
        settings = Settings()
        out = await assess_zh_article(
            svc,
            settings,
            title="美军称拦截伊朗导弹和无人机",
            text="中东局势升级，以军发动空袭。",
            snippet="",
            url="https://example.com/war",
        )
        assert out.keep is False
        assert out.reason

    asyncio.run(_run())


def test_smear_rejected_deterministic() -> None:
    async def _run() -> None:
        svc = SummaryService(api_key="", base_url="https://api.deepseek.com", model="deepseek-chat")
        settings = Settings()
        out = await assess_zh_article(
            svc,
            settings,
            title="唱衰中国经济威胁论升温",
            text="外媒称中国无人机产业面临崩溃。",
            snippet="",
            url="https://example.com/smear",
        )
        assert out.keep is False
        assert out.is_anti_china_smear is True

    asyncio.run(_run())
