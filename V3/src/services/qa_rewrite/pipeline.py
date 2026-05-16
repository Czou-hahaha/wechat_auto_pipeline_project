"""writer → QA →（未达标则重写，最多 N 次）→ 终稿。"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from src.config import Settings
from src.services.ai_press_writer.deepseek_client import DeepSeekChatClient

from .qa_service import QAResult, QAService, parse_qa_payload
from .rewrite_service import RewriteService

logger = logging.getLogger(__name__)


@dataclass
class QualityRoundTrace:
    """单轮 QA（及可选重写前）轨迹。"""

    draft_chars: int
    qa: dict[str, Any]
    score: int
    passed_threshold: bool
    rewrite_applied_after: bool


@dataclass
class PressQualityResult:
    """质量控制流水线输出。"""

    final_article: str
    last_qa: QAResult
    rounds: list[QualityRoundTrace] = field(default_factory=list)
    rewrite_attempts: int = 0
    stopped_reason: str = ""

    def to_log_dict(self) -> dict[str, Any]:
        return {
            "event": "press_quality_pipeline_done",
            "final_chars": len(self.final_article or ""),
            "rewrite_attempts": self.rewrite_attempts,
            "stopped_reason": self.stopped_reason,
            "last_score": self.last_qa.score,
            "last_hallucination": self.last_qa.hallucination,
            "rounds": [
                {
                    "draft_chars": r.draft_chars,
                    "score": r.score,
                    "passed_threshold": r.passed_threshold,
                    "rewrite_applied_after": r.rewrite_applied_after,
                }
                for r in self.rounds
            ],
        }


def _passes(score: int, hallucination: bool, *, threshold: int) -> bool:
    return (not hallucination) and score >= threshold


async def run_press_quality_pipeline(
    *,
    event_articles: str | Sequence[Mapping[str, Any]],
    draft: str,
    settings: Settings | None = None,
    deepseek: DeepSeekChatClient | None = None,
    pass_threshold: int | None = None,
    max_rewrite_rounds: int | None = None,
    qa_timeout_sec: float | None = None,
    rewrite_timeout_sec: float | None = None,
    max_event_articles_chars: int | None = None,
) -> PressQualityResult:
    """
    对 ``draft`` 执行 QA；若 ``score < threshold`` 则调用重写，最多 ``max_rewrite_rounds`` 次。

    每轮重写后会再次 QA，直到达标或用尽重写次数。
    """
    cfg = settings or Settings()
    threshold = int(pass_threshold if pass_threshold is not None else cfg.qa_rewrite_pass_threshold)
    max_rw = int(max_rewrite_rounds if max_rewrite_rounds is not None else cfg.qa_rewrite_max_rounds)
    qa_to = float(qa_timeout_sec if qa_timeout_sec is not None else cfg.qa_rewrite_qa_timeout_sec)
    rw_to = float(rewrite_timeout_sec if rewrite_timeout_sec is not None else cfg.qa_rewrite_rewrite_timeout_sec)
    max_ctx = int(max_event_articles_chars if max_event_articles_chars is not None else cfg.qa_rewrite_max_event_chars)

    if not (cfg.deepseek_api_key or "").strip():
        logger.error("%s", json.dumps({"event": "press_quality_missing_api_key"}, ensure_ascii=False))
        return PressQualityResult(
            final_article=draft,
            last_qa=QAResult(score=0, approved=False, hallucination=False, rewrite_suggestions=[]),
            rewrite_attempts=0,
            stopped_reason="missing_deepseek_api_key",
        )

    if deepseek is not None:
        qa_svc = QAService(deepseek)
        rw_svc = RewriteService(deepseek)
    else:
        qa_client = DeepSeekChatClient(
            api_key=cfg.deepseek_api_key,
            base_url=cfg.deepseek_base_url,
            model=cfg.deepseek_model,
            timeout_sec=qa_to,
            max_retries=cfg.qa_rewrite_max_retries,
            retry_backoff_sec=cfg.qa_rewrite_retry_backoff_sec,
        )
        rw_client = DeepSeekChatClient(
            api_key=cfg.deepseek_api_key,
            base_url=cfg.deepseek_base_url,
            model=cfg.deepseek_model,
            timeout_sec=rw_to,
            max_retries=cfg.qa_rewrite_max_retries,
            retry_backoff_sec=cfg.qa_rewrite_retry_backoff_sec,
        )
        qa_svc = QAService(qa_client)
        rw_svc = RewriteService(rw_client)

    current = draft.strip()
    rounds: list[QualityRoundTrace] = []
    rewrite_attempts = 0
    stopped = "initial"

    for cycle in range(0, max_rw + 1):
        qa_res = await qa_svc.review(event_articles=event_articles, draft=current, max_event_articles_chars=max_ctx)
        ok = _passes(qa_res.score, qa_res.hallucination, threshold=threshold)
        trace = QualityRoundTrace(
            draft_chars=len(current),
            qa=qa_res.to_public_dict(),
            score=qa_res.score,
            passed_threshold=ok,
            rewrite_applied_after=False,
        )
        rounds.append(trace)
        logger.info(
            "%s",
            json.dumps(
                {
                    "event": "press_quality_round",
                    "cycle": cycle,
                    "score": qa_res.score,
                    "passed": ok,
                    "rewrite_attempts_so_far": rewrite_attempts,
                },
                ensure_ascii=False,
            ),
        )
        if ok:
            stopped = "passed_threshold"
            logger.info("%s", json.dumps(PressQualityResult(current, qa_res, rounds, rewrite_attempts, stopped).to_log_dict(), ensure_ascii=False))
            return PressQualityResult(current, qa_res, rounds, rewrite_attempts, stopped)

        if rewrite_attempts >= max_rw:
            stopped = "max_rewrite_rounds_exhausted"
            logger.warning("%s", json.dumps(PressQualityResult(current, qa_res, rounds, rewrite_attempts, stopped).to_log_dict(), ensure_ascii=False))
            return PressQualityResult(current, qa_res, rounds, rewrite_attempts, stopped)

        current = await rw_svc.rewrite(
            original_articles=event_articles,
            draft=current,
            qa=qa_res,
            max_original_chars=max_ctx,
        )
        rewrite_attempts += 1
        rounds[-1].rewrite_applied_after = True
        stopped = "rewrote_and_continue"

    stopped = "unexpected_end"
    last = rounds[-1] if rounds else None
    last_qa = QAResult(score=0, approved=False, hallucination=True) if last is None else parse_qa_payload(last.qa)
    return PressQualityResult(current, last_qa, rounds, rewrite_attempts, stopped)
