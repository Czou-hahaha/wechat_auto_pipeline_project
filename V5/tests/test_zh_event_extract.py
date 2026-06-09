"""中文簇级 LLM 事件提炼测试。"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from src.ai import SummaryService
from src.config import Settings
from src.services.zh_ingest.event_extract import extract_zh_cluster_event


@dataclass
class _FakeHit:
    url: str = "https://www.jiemian.com/article/1.html"
    snippet: str = ""


@dataclass
class _FakePrepared:
    title: str
    text: str
    final_url: str = "https://www.jiemian.com/article/1.html"
    hit: _FakeHit | None = None

    def __post_init__(self) -> None:
        if self.hit is None:
            self.hit = _FakeHit(url=self.final_url)


def test_cluster_extract_fallback_keeps_drone_event() -> None:
    async def _run() -> None:
        svc = SummaryService(api_key="", base_url="https://api.deepseek.com", model="deepseek-chat")
        settings = Settings(zh_llm_event_extract_max_chars=24)
        cluster = [
            _FakePrepared(
                title="三峡集团首个无人机智能巡检管理体系投入运行",
                text="无人机智能巡检在内蒙古新能源场站投入运行，覆盖光伏与风机巡检。",
            )
        ]
        out = await extract_zh_cluster_event(svc, settings, cluster)
        assert out.keep_cluster is True
        assert out.event_title_zh
        assert len(out.event_title_zh) <= 24

    asyncio.run(_run())


def test_cluster_extract_fallback_rejects_offtopic() -> None:
    async def _run() -> None:
        svc = SummaryService(api_key="", base_url="https://api.deepseek.com", model="deepseek-chat")
        settings = Settings(zh_llm_event_extract_max_chars=24)
        cluster = [
            _FakePrepared(
                title="今日足球联赛战报",
                text="某队主场获胜。",
            )
        ]
        out = await extract_zh_cluster_event(svc, settings, cluster)
        assert out.keep_cluster is False

    asyncio.run(_run())
