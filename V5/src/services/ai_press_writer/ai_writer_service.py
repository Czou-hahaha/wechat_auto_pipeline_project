"""事件级中文通稿：选文、控长、调用 DeepSeek。"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from src.services.ai_press_writer.article_selector import (
    format_articles_block,
    select_articles_for_event,
)
from src.services.ai_press_writer.deepseek_client import ChatParams, DeepSeekChatClient
from src.services.ai_press_writer.prompt_builder import (
    format_event_press_user,
    get_event_press_system_prompt,
    get_event_press_user_template,
)

if TYPE_CHECKING:
    from src.config import Settings

logger = logging.getLogger(__name__)


@dataclass
class EventPressWriterConfig:
    """运行时可覆盖的默认参数。"""

    top_k: int = 5
    temperature: float = 0.4
    max_tokens: int = 1800
    top_p: float = 0.8
    frequency_penalty: float = 0.2
    timeout_sec: float = 180.0
    max_retries: int = 3
    # 0 = 不截断单篇正文；>0 则每篇最多取前 N 字符
    per_article_max_chars: int = 0
    # 0 = 不截断整段 user prompt；>0 则总字符硬帽
    approx_max_user_chars: int = 0
    # 0 = 关闭「估 token 超预算则自动缩短单篇」；>0 时仅在 per_article_max_chars>0 时参与收缩
    soft_token_budget: int = 0


def _estimate_tokens_mixed(text: str) -> int:
    """粗估 token（中英混排保守）：避免把整库塞进上下文。"""
    s = text or ""
    if not s:
        return 0
    cjk = sum(1 for ch in s if "\u4e00" <= ch <= "\u9fff")
    rest = max(0, len(s) - cjk)
    return int(cjk * 1.0 + rest * 0.35)


class EventPressWriterService:
    """基于 ``JsonStore`` 事件与稿件生成中文通稿。"""

    def __init__(
        self,
        settings: "Settings",
        *,
        writer_cfg: EventPressWriterConfig | None = None,
    ) -> None:
        self._settings = settings
        self._cfg = writer_cfg or EventPressWriterConfig()
        if writer_cfg is None:
            self._cfg.per_article_max_chars = int(
                getattr(settings, "event_ai_press_per_article_max_chars", 0) or 0
            )
            self._cfg.approx_max_user_chars = int(getattr(settings, "event_ai_press_max_user_chars", 0) or 0)
            self._cfg.soft_token_budget = int(getattr(settings, "event_ai_press_soft_token_budget", 0) or 0)
            self._cfg.timeout_sec = float(getattr(settings, "event_ai_press_timeout_sec", 180.0))
        raw_mode = str(getattr(settings, "event_ai_press_selection_mode", "") or "all_by_tier").strip().lower()
        self._selection_mode = raw_mode if raw_mode in ("top_k_dedupe", "all_by_tier") else "top_k_dedupe"
        self._max_articles_in_prompt = max(
            1, min(int(getattr(settings, "event_ai_press_max_articles_in_prompt", 20)), 60)
        )
        self._client = DeepSeekChatClient(
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url,
            model=settings.deepseek_model,
            timeout_sec=self._cfg.timeout_sec,
            max_retries=self._cfg.max_retries,
        )
        # 批量多事件时：system 与 user 模板各加载一次，循环内只拼装 per-event user（对齐 DeepSeek/OpenAI 常见省 token 写法）
        self._event_press_system = get_event_press_system_prompt()
        self._event_press_user_template = get_event_press_user_template()

    @property
    def available(self) -> bool:
        return self._client.configured

    async def generate_press_for_event(
        self,
        *,
        event_title: str,
        dominant_topic_key: str,
        article_rows: list[dict[str, Any]],
    ) -> str:
        """
        返回模型正文；无 key 或选文后无材料时返回固定不足提示或抛错。

        不在此服务内做「全文翻译」步骤；英文材料以摘录形式直接进入 user prompt。
        """
        if not self.available:
            logger.warning("event press writer: skip, DEEPSEEK_API_KEY empty")
            return "【信息不足，无法生成高质量通稿】"
        selected = select_articles_for_event(
            article_rows,
            top_k=self._cfg.top_k,
            mode=self._selection_mode,
            max_articles_in_prompt=self._max_articles_in_prompt,
        )
        if not selected:
            return "【信息不足，无法生成高质量通稿】"
        per_cap = self._cfg.per_article_max_chars
        block = format_articles_block(selected, per_article_max_chars=per_cap)
        soft = self._cfg.soft_token_budget
        if soft > 0 and per_cap > 0:
            while _estimate_tokens_mixed(block) > soft and per_cap > 900:
                per_cap = max(900, int(per_cap * 0.75))
                block = format_articles_block(selected, per_article_max_chars=per_cap)
                logger.info("event press writer: shrink per_article_max_chars=%d (soft_token_budget=%d)", per_cap, soft)
        elif soft > 0 and per_cap <= 0:
            logger.warning(
                "event press writer: soft_token_budget=%d ignored (set EVENT_AI_PRESS_PER_ARTICLE_MAX_CHARS>0 to enable shrink)",
                soft,
            )
        kw_parts: list[str] = []
        dk = (dominant_topic_key or "").strip()
        if dk:
            kw_parts.append(dk)
        for key in sorted({str(r.get("topic_key") or "").strip() for r in article_rows if r.get("topic_key")}):
            if key and key not in kw_parts:
                kw_parts.append(key)
        keywords = ", ".join(kw_parts) if kw_parts else dk
        user_prompt = format_event_press_user(
            self._event_press_user_template,
            event_title=event_title,
            keywords=keywords,
            articles_block=block,
        )
        cap_chars = self._cfg.approx_max_user_chars
        if cap_chars > 0 and len(user_prompt) > cap_chars:
            user_prompt = user_prompt[:cap_chars]
            logger.warning("event press writer: user prompt truncated to %d chars", cap_chars)
        params = ChatParams(
            temperature=self._cfg.temperature,
            max_tokens=self._cfg.max_tokens,
            top_p=self._cfg.top_p,
            frequency_penalty=self._cfg.frequency_penalty,
        )
        try:
            out = await self._client.chat_completion_text(
                system_prompt=self._event_press_system,
                user_prompt=user_prompt,
                params=params,
            )
        except Exception:
            logger.exception("event press writer: DeepSeek 调用失败")
            return "【信息不足，无法生成高质量通稿】"
        return (out or "").strip() or "【信息不足，无法生成高质量通稿】"
