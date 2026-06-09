"""中文事件/通稿标题：短标题（约 12–28 字），避免摘要首句当标题。"""
from __future__ import annotations

import re

DEFAULT_MAX_ZH_HEADLINE = 28


def zh_visible_len(text: str) -> int:
    """标题有效长度：汉字计 1，其它可见字符计 0.5（向上取整）。"""
    s = re.sub(r"<[^>]+>", "", (text or "").strip())
    if not s:
        return 0
    cjk = len(re.findall(r"[\u4e00-\u9fff]", s))
    other = len(re.sub(r"[\u4e00-\u9fff\s]", "", s))
    return cjk + (other + 1) // 2


def is_overlong_zh_headline(text: str, *, max_len: int = DEFAULT_MAX_ZH_HEADLINE) -> bool:
    return zh_visible_len(text) > max_len


def first_zh_sentence(text: str) -> str:
    s = re.sub(r"<[^>]+>", "", (text or "").strip())
    if not s:
        return ""
    return re.split(r"[。！？\n]", s, maxsplit=1)[0].strip()


def trim_zh_headline_heuristic(text: str, *, max_len: int = DEFAULT_MAX_ZH_HEADLINE) -> str:
    """规则截短：优先在逗号处截断，否则硬截到 max_len。"""
    s = re.sub(r"<[^>]+>", "", (text or "").strip())
    if not s or not is_overlong_zh_headline(s, max_len=max_len):
        return s
    for sep in ("，", ",", "、", "；", ";", "：", ":"):
        parts = s.split(sep)
        acc = ""
        for i, part in enumerate(parts):
            chunk = (sep if acc else "") + part if acc else part
            trial = acc + chunk if acc else part
            if zh_visible_len(trial) <= max_len:
                acc = trial
            else:
                break
        if acc and 6 <= zh_visible_len(acc) <= max_len:
            return acc.rstrip("，,、；;：:")
    out: list[str] = []
    for ch in s:
        out.append(ch)
        if zh_visible_len("".join(out)) >= max_len:
            break
    return "".join(out).rstrip("，,、；;：:")
