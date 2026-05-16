"""事件通稿 / 新闻稿：DeepSeek 异步审稿（JSON 输出）。"""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.services.ai_press_writer.deepseek_client import ChatParams, DeepSeekChatClient

from .context_pack import format_event_articles_block
from .json_utils import extract_first_json_object

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class QAIssue:
    """单条审稿问题。"""

    type: str
    severity: str
    description: str


@dataclass
class QAResult:
    """审稿结构化结果（与 prompt 中 JSON 字段对齐）。"""

    score: int
    approved: bool
    hallucination: bool
    issues: list[QAIssue] = field(default_factory=list)
    missing_points: list[str] = field(default_factory=list)
    rewrite_suggestions: list[str] = field(default_factory=list)

    def to_public_dict(self) -> dict[str, Any]:
        """供存储或 API 返回的字典（可 JSON 序列化）。"""
        return {
            "score": int(self.score),
            "approved": bool(self.approved),
            "hallucination": bool(self.hallucination),
            "issues": [
                {"type": i.type, "severity": i.severity, "description": i.description} for i in self.issues
            ],
            "missing_points": list(self.missing_points),
            "rewrite_suggestions": list(self.rewrite_suggestions),
        }


def _default_prompts_dir() -> Path:
    return Path(__file__).resolve().parent / "prompts"


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip()


def _parse_issues(raw: object) -> list[QAIssue]:
    if not isinstance(raw, list):
        return []
    out: list[QAIssue] = []
    for it in raw:
        if isinstance(it, str):
            s = it.strip()
            if s:
                out.append(QAIssue(type="note", severity="medium", description=s))
            continue
        if isinstance(it, dict):
            out.append(
                QAIssue(
                    type=str(it.get("type") or "unknown").strip(),
                    severity=str(it.get("severity") or "medium").strip(),
                    description=str(it.get("description") or "").strip(),
                )
            )
    return out


def _parse_str_list(raw: object) -> list[str]:
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for it in raw:
        s = str(it).strip()
        if s:
            out.append(s)
    return out


def _coerce_bool(val: object, *, default: bool = False) -> bool:
    if isinstance(val, bool):
        return val
    if isinstance(val, (int, float)):
        return bool(val)
    if isinstance(val, str):
        low = val.strip().lower()
        if low in ("true", "1", "yes", "y"):
            return True
        if low in ("false", "0", "no", "n"):
            return False
    return default


def parse_qa_payload(data: dict[str, Any]) -> QAResult:
    """将模型 JSON object 转为 ``QAResult``。"""
    score_raw = data.get("score", 0)
    try:
        score = int(score_raw)
    except (TypeError, ValueError):
        score = 0
    score = max(0, min(100, score))
    hallucination = _coerce_bool(data.get("hallucination"), default=False)
    approved = _coerce_bool(data.get("approved"), default=False)
    return QAResult(
        score=score,
        approved=approved,
        hallucination=hallucination,
        issues=_parse_issues(data.get("issues")),
        missing_points=_parse_str_list(data.get("missing_points")),
        rewrite_suggestions=_parse_str_list(data.get("rewrite_suggestions")),
    )


class QAService:
    """加载 ``qa_system.txt``，调用 DeepSeek，解析 JSON 为 ``QAResult``。"""

    def __init__(
        self,
        client: DeepSeekChatClient,
        *,
        prompts_dir: Path | None = None,
        chat_params: ChatParams | None = None,
    ) -> None:
        self._client = client
        self._prompts_dir = prompts_dir or _default_prompts_dir()
        self._system = _read_text(self._prompts_dir / "qa_system.txt")
        self._params = chat_params or ChatParams(temperature=0.2, max_tokens=2200, top_p=0.75, frequency_penalty=0.0)

    def _build_user_prompt(self, *, event_block: str, draft: str) -> str:
        return (
            "以下为输入材料，请严格按 system 要求只输出 JSON。\n\n"
            "【原始 event articles】\n"
            f"{event_block}\n\n"
            "【AI 生成稿件】\n"
            f"{draft.strip()}\n"
        )

    async def review(
        self,
        *,
        event_articles: str | Sequence[Mapping[str, Any]],
        draft: str,
        max_event_articles_chars: int,
    ) -> QAResult:
        """
        对 ``draft`` 做审稿。

        Args:
            event_articles: 原始素材（字符串或若干 dict，含 title/url/body 等键）。
            draft: AI 生成稿件全文。
            max_event_articles_chars: 原始素材侧最大字符数（>0 生效）；用于粗估 token 控制。
        """
        event_block, pack_meta = format_event_articles_block(event_articles, max_chars=max_event_articles_chars)
        user_prompt = self._build_user_prompt(event_block=event_block, draft=draft)
        logger.info(
            "%s",
            json.dumps(
                {
                    "event": "qa_review_request",
                    "draft_chars": len(draft or ""),
                    **pack_meta,
                },
                ensure_ascii=False,
            ),
        )
        text = await self._client.chat_completion_text(
            system_prompt=self._system,
            user_prompt=user_prompt,
            params=self._params,
        )
        data = extract_first_json_object(text)
        if not data:
            logger.error(
                "%s",
                json.dumps(
                    {"event": "qa_review_parse_failed", "model_text_head": (text or "")[:400]},
                    ensure_ascii=False,
                ),
            )
            return QAResult(score=0, approved=False, hallucination=True, issues=[], missing_points=[], rewrite_suggestions=["模型输出非合法 JSON，视为高风险"])
        result = parse_qa_payload(data)
        logger.info(
            "%s",
            json.dumps(
                {
                    "event": "qa_review_completed",
                    "score": result.score,
                    "approved": result.approved,
                    "hallucination": result.hallucination,
                    "issues_count": len(result.issues),
                    "rewrite_suggestions_count": len(result.rewrite_suggestions),
                },
                ensure_ascii=False,
            ),
        )
        return result
