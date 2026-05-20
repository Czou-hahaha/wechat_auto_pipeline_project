"""GDELT/RSS 命中在抓正文前的轻量主题过滤（标题+摘要，无 LLM）。"""
from __future__ import annotations

import re

from src.search import SearchHit

_CJK_KEYWORDS = (
    "低空",
    "无人机",
    "无人驾驶航空器",
    "民航局",
    "通用航空",
    "飞行汽车",
    "空域",
)

_LATIN_KEYWORDS = (
    "evtol",
    "uam",
    "drone",
    "uav",
)

# 地缘/战争类误召回（标题含 drone strike 等）
_WAR_GEO_MARKERS = (
    "iran",
    "israel",
    "gaza",
    "lebanon",
    "ukraine",
    "russia",
    "syria",
    "yemen",
    "tehran",
    "middle east",
    "nuclear plant",
    "导弹",
    "以军",
    "哈马斯",
    "俄乌",
)

_INDUSTRY_CONTEXT = (
    "evtol",
    "uam",
    "aam",
    "caac",
    "faa",
    "easa",
    "低空",
    "通航",
    "air taxi",
    "bvlos",
    "delivery drone",
    "urban air mobility",
)

# 战争/冲突战术（含 drone 误召回）
_WAR_CONFLICT_TITLE_RES = (
    re.compile(r"\b(kill\s*zone|war\s*zone|corridor|strike|conflict|invasion|offensive)\b", re.I),
    re.compile(r"\b(ukrainian|russian|nato|gaza|iran|israel|lebanon)\b.*\b(drone|missile)\b", re.I),
    re.compile(r"\b(drone|missile)\b.*\b(ukrainian|russian|nato|gaza|iran|israel)\b", re.I),
    re.compile(r"击落|走廊|杀伤|冲突|以军|俄军|乌军"),
)

# 电商促销/Deal 稿（非产业新闻）
_PROMO_TITLE_RES = (
    re.compile(r"\b(on sale|deal|discount|save\s*\$|record[- ]low|memorial day|black friday)\b", re.I),
    re.compile(r"\b(amazon|ebay|mashable)\b.*\b(drone|deal|price|save)\b", re.I),
    re.compile(r"\b(drone|evtol)\b.*\b(deal|price|save\s*\$|%\s*off)\b", re.I),
    re.compile(r"促销|打折|历史低价|省钱|特惠"),
)

_PROMO_HOSTS = frozenset(
    {
        "mashable.com",
        "ebay.com",
        "amazon.com",
        "www.amazon.com",
    }
)

# 监狱/走私/犯罪类「无人机」误召回
_PRISON_CRIME_MARKERS = (
    "prison",
    "jail",
    "inmate",
    "contraband",
    "smuggl",
    "penitentiary",
    "监狱",
    "看守所",
    "狱",
    "走私",
    "贩毒",
)

# 台湾时政/两岸（非产业政策语境）
_TAIWAN_POLITICS_MARKERS = (
    "taiwan",
    "台灣",
    "臺灣",
    "台湾",
    "台海",
    "赖清德",
    "賴清德",
    "蔡英文",
    "国民党",
    "國民黨",
    "民进党",
    "民進黨",
    "国安五法",
    "國安",
)

# 繁体媒体/域名
_TW_HK_HOST_SUFFIXES = (
    ".tw",
    ".hk",
)
_TRAD_MEDIA_MARKERS = (
    "聯合報",
    "自由時報",
    "中央社",
    "蘋果日報",
    "端傳媒",
    "TVBS",
    "東森",
)

# 抹黑/对抗性叙事（无产业政策语境时丢弃）
_ANTI_CHINA_NARRATIVE_RES = (
    re.compile(r"\b(china threat|beijing regime|counter\s*china|contain\s*china)\b", re.I),
    re.compile(r"(抹黑|唱衰|遏制中国|打压中国|威胁论)"),
)

# 简繁判断：标题中「繁体专用字」占比过高
_TRAD_ONLY_CHARS = frozenset(
    "臺國區體報導總統議會網絡訊號無機車東與國際貿易條約衛星應臺灣區域"
)

_CROSS_DOMAIN_NOISE = (
    "食品安全",
    "药品",
    "殡葬",
    "渔业",
    "基金",
    "烟花爆竹",
    "商事调解",
    "特种设备",
    "咖啡机",
    "mining subsidy",
    "矿产补贴",
    "矿业补贴",
    "iron ore",
    "coal subsidy",
)


