"""加载 ``src/services/zh_ingest/prompts/*.md``。"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

_PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"


@lru_cache(maxsize=16)
def load_zh_ingest_prompt(stem: str) -> str:
    path = _PROMPTS_DIR / f"{stem}.md"
    if not path.is_file():
        raise FileNotFoundError(f"zh_ingest prompt missing: {path}")
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        raise ValueError(f"empty zh_ingest prompt: {path}")
    return text


def clear_zh_ingest_prompt_cache() -> None:
    load_zh_ingest_prompt.cache_clear()
