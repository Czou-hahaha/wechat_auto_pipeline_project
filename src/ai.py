from __future__ import annotations

import logging
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)
_PROMPT_DOC_PATH = Path(__file__).resolve().parents[1] / "docs" / "summary_prompt.md"


class SummaryService:
    def __init__(self, *, api_key: str, base_url: str, model: str):
        self._api_key = api_key.strip()
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._style_guide = self._load_style_guide()

    async def summarize(self, *, title: str, text: str, max_chars: int = 2200) -> str:
        clean_text = (text or "").strip()[:12000]
        if not clean_text:
            return f"【摘要】{title}\n原文正文不足，暂不生成摘要。"
        if not self._api_key:
            return self._fallback(title=title, text=clean_text, max_chars=max_chars)
        prompt = (
            self._style_guide.replace("{{MAX_CHARS}}", str(max_chars)).strip()
            + "\n\n"
            + f"标题：{title}\n\n原文：\n{clean_text}\n\n仅输出摘要正文。"
        )
        payload = {
            "model": self._model,
            "temperature": 0.7,
            "max_tokens": min(4096, max_chars + 800),
            "messages": [
                {"role": "system", "content": "你是严谨的中文编辑。"},
                {"role": "user", "content": prompt},
            ],
        }
        try:
            async with httpx.AsyncClient(timeout=90.0) as client:
                resp = await client.post(
                    f"{self._base_url}/v1/chat/completions",
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    json=payload,
                )
                resp.raise_for_status()
                data = resp.json()
            content = (data.get("choices", [{}])[0].get("message", {}).get("content", "") or "").strip()
            if content:
                return self._sanitize_summary_text(content)[:max_chars]
            return self._fallback(title=title, text=clean_text, max_chars=max_chars)
        except Exception:
            logger.exception("DeepSeek 摘要失败，回退本地摘要")
            return self._fallback(title=title, text=clean_text, max_chars=max_chars)

    @staticmethod
    def _load_style_guide() -> str:
        default_prompt = (
            "你是中文公众号编辑。只基于原文写摘要，不要扩写，不要编造，不要增加原文不存在的数据。\n"
            "长度不超过 {{MAX_CHARS}} 字。"
        )
        try:
            text = _PROMPT_DOC_PATH.read_text(encoding="utf-8").strip()
            if text:
                return text
        except Exception:
            logger.warning("摘要规范文档读取失败，使用内置默认 prompt: %s", _PROMPT_DOC_PATH)
        return default_prompt

    @staticmethod
    def _fallback(*, title: str, text: str, max_chars: int) -> str:
        body = " ".join(text.split())[: max_chars - 20]
        return SummaryService._sanitize_summary_text(f"【摘要】{title}\n{body}")

    @staticmethod
    def _sanitize_summary_text(text: str) -> str:
        out = text or ""
        # Product requirement: do not expose markdown emphasis markers.
        out = out.replace("**", "")
        out = out.replace("\r\n", "\n").replace("\r", "\n")
        out = "\n".join(line.rstrip() for line in out.split("\n"))
        return out.strip()
