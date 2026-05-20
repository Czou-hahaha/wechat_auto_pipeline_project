"""公众号摘要：重点句 <strong> 与微信草稿 HTML。"""
from __future__ import annotations

import re
from html import escape

_STRONG_TAG_RE = re.compile(r"<strong>(.*?)</strong>", re.DOTALL | re.IGNORECASE)
_BOLD_MD_RE = re.compile(r"\*\*(.+?)\*\*", re.DOTALL)
_INCONSISTENCY_RE = re.compile(
    r"[。！？\n]*[^。！？\n]*(?:报道口径不一致|口径不一致|来源矛盾|各家说法)[^。！？\n]*[。！？]?",
    re.IGNORECASE,
)
_UI_CITATION_RE = re.compile(r"〔\d+〕|【\d+】|\[\d+\]")


def strip_ui_citation_markers(text: str) -> str:
    """去掉阅读态段落引用标记，避免进入草稿箱 digest/content。"""
    out = _UI_CITATION_RE.sub("", text or "")
    out = re.sub(r"  +", " ", out)
    out = re.sub(r"\n{3,}", "\n\n", out)
    return out.strip()


def sanitize_summary_text(text: str) -> str:
    """存储/QA 用：规范化高亮标签，去掉口径不一致元叙述。"""
    out = strip_ui_citation_markers(text or "")
    out = out.replace("\r\n", "\n").replace("\r", "\n")
    out = _BOLD_MD_RE.sub(r"<strong>\1</strong>", out)
    out = _INCONSISTENCY_RE.sub("", out)
    out = re.sub(r"</?strong>", lambda m: m.group(0).lower(), out, flags=re.IGNORECASE)
    # 剥除非 strong 的 HTML
    out = re.sub(r"<(?!/?strong>)[^>]+>", "", out, flags=re.IGNORECASE)
    out = out.replace("**", "")
    out = re.sub(r"\n{3,}", "\n\n", out)
    return "\n".join(line.rstrip() for line in out.split("\n")).strip()


def _paragraph_to_wechat_html(paragraph: str) -> str:
    """转义正文，仅保留 <strong> 标签。"""
    parts: list[str] = []
    last = 0
    for m in _STRONG_TAG_RE.finditer(paragraph):
        if m.start() > last:
            parts.append(escape(paragraph[last : m.start()]))
        inner = escape(m.group(1))
        parts.append(f"<strong>{inner}</strong>")
        last = m.end()
    if last < len(paragraph):
        parts.append(escape(paragraph[last:]))
    return "".join(parts) if parts else escape(paragraph)


def summary_to_wechat_html_body(summary: str) -> str:
    """多段摘要 → 微信草稿 content 字段 HTML（不含免责声明尾注）。"""
    plain = sanitize_summary_text(summary)
    blocks: list[str] = []
    for para in plain.split("\n\n"):
        p = para.strip()
        if not p:
            continue
        inner = _paragraph_to_wechat_html(p).replace("\n", "<br/>")
        blocks.append(f"<p>{inner}</p>")
    return "".join(blocks) if blocks else "<p></p>"


def summary_plain_for_digest(summary: str) -> str:
    """草稿 digest 用纯文本（去掉标签）。"""
    s = sanitize_summary_text(summary)
    s = _STRONG_TAG_RE.sub(r"\1", s)
    return re.sub(r"\s+", " ", s).strip()


def summary_visible_char_count(summary: str) -> int:
    """摘要可见字数（不含 HTML 标签与空白），与 prompt「计数字不含 HTML 标签」一致。"""
    s = sanitize_summary_text(summary)
    s = _STRONG_TAG_RE.sub(r"\1", s)
    return len(re.sub(r"\s+", "", s))
