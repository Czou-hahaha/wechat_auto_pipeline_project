"""中文短稿入库门槛与 AI 领域判定辅助逻辑。"""

from __future__ import annotations

from dataclasses import dataclass

from src.ai import SummaryService
from src.config import Settings
from src.pipeline import PipelineRunner
from src.search import SearchHit


def test_zh_media_host_detection() -> None:
    settings = Settings(zh_domain_relevance_ai_enabled=True)
    runner = PipelineRunner(settings)
    assert runner._host_is_zh_media("https://www.cls.cn/detail/123")
    assert not runner._host_is_zh_media("https://www.faa.gov/news/1")


def test_editorial_blob_counts_snippet_for_short_telegraph() -> None:
    settings = Settings(zh_ingest_min_chars=80, en_ingest_min_chars=400)
    runner = PipelineRunner(settings)
    blob = runner._editorial_blob_for_length(
        title="低空经济试点扩围",
        snippet="财联社讯，多地发布低空经济支持政策，无人机物流场景加速落地，产业基金与适航审批同步推进。" * 2,
        text="短正文。",
    )
    assert len(blob.replace(" ", "")) >= 80
    assert runner._min_ingest_body_chars("https://www.cls.cn/x") == 80
    assert runner._min_ingest_body_chars("https://www.faa.gov/x") == 400


def test_zh_llm_path_skips_length_gate(monkeypatch) -> None:
    monkeypatch.setenv("ZH_INGEST_LLM_ENABLED", "true")
    monkeypatch.setenv("ZH_SKIP_LENGTH_GATE", "true")
    settings = Settings(zh_ingest_min_chars=80)
    runner = PipelineRunner(settings)
    url = "https://www.jiemian.com/article/14546638.html"
    assert runner._uses_zh_llm_ingest(url) is True
    short_blob = "三峡集团无人机巡检体系投运"
    assert runner._is_too_short(short_blob, min_chars=80) is True
    assert bool(settings.zh_skip_length_gate) is True


def test_zh_llm_cluster_editorial_bypass(monkeypatch) -> None:
    monkeypatch.setenv("ZH_INGEST_LLM_ENABLED", "true")
    settings = Settings()
    runner = PipelineRunner(settings)

    @dataclass
    class PA:
        hit: SearchHit
        title: str
        text: str
        final_url: str

    hit = SearchHit(
        title="短标题无低空词",
        url="https://www.cls.cn/detail/1",
        snippet="",
        published_at="2026-06-07T00:00:00+00:00",
    )

    cluster = [
        PA(hit=hit, title=hit.title, text="短", final_url=hit.url),
    ]
    assert runner._cluster_is_zh_dominant(cluster) is True
    assert runner._cluster_passes_editorial_for_run(cluster) is True


def test_fallback_domain_relevance_keywords() -> None:
    svc = SummaryService(api_key="", base_url="https://api.deepseek.com", model="deepseek-chat")
    out = svc._fallback_domain_relevance(
        title="无人机适航新规征求意见",
        text="民航局发布无人驾驶航空器适航管理征求意见稿。",
        snippet="",
    )
    assert out["is_relevant"] is True
    out2 = svc._fallback_domain_relevance(
        title="今日足球联赛战报",
        text="某队获胜。",
        snippet="",
    )
    assert out2["is_relevant"] is False
