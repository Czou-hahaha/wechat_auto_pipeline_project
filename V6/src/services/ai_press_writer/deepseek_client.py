"""DeepSeek Chat Completions 异步客户端：重试、超时、可调采样参数。"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

import httpx

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ChatParams:
    """单次对话请求参数（与 DeepSeek OpenAI 兼容接口对齐）。"""

    temperature: float = 0.4
    max_tokens: int = 1800
    top_p: float = 0.8
    frequency_penalty: float = 0.2


class DeepSeekChatClient:
    """``/v1/chat/completions`` 异步调用，带有限次重试。"""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = "https://api.deepseek.com",
        model: str = "deepseek-chat",
        timeout_sec: float = 120.0,
        max_retries: int = 3,
        retry_backoff_sec: float = 1.6,
    ) -> None:
        self._api_key = (api_key or "").strip()
        self._base = (base_url or "").rstrip("/")
        self._model = (model or "").strip() or "deepseek-chat"
        self._timeout = float(timeout_sec)
        self._max_retries = max(1, int(max_retries))
        self._retry_backoff = max(0.2, float(retry_backoff_sec))

    @property
    def configured(self) -> bool:
        return bool(self._api_key)

    async def chat_completion_text(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        params: ChatParams | None = None,
    ) -> str:
        """
        返回 assistant 文本内容；失败抛错由上层处理。

        批量调用时建议：**长体例固定为同一 ``system_prompt`` 字符串引用**，仅每次替换 ``user_prompt``。
        这样便于厂商对重复前缀做缓存（若支持），也有利于风格一致；输入侧 token 仍按次计费，除非 API 明确减免。
        """
        if not self._api_key:
            raise RuntimeError("DeepSeek API key 未配置")
        p = params or ChatParams()
        payload: dict[str, Any] = {
            "model": self._model,
            "temperature": p.temperature,
            "max_tokens": p.max_tokens,
            "top_p": p.top_p,
            "frequency_penalty": p.frequency_penalty,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        last_exc: Exception | None = None
        for attempt in range(1, self._max_retries + 1):
            try:
                return await self._post_once(payload=payload)
            except (httpx.TimeoutException, httpx.TransportError) as e:
                last_exc = e
                logger.warning(
                    "deepseek transport/timeout attempt=%d/%d err=%s",
                    attempt,
                    self._max_retries,
                    type(e).__name__,
                )
            except httpx.HTTPStatusError as e:
                last_exc = e
                code = e.response.status_code
                if code in (429, 500, 502, 503, 504):
                    logger.warning(
                        "deepseek http %s attempt=%d/%d",
                        code,
                        attempt,
                        self._max_retries,
                    )
                else:
                    raise
            if attempt < self._max_retries:
                await asyncio.sleep(self._retry_backoff * attempt)
        assert last_exc is not None
        raise last_exc

    async def _post_once(self, *, payload: dict[str, Any]) -> str:
        url = f"{self._base}/v1/chat/completions"
        headers = {"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"}
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
        choices = data.get("choices")
        if not isinstance(choices, list) or not choices:
            logger.error("deepseek empty choices")
            return ""
        msg = choices[0].get("message") if isinstance(choices[0], dict) else None
        content = (msg or {}).get("content") if isinstance(msg, dict) else None
        return str(content or "").strip()
