"""栏目页（HTML 列表）抓取：从 ``data_sources.json`` 的 ``list_monitor_url`` 抽取稿件链接，输出 ``SearchHit``。"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse
from zoneinfo import ZoneInfo

import httpx
from bs4 import BeautifulSoup

from src.search import SearchHit, _is_blocked_url, normalize_snippet, normalize_title
from src.utils.http_decode import decode_http_html_bytes

logger = logging.getLogger(__name__)

# 与常见反爬策略兼容：部分站点对非浏览器 UA 返回 403（如 FAA Akamai）
DEFAULT_INGEST_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

_ASSET_EXT = re.compile(r"\.(jpg|jpeg|png|gif|webp|svg|ico|pdf|zip|rar|css|js|woff2?)(\?|$)", re.I)
_NAV_TITLES = frozenset(
    {
        "首页",
        "更多",
        "下一页",
        "上一页",
        "下一頁",
        "上一頁",
        "english",
        "繁體中文",
        "简体中文",
        "register",
        "sign in",
        "search",
    }
)

_FAA_NEWSROOM_HUB = re.compile(
    r"^/newsroom/(statements|speeches|testimony|conferences-events|fact-sheets)(/|$)",
    re.I,
)


def _host_matches_site(url: str, site_value: str) -> bool:
    raw_site = (site_value or "").strip().lower().replace("https://", "").replace("http://", "").strip("/")
    if "/" in raw_site:
        raw_site = raw_site.split("/", 1)[0]
    if raw_site.startswith("www."):
        raw_site = raw_site[4:]
    host = (urlparse(url).hostname or "").lower()
    if not host or not raw_site:
        return False
    if host == raw_site:
        return True
    return host.endswith("." + raw_site)


def _article_like_path(url: str, site_value: str) -> bool:
    try:
        pr = urlparse(url)
    except Exception:
        return False
    path = pr.path or ""
    low = url.lower()
    host = (pr.hostname or "").lower()
    if _ASSET_EXT.search(path):
        return False
    if any(x in low for x in ("/login", "/signin", "/register", "javascript:", "mailto:")):
        return False

    if re.search(r"t20\d{6}_\d+\.html?", path, re.I):
        return True
    if re.search(r"content_\d+\.htm", path, re.I):
        return True
    if "/post_" in path and path.lower().endswith(".html"):
        return True
    if "/art/art_" in path and path.lower().endswith(".html"):
        return True
    if "miit.gov.cn" in host and "art_" in path.lower() and path.lower().endswith(".html") and "/art/" in path.lower():
        return True
    if "cls.cn" in host and re.search(r"/detail/\d+", path):
        return True
    if "dji.com" in host and "/media-center/" in path and (
        "/announcements/" in path or "/media-coverage/" in path
    ):
        return True
    if "ehang.com" in host and "news-release-details" in path:
        return True
    if "easa.europa.eu" in host and "/news/" in path and path.lower().rstrip("/") not in (
        "/en/newsroom-and-events/news",
        "/en/newsroom-and-events/news/",
    ):
        tail = path.lower().split("/news/", 1)[-1]
        if tail and len(tail) > 12:
            return True
    if "faa.gov" in host and "/newsroom/" in path:
        if _FAA_NEWSROOM_HUB.search(path):
            return False
        m = re.match(r"^/newsroom/([^/]+)/?", path, re.I)
        if not m:
            return False
        slug = m.group(1)
        if slug in {"newsroom", "updates", "index"}:
            return False
        return len(slug) >= 18 and "-" in slug
    if "spectrum.ieee.org" in host and "/topic/" not in path.lower():
        slug = path.strip("/").split("/")[-1] if path.strip("/") else ""
        return len(slug) >= 18 and slug not in {"aerospace", "spectrum", "ieee", "topic"}
    if "caac.gov.cn" in host and ".html" in path.lower() and "/xwzx/" in path.lower():
        return True
    if "uavcoach.com" in host and path.count("/") >= 2 and len(path) > 15:
        if any(path.lower().startswith(p) for p in ("/wp-", "/category/", "/tag/", "/author/")):
            return False
        if path.rstrip("/").split("/")[-1] in {"feed", "rss", "shop", "cart"}:
            return False
        return bool(re.search(r"/\d{4}/", path)) or len(path.strip("/").split("/")[-1]) > 20
    return False


def _iso_from_article_url(url: str) -> str:
    """从常见政务稿件 URL 中的 ``tYYYYMMDD_`` 片段推断本地日历日，转 UTC ISO（日界按 Asia/Shanghai）。"""
    m = re.search(r"t(\d{8})_\d+", url, re.I)
    if not m:
        return ""
    ymd = m.group(1)
    if len(ymd) != 8:
        return ""
    try:
        y, mo, d = int(ymd[:4]), int(ymd[4:6]), int(ymd[6:8])
        dt = datetime(y, mo, d, 0, 0, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
        return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    except Exception:
        return ""


def _iso_from_time_datetime_attr(raw: str) -> str:
    """解析 HTML5 ``<time datetime=\"...\">`` 常见写法，统一为带 UTC 偏移的 ISO 字符串。"""
    s = (raw or "").strip()
    if not s:
        return ""
    try:
        dtp = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dtp.tzinfo is None:
            dtp = dtp.replace(tzinfo=timezone.utc)
        return dtp.astimezone(timezone.utc).isoformat()
    except Exception:
        return ""