def is_low_altitude_relevant_snippet(*, title: str, snippet: str, text: str = "") -> bool:
    blob = f"{title}\n{snippet}\n{text[:3000]}"
    blob_l = blob.lower()
    if any(k in blob for k in _CJK_KEYWORDS):
        return True
    return any(re.search(rf"\b{re.escape(k)}\b", blob_l) for k in _LATIN_KEYWORDS)


def is_war_conflict_headline(*, title: str, snippet: str) -> bool:
    blob = f"{title}\n{snippet}"
    blob_l = blob.lower()
    if any(rx.search(blob) for rx in _WAR_CONFLICT_TITLE_RES):
        if not any(m in blob_l or m in blob for m in _INDUSTRY_CONTEXT):
            return True
    war_hits = sum(1 for m in _WAR_GEO_MARKERS if m in blob_l or m in blob)
    if war_hits >= 1 and any(
        w in blob_l for w in ("strike", "shoot", "down", "war", "conflict", "missile", "击落", "冲突")
    ):
        if not any(m in blob_l or m in blob for m in _INDUSTRY_CONTEXT):
            return True
    return False


def is_commerce_promo_headline(*, title: str, snippet: str, url: str = "") -> bool:
    blob = f"{title}\n{snippet}"
    if any(rx.search(blob) for rx in _PROMO_TITLE_RES):
        return True
    try:
        from urllib.parse import urlparse

        host = (urlparse(url).hostname or "").lower()
        if host.startswith("www."):
            host = host[4:]
    except Exception:
        host = ""
    if host in _PROMO_HOSTS and any(
        w in blob.lower() for w in ("deal", "sale", "save", "price", "discount", "促销", "低价")
    ):
        return True
    return False


def _has_industry_context(blob: str, blob_l: str) -> bool:
    return any(m in blob_l or m in blob for m in _INDUSTRY_CONTEXT) or any(
        k in blob for k in _CJK_KEYWORDS
    )


def is_prison_crime_drone_headline(*, title: str, snippet: str) -> bool:
    blob = f"{title}\n{snippet}"
    blob_l = blob.lower()
    if not any(m in blob_l or m in blob for m in _PRISON_CRIME_MARKERS):
        return False
    if "drone" in blob_l or "无人机" in blob or "uav" in blob_l:
        return not _has_industry_context(blob, blob_l)
    return False


def is_taiwan_politics_headline(*, title: str, snippet: str, url: str = "") -> bool:
    blob = f"{title}\n{snippet}"
    blob_l = blob.lower()
    try:
        from urllib.parse import urlparse

        host = (urlparse(url).hostname or "").lower()
    except Exception:
        host = ""
    if host and any(host.endswith(s) for s in _TW_HK_HOST_SUFFIXES):
        if not _has_industry_context(blob, blob_l):
            return True
    tw_hits = sum(1 for m in _TAIWAN_POLITICS_MARKERS if m in blob or m.lower() in blob_l)
    if tw_hits >= 1 and not _has_industry_context(blob, blob_l):
        return True
    if any(m in blob for m in _TRAD_MEDIA_MARKERS) and not _has_industry_context(blob, blob_l):
        return True
    return False


def is_traditional_chinese_dominant(*, title: str, snippet: str = "", max_ratio: float = 0.12) -> bool:
    """标题（+可选摘要）繁体专用字占比过高 → 视为繁体稿。"""
    blob = f"{title}\n{snippet}"
    cjk = [c for c in blob if "\u4e00" <= c <= "\u9fff"]
    if len(cjk) < 6:
        return False
    trad = sum(1 for c in cjk if c in _TRAD_ONLY_CHARS)
    return (trad / len(cjk)) >= max_ratio


def is_anti_china_smear_headline(*, title: str, snippet: str) -> bool:
    blob = f"{title}\n{snippet}"
    if not any(rx.search(blob) for rx in _ANTI_CHINA_NARRATIVE_RES):
        return False
    return not _has_industry_context(blob, blob.lower())


