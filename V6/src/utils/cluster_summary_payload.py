"""为簇摘要组 prompt 载荷：限篇数、摘录长度，并附带来源链接。"""
from __future__ import annotations

from urllib.parse import urlparse


def _article_url(row: dict) -> str:
    return str(row.get("resolved_url") or row.get("source_url") or "").strip()


def _pick_summary_sources(
    rows: list[dict],
    *,
    max_sources: int,
    url_roles: dict[str, str] | None = None,
) -> list[dict]:
    """优先 primary，再按正文长度降序，最多 ``max_sources`` 篇。"""
    if not rows:
        return []
    roles = url_roles or {}
    cap = max(1, int(max_sources))

    def sort_key(r: dict) -> tuple[int, int]:
        url = _article_url(r)
        is_primary = 1 if roles.get(url) == "primary" else 0
        text_len = len(str(r.get("extracted_text") or ""))
        return (is_primary, text_len)

    ordered = sorted(rows, key=sort_key, reverse=True)
    out: list[dict] = []
    seen_urls: set[str] = set()
    for row in ordered:
        url = _article_url(row)
        if url and url in seen_urls:
            continue
        if url:
            seen_urls.add(url)
        out.append(row)
        if len(out) >= cap:
            break
    return out


def build_cluster_summary_items(
    rows: list[dict],
    *,
    max_sources: int = 5,
    excerpt_chars: int = 1500,
    url_roles: dict[str, str] | None = None,
) -> list[dict[str, str]]:
    """
    供 ``summarize_cluster`` 使用。

    - 最多 ``max_sources`` 篇（非全文 7 篇灌 prompt）
    - 每篇：标题 + 链接 + 正文摘录（模型无法自行打开链接，须给摘录）
    """
    picked = _pick_summary_sources(rows, max_sources=max_sources, url_roles=url_roles)
    cap = max(400, int(excerpt_chars))
    items: list[dict[str, str]] = []
    for row in picked:
        url = _article_url(row)
        host = str(row.get("source_host") or "").strip()
        if not host and url:
            host = (urlparse(url).hostname or "").lower()
        body = str(row.get("extracted_text") or "").strip()
        if body.startswith("【事件增强"):
            continue
        excerpt = body[:cap]
        link_line = f"链接：{url}\n" if url else ""
        text = f"{link_line}正文摘录：\n{excerpt}"
        items.append(
            {
                "title": str(row.get("title") or ""),
                "text": text,
                "source_host": host,
                "source_url": url,
            }
        )
    return items
