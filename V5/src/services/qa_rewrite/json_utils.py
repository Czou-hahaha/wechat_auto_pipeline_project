"""从模型输出中提取并解析 JSON 对象。"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)


def strip_code_fence(text: str) -> str:
    s = (text or "").strip()
    if s.startswith("```"):
        s = re.sub(r"^```(?:json)?\s*", "", s, flags=re.IGNORECASE)
        s = re.sub(r"\s*```$", "", s)
    return s.strip()


def extract_first_json_object(text: str) -> dict[str, Any] | None:
    """
    从可能含前后噪声的文本中取出第一个顶层 JSON object。

    优先整段 ``json.loads``；失败则自第一个 ``{`` 起做括号扫描。
    """
    s = strip_code_fence(text)
    if not s:
        return None
    try:
        val = json.loads(s)
        return val if isinstance(val, dict) else None
    except json.JSONDecodeError:
        pass

    start = s.find("{")
    if start < 0:
        return None
    depth = 0
    in_str = False
    esc = False
    quote = ""
    for i in range(start, len(s)):
        ch = s[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == quote:
                in_str = False
                quote = ""
            continue
        if ch in ('"', "'"):
            in_str = True
            quote = ch
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                chunk = s[start : i + 1]
                try:
                    val = json.loads(chunk)
                    return val if isinstance(val, dict) else None
                except json.JSONDecodeError:
                    logger.warning("json slice parse failed len=%d", len(chunk))
                    return None
    return None
