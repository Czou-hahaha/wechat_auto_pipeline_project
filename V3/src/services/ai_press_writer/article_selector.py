"""按来源优先级与转载去重，为单个 event 选取 top_k 篇稿件进模型。"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# 数字越小优先级越高（1 最先保留）
TIER_OFFICIAL = 1
TIER_WIRE = 2
TIER_TECH = 3
TIER_CN_MEDIA = 4
TIER_OTHER = 5

_OFFICIAL_SUFFIXES = (".gov.cn", ".gov.uk", ".gouv.fr", ".go.jp")
_OFFICIAL_HOST_MARKERS = (
    "europa.eu",
    "state.gov",
    "whitehouse.gov",
    "fda.gov",
    "fcc.gov",
    "nasa.gov",
    "icao.int",
    "who.int",
    "un.org",
)

_WIRE_HOST_SUBSTRINGS = (
    "reuters.com",
    "reuters.co",
    "apnews.com",
    "ap.org",
    "hosted.ap.org",
)

_TECH_HOST_SUBSTRINGS = (
    "techcrunch.com",
    "theverge.com",
    "arstechnica.com",
    "wired.com",
    "engadget.com",
    "theregister.com",
    "36kr.com",
    "geekpark.net",
    "ifanr.com",
    "leiphone.com",
    "solidot.org",
    "ithome.com",
    "cnbeta.com",
    "infoq.cn",
    "tech.sina.com.cn",
    "technode.com",
    "zdnet.com",
    "venturebeat.com",
)

_CN_MEDIA_HOST_SUBSTRINGS = (
    "people.com.cn",
    "xinhuanet.com",
    "news.cn",
    "cctv.com",
    "chinadaily.com.cn",
    "china.com.cn",
    "chinanews.com.cn",
    "thepaper.cn",
    "yicai.com",
    "caixin.com",
    "qq.com",
    "sina.com.cn",
    "sohu.com",
    "eastday.com",
    "stcn.com",
    "nbd.com.cn",
    "jiemian.com",
    "cls.cn",
    "wallstreetcn.com",
    "huanqiu.com",
    "guancha.cn",
)


def _host_from_article(row: dict[str, Any]) -> str:
    raw = str(row.get("source_host") or "").strip().lower()
    if raw:
        return raw
    for key in ("resolved_url", "source_url"):
        u = str(row.get(key) or "").strip()
        if not u:
            continue
        try:
            h = (urlparse(u).netloc or "").lower()
            if h.startswith("www."):
                h = h[4:]
            return h
        except Exception:
            continue
    return ""


def source_tier_for_host(host: str) -> int:
    """返回来源层级（越小越优先）。"""
    h = (host or "").lower()
    if not h:
        return TIER_OTHER
    if h.endswith(_OFFICIAL_SUFFIXES) or any(h == m or h.endswith("." + m) for m in _OFFICIAL_HOST_MARKERS):
        return TIER_OFFICIAL
    if any(s in h for s in _WIRE_HOST_SUBSTRINGS):
        return TIER_WIRE
    if any(s in h for s in _TECH_HOST_SUBSTRINGS):
        return TIER_TECH
    if any(s in h for s in _CN_MEDIA_HOST_SUBSTRINGS):
        return TIER_CN_MEDIA
    return TIER_OTHER


@dataclass
class SelectedArticle:
    """供 prompt 使用的单条材料。"""

    article_id: str
    source_label: str
    title: str
    body: str
    tier: int
    canonical_url: str = ""


def _norm_title(title: str) -> str:
    t = re.sub(r"\s+", "", (title or "").lower())
    return re.sub(r"[^\w\u4e00-\u9fff]", "", t)


def _body_prefix(text: str, n: int = 900) -> str:
    s = re.sub(r"\s+", " ", (text or "").strip())
    return s[:n]


def _is_near_duplicate(a: SelectedArticle, b: SelectedArticle) -> bool:
    """转载/同题重复：标题或正文开头高度重合则视为重复。"""
    ta, tb = _norm_title(a.title), _norm_title(b.title)
    if len(ta) >= 10 and len(tb) >= 10 and SequenceMatcher(None, ta, tb).ratio() >= 0.92:
        return True
    pa, pb = _body_prefix(a.body), _body_prefix(b.body)
    if len(pa) >= 200 and len(pb) >= 200 and SequenceMatcher(None, pa, pb).ratio() >= 0.88:
        return True
    return False


def _canonical_url(row: dict[str, Any]) -> str:
    return str(row.get("resolved_url") or row.get("source_url") or "").strip()


def select_articles_for_event(
    rows: list[dict[str, Any]],
    *,
    top_k: int = 5,
    mode: str = "top_k_dedupe",
    max_articles_in_prompt: int = 20,
) -> list[SelectedArticle]:
    """
    从同一 event 下的多篇 ``articles.json`` 行中选取进入 user prompt 的稿件摘录。

    **事件**由调用方已限定（同一 ``event_id`` 的 ``rows``）；本函数只决定**哪些篇**、**以何顺序**
    写入 prompt，不是「选事件」。

    * ``top_k_dedupe``（默认）：官方 > 通讯社 > 技术媒体 > 中文媒体 > 其他；去掉标题或正文开头
      高相似的转载；最多 ``top_k`` 篇（与早期「避免 token 爆炸 / 避免重复转载」规格一致）。
    * ``all_by_tier``：同一排序，**不做**高相似去重，只去掉 **canonical_url 完全相同** 的重复行；
      最多 ``max_articles_in_prompt`` 篇，便于「事件下素材尽量都给模型」；单篇是否截断由
      ``format_articles_block(..., per_article_max_chars)`` 决定（``0`` 表示全文）。
    """
    m = (mode or "top_k_dedupe").strip().lower()
    if m not in ("top_k_dedupe", "all_by_tier"):
        m = "top_k_dedupe"
    k = max(1, min(int(top_k), 12))
    cap_all = max(1, min(int(max_articles_in_prompt), 60))

    candidates: list[SelectedArticle] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        aid = str(row.get("id") or "").strip()
        title = str(row.get("title") or "").strip() or "未命名"
        body = str(row.get("extracted_text") or row.get("summary") or "").strip()
        if not body and not title:
            continue
        host = _host_from_article(row)
        tier = source_tier_for_host(host)
        label = host or "unknown"
        candidates.append(
            SelectedArticle(
                article_id=aid,
                source_label=label,
                title=title,
                body=body,
                tier=tier,
                canonical_url=_canonical_url(row),
            )
        )
    # 稳定排序：层级升序；同层正文更长优先（通常信息更完整）
    candidates.sort(key=lambda x: (x.tier, -len(x.body), x.source_label))
    picked: list[SelectedArticle] = []
    if m == "all_by_tier":
        seen_url: set[str] = set()
        for c in candidates:
            u = (c.canonical_url or "").strip()
            if u:
                if u in seen_url:
                    continue
                seen_url.add(u)
            picked.append(c)
            if len(picked) >= cap_all:
                break
        logger.info(
            "article_selector: mode=all_by_tier raw=%d picked=%d max=%d",
            len(candidates),
            len(picked),
            cap_all,
        )
        return picked

    for c in candidates:
        if any(_is_near_duplicate(c, p) for p in picked):
            continue
        picked.append(c)
        if len(picked) >= k:
            break
    if len(picked) < len(candidates):
        logger.info(
            "article_selector: mode=top_k_dedupe raw=%d picked=%d top_k=%d",
            len(candidates),
            len(picked),
            k,
        )
    return picked


def article_rows_to_qa_sources(
    article_rows: list[dict[str, Any]],
    *,
    selection_mode: str = "all_by_tier",
    top_k: int = 5,
    max_articles_in_prompt: int = 20,
    per_article_max_chars: int = 0,
) -> list[dict[str, str]]:
    """
    与通稿 writer 同源选文，转为阶段五 QA/重写所需的 ``{title, url, body}`` 列表。
    """
    raw_mode = (selection_mode or "all_by_tier").strip().lower()
    mode = raw_mode if raw_mode in ("top_k_dedupe", "all_by_tier") else "all_by_tier"
    selected = select_articles_for_event(
        article_rows,
        top_k=top_k,
        mode=mode,
        max_articles_in_prompt=max_articles_in_prompt,
    )
    cap = int(per_article_max_chars)
    out: list[dict[str, str]] = []
    for a in selected:
        body = (a.body or "").strip()
        if cap > 0:
            body = body[: max(1, cap)]
        url = (a.canonical_url or "").strip() or (a.source_label or "").strip()
        out.append({"title": a.title, "url": url, "body": body})
    return out


def format_articles_block(selected: list[SelectedArticle], *, per_article_max_chars: int) -> str:
    """格式化为 prompt 中的「相关文章」文本块。

    ``per_article_max_chars <= 0`` 表示**不截断**该篇正文，整段 ``extracted_text`` 进入 prompt。
    """
    parts: list[str] = []
    cap = int(per_article_max_chars)
    for i, a in enumerate(selected, start=1):
        raw = (a.body or "").strip()
        if cap > 0:
            body = raw[: max(1, cap)]
        else:
            body = raw
        block = (
            f"【来源 {i}】站点：{a.source_label}\n"
            f"标题：{a.title}\n"
            f"正文摘录：\n{body}"
        )
        parts.append(block)
    return "\n\n---\n\n".join(parts)