_ISO_DAY_RE = re.compile(r"\b(20\d{2})-(\d{2})-(\d{2})\b")
_ZH_YMD_RE = re.compile(r"(20\d{2})年(\d{1,2})月(\d{1,2})日")
_EN_MONTH_DAY_YEAR = re.compile(
    r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2}),?\s+(20\d{2})\b",
    re.I,
)
_MONTH_MAP = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}


def _iso_calendar_shanghai(y: int, mo: int, d: int) -> str:
    """仅日历日时按 Asia/Shanghai 正午落盘，避免纯日边界误判。"""
    try:
        dt = datetime(y, mo, d, 12, 0, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
        return dt.astimezone(timezone.utc).isoformat()
    except Exception:
        return ""


def _extract_textual_date_iso(container: object) -> str:
    """从容器可见文本抽取首个日期（``YYYY-MM-DD`` / 中文年月日 / 英文月名）。"""
    get_text = getattr(container, "get_text", None)
    if not callable(get_text):
        return ""
    blob = get_text(separator=" ", strip=True)
    if len(blob) > 1500:
        blob = blob[:1500]
    m = _ISO_DAY_RE.search(blob)
    if m:
        return _iso_calendar_shanghai(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    m = _ZH_YMD_RE.search(blob)
    if m:
        return _iso_calendar_shanghai(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    m = _EN_MONTH_DAY_YEAR.search(blob)
    if m:
        mon = _MONTH_MAP.get(m.group(1).casefold(), 0)
        if mon:
            return _iso_calendar_shanghai(int(m.group(3)), mon, int(m.group(2)))
    return ""


def _meta_date_in_container(container: object) -> str:
    """列表块内 ``meta`` 常见发布时间字段。"""
    find_all = getattr(container, "find_all", None)
    if not callable(find_all):
        return ""
    for m in find_all("meta"):
        prop = (m.get("property") or "").strip().lower()
        name = (m.get("name") or "").strip().lower()
        itemp = (m.get("itemprop") or "").strip().lower()
        if prop != "article:published_time" and name != "pubdate" and itemp != "datepublished":
            continue
        raw = (m.get("content") or m.get("datetime") or "").strip()
        if not raw:
            continue
        iso = _iso_from_time_datetime_attr(raw)
        if iso:
            return iso
        sm = _ISO_DAY_RE.search(raw)
        if sm:
            return _iso_calendar_shanghai(int(sm.group(1)), int(sm.group(2)), int(sm.group(3)))
    return ""


def _is_descendant_of(node: object, ancestor: object) -> bool:
    p = node
    for _ in range(120):
        if p is None:
            return False
        if p is ancestor:
            return True
        p = getattr(p, "parent", None)
    return False


def _ordered_article_anchor_tags(container: object, *, base_url: str, site_value: str) -> list[object]:
    out: list[object] = []
    find_all = getattr(container, "find_all", None)
    if not callable(find_all):
        return out
    for a in find_all("a", href=True):
        if _anchor_article_candidate(a, base_url=base_url, site_value=site_value) is not None:
            out.append(a)
    return out


def _ordered_time_tags(container: object) -> list[object]:
    select = getattr(container, "select", None)
    if not callable(select):
        return []
    return list(select("time[datetime]"))


def _pub_from_list_container(
    container: object,
    anchor: object,
    *,
    base_url: str,
    site_value: str,
) -> str:
    """在同一列表块（``container``）内，为 ``anchor`` 推断 ``published_at``。"""
    if not _is_descendant_of(anchor, container):
        return ""
    links = _ordered_article_anchor_tags(container, base_url=base_url, site_value=site_value)
    if anchor not in links:
        return ""
    idx = links.index(anchor)
    times = _ordered_time_tags(container)
    if times:
        if len(times) == len(links) >= 1:
            return _iso_from_time_datetime_attr(times[idx].get("datetime") or "")
        if len(links) == 1:
            return _iso_from_time_datetime_attr(times[0].get("datetime") or "")
        if len(times) == 1 and len(links) <= 8:
            return _iso_from_time_datetime_attr(times[0].get("datetime") or "")
        if idx < len(times):
            return _iso_from_time_datetime_attr(times[idx].get("datetime") or "")
    meta_pub = _meta_date_in_container(container)
    if meta_pub and len(links) <= 8:
        return meta_pub
    if len(links) > 10:
        return ""
    return _extract_textual_date_iso(container)


def _extract_pub_near_anchor(anchor: object, *, base_url: str, site_value: str) -> str:
    """自链接向上遍历父级，在最小可用块内抽取列表常见时间（``time`` / ``meta`` / 文本日期）。"""
    cur = getattr(anchor, "parent", None)
    for _ in range(16):
        if cur is None:
            break
        name = getattr(cur, "name", None)
        if name in ("body", "html", "[document]"):
            break
        got = _pub_from_list_container(cur, anchor, base_url=base_url, site_value=site_value)
        if got:
            return got
        cur = getattr(cur, "parent", None)
    return ""


def _anchor_article_candidate(
    a: object,
    *,
    base_url: str,
    site_value: str,
) -> tuple[str, str] | None:
    """若 ``<a>`` 指向一条可收录的稿件，返回 ``(绝对 URL, 标题)``，否则 ``None``。"""
    get_href = getattr(a, "get", None)
    if not callable(get_href):
        return None
    raw_href = (get_href("href") or "").strip()
    if not raw_href or raw_href.startswith("#"):
        return None
    abs_url = urljoin(base_url, raw_href).split("#")[0].strip()
    if not abs_url.startswith("http"):
        return None
    if _is_blocked_url(abs_url):
        return None
    if not _host_matches_site(abs_url, site_value):
        return None
    if not _article_like_path(abs_url, site_value):
        return None
    get_text = getattr(a, "get_text", None)
    raw_title = get_text() if callable(get_text) else ""
    title = (raw_title or "").strip()
    title = re.sub(r"\s+", " ", title)
    if len(title) < 10 or len(title) > 300:
        return None
    low = title.casefold()
    if low in _NAV_TITLES or title in _NAV_TITLES:
        return None
    return abs_url, title


def _extract_candidates(html: str, base_url: str, site_value: str, *, cap: int = 400) -> list[tuple[str, str, str]]:
    """返回 ``(url, title, published_at_hint)``。

    对每条稿件链接：先尝试所在 ``views-row`` 的 ``<time datetime>``；再自链接向上在父级容器内抽取
    ``time``/``meta``/可见文本日期（与链接条数启发式对齐）；最后回退 URL ``tYYYYMMDD_``。
    """
    soup = BeautifulSoup(html, "html.parser")
    by_url: dict[str, tuple[str, str]] = {}

    def _upsert(url: str, title: str, pub_hint: str) -> None:
        prev = by_url.get(url)
        url_pub = _iso_from_article_url(url)
        merged_pub = (pub_hint or "").strip() or url_pub
        if prev is None:
            by_url[url] = (title, merged_pub)
            return
        old_title, old_pub = prev
        if not (old_pub or "").strip() and merged_pub:
            by_url[url] = (old_title, merged_pub)

    for row in soup.select("div.views-row"):
        row_pub = ""
        t_el = row.find("time", attrs={"datetime": True})
        if t_el is not None:
            row_pub = _iso_from_time_datetime_attr(t_el.get("datetime") or "")
        for a in row.find_all("a", href=True):
            got = _anchor_article_candidate(a, base_url=base_url, site_value=site_value)
            if got is None:
                continue
            u, t = got
            near = row_pub or _extract_pub_near_anchor(a, base_url=base_url, site_value=site_value)
            _upsert(u, t, near)
            if len(by_url) >= cap:
                return [(u2, t2, p2) for u2, (t2, p2) in by_url.items()]

    for a in soup.find_all("a", href=True):
        got = _anchor_article_candidate(a, base_url=base_url, site_value=site_value)
        if got is None:
            continue
        u, t = got
        near = _extract_pub_near_anchor(a, base_url=base_url, site_value=site_value)
        _upsert(u, t, near)
        if len(by_url) >= cap:
            break
    return [(u, t, p) for u, (t, p) in by_url.items()]


def _text_matches_any_keyword(haystack: str, keywords: list[str]) -> bool:
    """词表命中（与 RSS 一致：ASCII 用大小写不敏感子串，中文用子串）。"""
    if not keywords:
        return True
    blob = haystack or ""
    for k in keywords:
        kw = (k or "").strip()
        if not kw:
            continue
        ascii_only = all(ord(c) < 128 for c in kw)
        if ascii_only:
            if kw.casefold() in blob.casefold():
                return True
        elif kw in blob:
            return True
    return False


async def fetch_html_list_hits(
    client: httpx.AsyncClient,
    *,
    list_url: str,
    site_value: str,
    per_feed_max: int,
    keywords: list[str] | None,
    relevance_filter: bool,
    source_name: str,
) -> list[SearchHit]:
    """GET 栏目页，解析稿件链接。

    关键词：在 ``relevance_filter`` 为真时，**仅对文章标题**（``normalize_title`` 后）做与 RSS 相同的词表匹配。
    ``published_at``：每条链接必经「列表块内时间解析」——自父级向上尝试 ``<time datetime>``、与条数对齐的
    ``time`` 序列、``meta`` 日期、容器内可见文本日期（``YYYY-MM-DD``/中文年月日/英文月名），再回退 URL ``tYYYYMMDD_``；
    入库仍以 pipeline 落地页解析为准。
    """
    try:
        resp = await client.get(list_url, headers={"User-Agent": DEFAULT_INGEST_UA})
        resp.raise_for_status()
    except Exception:
        logger.warning("html list fetch failed name=%s url=%s", source_name, list_url[:120], exc_info=True)
        return []

    html = decode_http_html_bytes(
        resp.content,
        content_type=str(resp.headers.get("content-type") or ""),
        httpx_encoding=str(resp.encoding or ""),
    )
    triples = _extract_candidates(html, str(resp.url), site_value, cap=500)
    rows: list[SearchHit] = []
    for url, title, pub_hint in triples:
        nt = normalize_title(title)
        snippet = normalize_snippet("")[:2000]
        if relevance_filter and keywords:
            if not _text_matches_any_keyword(nt, keywords):
                continue
        pub = (pub_hint or "").strip() or _iso_from_article_url(url)
        rows.append(
            SearchHit(title=nt, url=url, snippet=snippet, published_at=pub, from_rss=True),
        )
        if len(rows) >= per_feed_max:
            break
    if rows:
        logger.info("html list ok name=%s url=%s rows=%d", source_name, list_url[:80], len(rows))
    else:
        logger.info("html list empty name=%s url=%s", source_name, list_url[:80])
    return rows
