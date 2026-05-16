"""基于原始素材与审稿意见，对新闻稿做 DeepSeek 异步重写。"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from collections.abc import Mapping, Sequence
from typing import Any

from src.services.ai_press_writer.deepseek_client import ChatParams, DeepSeekChatClient

from .context_pack import format_event_articles_block
from .qa_service import QAResult

logger = logging.getLogger(__name__)


def _default_prompts_dir() -> Path:
    return Path(__file__).resolve().parent / "prompts"


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip()


class RewriteService:
    """加载 ``rewrite_system.txt``，仅输出正文（非 JSON）。"""

    def __init__(
        self,
        client: DeepSeekChatClient,
        *,
        prompts_dir: Path | None = None,
        chat_params: ChatParams | None = None,
    ) -> None:
        self._client = client
        self._prompts_dir = prompts_dir or _default_prompts_dir()
        self._system = _read_text(self._prompts_dir / "rewrite_system.txt")
        self._params = chat_params or ChatParams(temperature=0.35, max_tokens=3600, top_p=0.85, frequency_penalty=0.15)

    def _build_user_prompt(self, *, event_block: str, qa_payload: dict[str, Any], draft: str) -> str:
        qa_json = json.dumps(qa_payload, ensure_ascii=False)
        return (
            "以下为输入材料，请严格按 system 要求只输出最终新闻稿正文。\n\n"
            "【原始 event articles】\n"
            f"{event_block}\n\n"
            "【审稿 JSON】\n"
            f"{qa_json}\n\n"
            "【当前新闻稿】\n"
            f"{draft.strip()}\n"
        )

    async def rewrite(
        self,
        *,
        original_articles: str | Sequence[Mapping[str, Any]],
        draft: str,
        qa: QAResult | dict[str, Any],
        max_original_chars: int,
    ) -> str:
        """
        根据审稿意见重写 ``draft``。

        Args:
            original_articles: 与审稿时一致的原始素材。
            draft: 当前待改稿件。
            qa: ``QAResult`` 或可 JSON 序列化的 dict。
            max_original_chars: 原始素材侧最大字符数（>0 生效）。
        """
        event_block, pack_meta = format_event_articles_block(original_articles, max_chars=max_original_chars)
        qa_payload = qa.to_public_dict() if isinstance(qa, QAResult) else dict(qa)
        user_prompt = self._build_user_prompt(event_block=event_block, qa_payload=qa_payload, draft=draft)
        logger.info(
            "%s",
            json.dumps(
                {
                    "event": "rewrite_request",
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
        out = (text or "").strip()
        logger.info(
            "%s",
            json.dumps(
                {
                    "event": "rewrite_completed",
                    "output_chars": len(out),
                },
                ensure_ascii=False,
            ),
        )
        return out
