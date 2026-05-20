"""Build search blurbs and expansion plain phrases / GDELT query strings (no LLM)."""
from __future__ import annotations

import re
from typing import Iterable


def _strip_site_suffix(title: str) -> str:
    t = (title or "").strip()
    t = re.sub(r"\s*[-|｜]\s*[^-|｜]{1,40}$", "", t)
    return t.strip()


def build_search_blurb(
    event_title: str,
    member_titles: Iterable[str],
    *,
    max_chars: int = 1200,
    max_titles: int = 6,
) -> str:
    parts: list[str] = [_strip_site_suffix(event_title)]
    seen: set[str] = set()
    for raw in member_titles:
        t = _strip_site_suffix(str(raw))
        if not t or t in seen:
            continue
        seen.add(t)
        parts.append(t)
        if len(parts) >= max_titles + 1:
            break
    blob = "\n".join(parts)
    if len(blob) > max_chars:
        blob = blob[:max_chars]
    return blob


def gdelt_format_or_term(raw: str) -> str:
    t = str(raw or "").strip().replace('"', "")
    if not t:
        return ""
    if re.search(r"\s", t):
        return f'"{t}"'
    return f"({t})"


def gdelt_build_or_query(terms: list[str]) -> str:
    parts: list[str] = []
    for term in terms:
        frag = gdelt_format_or_term(term)
        if frag:
            parts.append(frag)
    if not parts:
        return ""
    return "(" + " OR ".join(parts) + ")"


def extract_candidate_terms(blurb: str, *, max_terms: int = 6) -> list[str]:
    """从 blurb 抽中英文词/短语，保序去重。"""
    raw = blurb or ""
    found = re.findall(r"[\u4e00-\u9fff]{2,}|[a-zA-Z][a-zA-Z0-9\-]{2,}", raw)
    out: list[str] = []
    seen: set[str] = set()
    for w in found:
        w2 = w.strip()
        if len(w2) < 2 or w2.lower() in seen:
            continue
        seen.add(w2.lower())
        out.append(w2)
        if len(out) >= max_terms:
            break
    return out


def strip_gdelt_query_lang_suffix(query: str) -> str:
    """Strip trailing ``sourcelang:*`` for non-GDELT backends (e.g. DDGS plain text)."""
    return re.sub(r"\s+sourcelang:\w+\s*$", "", (query or "").strip(), flags=re.I).strip()


def limit_english_words(text: str, max_words: int) -> str:
    """Trim to at most ``max_words`` whitespace-separated tokens."""
    t = _strip_site_suffix(text or "")
    t = re.sub(r"[《》【】\[\]]", "", t).strip()
    if max_words <= 0 or not t:
        return t
    words = t.split()
    if len(words) > max_words:
        t = " ".join(words[:max_words])
    return t.rstrip(".,;:")


def format_english_event_title(
    event_title: str,
    member_titles: Iterable[str] | None = None,
    *,
    max_words: int = 20,
) -> str:
    """
    English event label for storage and expansion: one line, at most ``max_words`` tokens.
    Merges up to two member headlines when they add distinct wording.
    """
    parts: list[str] = []
    seen: set[str] = set()
    for raw in [event_title, *(member_titles or [])]:
        t = _strip_site_suffix(str(raw or ""))
        if not t:
            continue
        key = t.lower()
        if key in seen:
            continue
        seen.add(key)
        parts.append(t)
        if len(parts) >= 3:
            break
    blob = " ".join(parts)
    return limit_english_words(blob, max_words)


def _primary_anchor_term(anchor_terms: list[str], *, override: str | None) -> str:
    o = (override or "").strip()
    if o:
        return o
    for a in anchor_terms:
        a = (a or "").strip()
        if not a:
            continue
        if re.search(r"[\u4e00-\u9fff]", a):
            return a
    if anchor_terms:
        return str(anchor_terms[0]).strip() or "低空经济"
    return "低空经济"


def build_expansion_plain_phrase(
    *,
    event_title: str,
    anchor_terms: list[str],
    event_title_max_chars: int | None,
    primary_anchor: str | None,
    event_lang: str = "zh",
    max_english_words: int = 20,
) -> str:
    """
    扩搜检索词（纯文本，无 AND/括号）：

    - ``zh``：``{截断后事件名} {主锚}``（默认主锚含「低空经济」）
    - ``en``：仅英文事件名，最多 ``max_english_words`` 个词，不拼中文锚词
    """
    lang = (event_lang or "zh").strip().lower()
    if lang == "en":
        return format_english_event_title(event_title, max_words=max_english_words)
    anchor = _primary_anchor_term(anchor_terms, override=primary_anchor)
    et = _strip_site_suffix(event_title)
    et = re.sub(r"[《》【】\[\]]", "", et).strip()
    if event_title_max_chars is not None and int(event_title_max_chars) > 0:
        et = et[: int(event_title_max_chars)]
    et = et.strip()
    if not et:
        return anchor
    return f"{et} {anchor}".strip()


def gdelt_chinese_query_from_plain(plain: str) -> str:
    """宽召回：纯文本 query，语言过滤在本地完成。"""
    return (plain or "").strip()


def gdelt_english_query_from_plain(plain: str) -> str:
    return (plain or "").strip()


def gdelt_query_from_plain(plain: str, *, lang: str) -> str:
    """``lang`` in ``zh`` | ``en``；扩搜对 zh event 默认不调用 GDELT。"""
    _ = lang
    return (plain or "").strip()


def build_gdelt_query_strings(
    *,
    event_title: str,
    member_titles: list[str],
    anchor_terms: list[str],
    event_title_max_chars: int | None = 15,
    include_member_titles_in_query: bool = False,
    max_or_terms: int = 4,
    primary_anchor: str | None = None,
) -> list[str]:
    """兼容旧调用：等价于 ``[gdelt_chinese_query_from_plain(build_expansion_plain_phrase(...))]``。"""
    _ = (member_titles, include_member_titles_in_query, max_or_terms)
    plain = build_expansion_plain_phrase(
        event_title=event_title,
        anchor_terms=anchor_terms,
        event_title_max_chars=event_title_max_chars,
        primary_anchor=primary_anchor,
    )
    q = gdelt_chinese_query_from_plain(plain)
    return [q] if q else []
