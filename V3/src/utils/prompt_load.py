"""从 ``V3/docs/prompts/*.md`` 加载可迭代的 prompt 文本。"""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).resolve().parents[2] / "docs" / "prompts"


def prompts_dir() -> Path:
    """仓库内 prompt 目录（``V3/docs/prompts``）。"""
    return _PROMPTS_DIR


@lru_cache(maxsize=64)
def load_prompt_file(stem: str) -> str:
    """
    读取 ``docs/prompts/{stem}.md`` 全文（UTF-8），首尾空白已去除。

    Args:
        stem: 不含扩展名的文件名，例如 ``event_press_user``。
    """
    path = _PROMPTS_DIR / f"{stem}.md"
    if not path.is_file():
        msg = f"prompt file missing: {path}"
        logger.error(msg)
        raise FileNotFoundError(msg)
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        raise ValueError(f"empty prompt file: {path}")
    return text


def clear_prompt_cache() -> None:
    """测试或热重载场景下清空 LRU 缓存。"""
    load_prompt_file.cache_clear()