def is_negative_regulation_clickbait(*, title: str, snippet: str) -> bool:
    """无产业语境的「中国打压/严管」标题党。"""
    blob = f"{title}\n{snippet}"
    blob_l = blob.lower()
    if not any(
        p in blob or p in blob_l
        for p in ("china crackdown", "china ban", "beijing crackdown", "严管", "打压", "封杀")
    ):
        return False
    if _has_industry_context(blob, blob_l):
        return False
    if any(k in blob for k in _CJK_KEYWORDS) or "drone" in blob_l or "evtol" in blob_l:
        return False
    return True


def is_obvious_offtopic_headline(*, title: str, snippet: str) -> bool:
    blob = f"{title}\n{snippet}"
    blob_l = blob.lower()
    war_hits = sum(1 for m in _WAR_GEO_MARKERS if m in blob_l or m in blob)
    if war_hits >= 2 and not any(m in blob_l or m in blob for m in _INDUSTRY_CONTEXT):
        return True
    if ("mining" in blob_l or "矿产" in blob or "矿业" in blob) and (
        "subsidy" in blob_l or "补贴" in blob
    ):
        if not is_low_altitude_relevant_snippet(title=title, snippet=snippet):
            return True
    cross = sum(1 for t in _CROSS_DOMAIN_NOISE if t in blob or t.lower() in blob_l)
    low_count = sum(blob.count(k) for k in _CJK_KEYWORDS)
    low_count += sum(len(re.findall(rf"\b{re.escape(k)}\b", blob_l)) for k in _LATIN_KEYWORDS)
    if cross >= 2 and low_count <= 2:
        return True
    return False


def should_keep_editorial_content(
    *,
    title: str,
    snippet: str = "",
    text: str = "",
    url: str = "",
) -> bool:
    """抓正文后/聚类前复用：战争、监狱、台湾时政、繁体、抹黑等。"""
    sn = snippet or text[:500]
    if is_war_conflict_headline(title=title, snippet=sn):
        return False
    if is_prison_crime_drone_headline(title=title, snippet=sn):
        return False
    if is_taiwan_politics_headline(title=title, snippet=sn, url=url):
        return False
    if is_traditional_chinese_dominant(title=title, snippet=sn):
        return False
    if is_anti_china_smear_headline(title=title, snippet=sn):
        return False
    if is_negative_regulation_clickbait(title=title, snippet=sn):
        return False
    if is_commerce_promo_headline(title=title, snippet=sn, url=url):
        return False
    if not _url_suggests_low_altitude(url):
        if not is_low_altitude_relevant_snippet(title=title, snippet=sn, text=text):
            return False
    if is_obvious_offtopic_headline(title=title, snippet=sn):
        return False
    return True


def _url_suggests_low_altitude(url: str) -> bool:
    u = (url or "").lower()
    return any(
        k in u
        for k in (
            "drone",
            "dji",
            "autel",
            "evtol",
            "uam",
            "aam",
            "fcc",
            "caac",
            "低空",
            "无人机",
            "无人驾驶",
            "飞行汽车",
        )
    )


def should_fetch_zh_media_hit(hit: SearchHit) -> bool:
    """中文科技/财经 RSS 用：只挡战争/监狱/台湾/繁体/抹黑等，不要求标题含「无人机」。"""
    title = (hit.title or "").strip()
    snippet = (hit.snippet or "").strip()
    url = hit.url or ""
    if is_war_conflict_headline(title=title, snippet=snippet):
        return False
    if is_prison_crime_drone_headline(title=title, snippet=snippet):
        return False
    if is_taiwan_politics_headline(title=title, snippet=snippet, url=url):
        return False
    if is_traditional_chinese_dominant(title=title, snippet=snippet):
        return False
    if is_anti_china_smear_headline(title=title, snippet=snippet):
        return False
    if is_negative_regulation_clickbait(title=title, snippet=snippet):
        return False
    if is_commerce_promo_headline(title=title, snippet=snippet, url=url):
        return False
    if is_obvious_offtopic_headline(title=title, snippet=snippet):
        return False
    return True


def should_fetch_search_hit(hit: SearchHit) -> bool:
    title = (hit.title or "").strip()
    snippet = (hit.snippet or "").strip()
    url = hit.url or ""
    # 固定 URL（如 FCC）可能尚无标题，用链接域名/路径做产业门
    if _url_suggests_low_altitude(url):
        return should_keep_editorial_content(
            title=title or "（待抓取标题）",
            snippet=snippet,
            url=url,
        )
    return should_keep_editorial_content(title=title, snippet=snippet, url=url)
