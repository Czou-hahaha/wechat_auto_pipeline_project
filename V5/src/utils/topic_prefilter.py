"""GDELT/RSS/正文抓取后的主题过滤（标题 + 摘要 + 全文，无 LLM）。"""
from __future__ import annotations

import re

from src.search import SearchHit

# 正文参与规则判断时的上限（字符）
EDITORIAL_FULL_TEXT_MAX = 12_000

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
    "drone",
    "uav",
)

_UAM_SCHOOL_RES = re.compile(r"\buam[- ]?ctc\b", re.I)
_UAM_INDUSTRY_RES = re.compile(r"\b(?:urban\s+air\s+mobility|air\s+taxi)\b", re.I)

_VOCATIONAL_OFFTOPIC_RES = (
    re.compile(r"\bskillsusa\b", re.I),
    re.compile(r"\b(pipe\s+)?welding\b", re.I),
    re.compile(r"\bwelding\s+(student|technology|instructor)\b", re.I),
    re.compile(r"焊接(专业|学生|技术|大赛)"),
    re.compile(r"职业技能大赛"),
)

_WAR_GEO_MARKERS = (
    "iran",
    "israel",
    "gaza",
    "lebanon",
    "ukraine",
    "ukrainian",
    "russia",
    "russian",
    "kyiv",
    "kiev",
    "syria",
    "yemen",
    "tehran",
    "middle east",
    "nuclear plant",
    "nato",
    "hamas",
    "hezbollah",
    "导弹",
    "以军",
    "哈马斯",
    "俄乌",
    "乌军",
    "俄军",
    "北约",
    "基辅",
    "普京",
    "泽连斯基",
    "波罗的海",
    "拉脱维亚",
    "爱沙尼亚",
    "立陶宛",
    "芬兰",
    "车臣",
    "顿涅茨克",
    "克里米亚",
)

_WAR_CONFLICT_ACTION = (
    "strike",
    "shoot down",
    "shot down",
    "war",
    "conflict",
    "invasion",
    "offensive",
    "missile",
    "artillery",
    "front line",
    "frontline",
    "ceasefire",
    "kill zone",
    "war zone",
    "corridor",
    "oil export",
    "refinery",
    "petroleum",
    "embargo",
    "sanctions",
    "击落",
    "冲突",
    "战争",
    "入侵",
    "前线",
    "炮击",
    "交火",
    "军事冲突",
    "占领",
    "打击",
    "误闯",
    "偏离航线",
    "政府垮台",
    "领空",
    "防空",
)

# 仅标题/短文本用的战术正则（正文仍走 geo+action 计数）
_WAR_CONFLICT_TITLE_RES = (
    re.compile(r"\b(kill\s*zone|war\s*zone|corridor|strike|conflict|invasion|offensive)\b", re.I),
    re.compile(r"\b(ukrainian|russian|nato|gaza|iran|israel|lebanon)\b.*\b(drone|missile)\b", re.I),
    re.compile(r"\b(drone|missile)\b.*\b(ukrainian|russian|nato|gaza|iran|israel)\b", re.I),
    re.compile(r"击落|走廊|杀伤|冲突|以军|俄军|乌军|俄乌战争|军事冲突"),
)

_PROMO_TITLE_RES = (
    re.compile(
        r"\b(on sale|deal\s+of|deal\s+for|discount|save\s*\$|record[- ]low|memorial day|black friday)\b",
        re.I,
    ),
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

# 主轴为治安/灾难/选举/体育，无人机仅为工具性提及（编辑原则：服务中国读者的产业叙事）
_NON_INDUSTRY_NARRATIVE_MARKERS = (
    # 治安 / 警用勤务
    "k-9",
    "k9 unit",
    "k9 team",
    "foot chase",
    "car chase",
    "police chase",
    "high-speed chase",
    "traffic stop",
    "manhunt",
    "sheriff",
    "deputy",
    "patrol deputy",
    "taken into custody",
    "fled on foot",
    "reckless driving",
    "track down",
    "shooting suspect",
    "hostage",
    "bank robbery",
    "警犬",
    "追捕",
    "逃犯",
    "刑警",
    "派出所",
    "交警",
    "通缉",
    # 灾难 / 突发
    "earthquake",
    "wildfire",
    "hurricane",
    "tornado",
    "flash flood",
    "mudslide",
    "tsunami",
    "地震",
    "山火",
    "洪灾",
    "泥石流",
    "台风",
    # 选举
    "election day",
    "polling station",
    "ballot",
    "presidential race",
    "campaign rally",
    "primary election",
    "选举",
    "投票",
    "大选",
    "竞选",
    # 体育
    "touchdown",
    "world cup",
    "playoff game",
    "championship game",
    "super bowl",
    "nba finals",
    "mlb",
    "欧冠",
    "世界杯",
    "全运会",
)

_NON_INDUSTRY_NARRATIVE_RES = (
    re.compile(r"\b(k-9|k9)\b", re.I),
    re.compile(r"\b(foot|car|police)\s+chase\b", re.I),
    re.compile(r"\btraffic\s+stop\b", re.I),
    re.compile(r"\b(sheriff|deputy).{0,40}\b(drone|uav)\b", re.I),
    re.compile(r"\b(drone|uav).{0,40}\b(sheriff|deputy|k-9|k9)\b", re.I),
)

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

_TW_HK_HOST_SUFFIXES = (".tw", ".hk")

_TRAD_MEDIA_MARKERS = (
    "聯合報",
    "自由時報",
    "中央社",
    "蘋果日報",
    "端傳媒",
    "TVBS",
    "東森",
)

_ANTI_CHINA_NARRATIVE_RES = (
    re.compile(r"\b(china threat|beijing regime|counter\s*china|contain\s*china)\b", re.I),
    re.compile(r"(抹黑|唱衰|遏制中国|打压中国|威胁论)"),
)

_TRAD_ONLY_CHARS = frozenset(
    "臺國區體報導總統議會網絡訊號無機車東與國際貿易條約衛星應臺灣區域"
)

_WAR_GEO_STRICT = (
    "ukraine",
    "ukrainian",
    "russia",
    "russian",
    "kyiv",
    "kiev",
    "nato",
    "gaza",
    "israel",
    "iran",
    "hamas",
    "hezbollah",
    "俄乌",
    "乌军",
    "俄军",
    "北约",
    "基辅",
    "泽连斯基",
    "普京",
    "波罗的海",
    "拉脱维亚",
    "爱沙尼亚",
    "立陶宛",
    "芬兰领空",
    "车臣",
    "顿涅茨克",
    "克里米亚",
)

_WAR_GEO_SOFT = (
    "syria",
    "yemen",
    "tehran",
    "lebanon",
    "middle east",
    "north africa",
)

_AAM_INDUSTRY_MARKERS = (
    "evtol",
    "vertiport",
    "air taxi",
    "air mobility",
    "urban air mobility",
    "advanced air mobility",
    "aam",
    "bvlos",
    "drone-in-a-box",
    "低空",
    "无人机",
    "飞行汽车",
    "适航",
    "certification",
)

# 产业政策/监管（可豁免「含无人机」的战争误召回；不含裸 uam）
_CIVIL_INDUSTRY_STRONG = (
    "evtol",
    "urban air mobility",
    "air taxi",
    "caac",
    "faa",
    "easa",
    "bvlos",
    "delivery drone",
    "低空经济",
    "民航局",
    "通航",
    "飞行汽车",
    "certification",
    "rulemaking",
    "firmware waiver",
    "covered list",
    "part 107",
    "运营合格证",
    "适航",
)

# 正文尾部侧栏/推荐阅读（抓取噪声，常含无关战争标题）
_SCRAPE_CHROME_MARKERS = (
    "\nrecommended articles",
    "\ndiscover more from",
    "\nrecent chats",
    "\nyou've reached your free preview",
    "\nshare via email",
    "\nsubmenu here",
)

_LISTICLE_WAR_LINE = re.compile(
    r"^-\s*\d+\s*(Ukraine|Russia|Gaza|Iran|Israel|Hamas)\b",
    re.I | re.M,
)

_EXTRA_RELEVANCE_PHRASES = (
    "unmanned aircraft",
    "unmanned aerial",
    "multirotor",
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

# 消费级游戏/AR 应用：标题或侧栏带 drone，主轴却是手游扫描、玩家贡献数据等（非低空产业）
_CONSUMER_GAMING_DRONE_BAIT_MARKERS = (
    "pokémon go",
    "pokemon go",
    "pokémon",
    "pokemon",
    "niantic spatial",
    "niantic",
    "mobile game",
    "video game",
    "game developer",
    "augmented reality game",
    "ar scan",
    "ar mapping",
    "pikachu",
    "ingress",
    "players unwittingly",
    "crowdsourced images",
    "30 billion photos",
    "world model",
    "宝可梦",
    "口袋妖怪",
    "手游",
    "游戏玩家",
    "实景扫描",
)

_CONSUMER_GAMING_DRONE_BAIT_RES = (
    re.compile(r"\b(pok[eé]mon\s+go|pok[eé]mon)\b", re.I),
    re.compile(r"\bniantic(?:\s+spatial)?\b", re.I),
    re.compile(r"\b(mobile|video)\s+game\b", re.I),
    re.compile(r"\bar\s+(scan|mapping|scans)\b", re.I),
)


def strip_scrape_chrome(text: str) -> str:
    """去掉正文尾部推荐阅读/付费墙等抓取噪声（避免侧栏战争标题误拦）。"""
    raw = (text or "").strip()
    if not raw:
        return raw
    lower = raw.lower()
    cut_at = len(raw)
    for marker in _SCRAPE_CHROME_MARKERS:
        idx = lower.find(marker)
        if idx >= 0:
            cut_at = min(cut_at, idx)
    trimmed = raw[:cut_at].strip()
    lines: list[str] = []
    for line in trimmed.splitlines():
        if _LISTICLE_WAR_LINE.match(line.strip()):
            continue
        lines.append(line)
    return "\n".join(lines).strip()


def editorial_content_blob(
    *,
    title: str,
    snippet: str = "",
    text: str = "",
    max_chars: int = EDITORIAL_FULL_TEXT_MAX,
) -> tuple[str, str]:
    """
    合并标题与正文用于规则判断。
    有抓取正文时优先用全文（截断至 max_chars），避免仅看标题/摘要漏拦。
    """
    t = (title or "").strip()
    body = strip_scrape_chrome(text)
    if len(body) >= 200:
        core = f"{t}\n{body[:max_chars]}"
    else:
        sn = (snippet or body or "").strip()
        core = f"{t}\n{sn[:max_chars]}"
    return core, core.lower()


def _marker_hits(blob: str, blob_l: str, markers: tuple[str, ...]) -> int:
    hits = 0
    for m in markers:
        if not m:
            continue
        if any("\u4e00" <= c <= "\u9fff" for c in m):
            if m in blob:
                hits += 1
        elif re.search(rf"\b{re.escape(m)}\b", blob_l):
            hits += 1
    return hits


def _aam_industry_density(blob: str, blob_l: str) -> int:
    return _marker_hits(blob, blob_l, _AAM_INDUSTRY_MARKERS)


def _has_civil_industry_exemption(blob: str, blob_l: str) -> bool:
    """明确产业政策/监管或 AAM 产业稿，且全文主叙事不是战争冲突。"""
    civil = _marker_hits(blob, blob_l, _CIVIL_INDUSTRY_STRONG)
    aam = _aam_industry_density(blob, blob_l)
    if civil < 1 and aam < 2:
        return False
    strict_geo = _marker_hits(blob, blob_l, _WAR_GEO_STRICT)
    action = _marker_hits(blob, blob_l, _WAR_CONFLICT_ACTION)
    if strict_geo >= 1 and action >= 1:
        return False
    if strict_geo >= 2:
        return False
    return True


def _latin_uam_is_industry(blob_l: str) -> bool:
    if _UAM_SCHOOL_RES.search(blob_l):
        return False
    if _UAM_INDUSTRY_RES.search(blob_l):
        return True
    return bool(re.search(r"\buam\b", blob_l))


def latin_low_altitude_keyword_hit(*, title: str, snippet: str, text: str = "") -> bool:
    blob, blob_l = editorial_content_blob(title=title, snippet=snippet, text=text)
    if any(re.search(rf"\b{re.escape(k)}\b", blob_l) for k in _LATIN_KEYWORDS):
        return True
    if any(p in blob_l for p in _EXTRA_RELEVANCE_PHRASES):
        return True
    return _latin_uam_is_industry(blob_l)


def is_war_conflict_content(*, title: str, snippet: str = "", text: str = "") -> bool:
    """战争/地缘冲突报道（基于标题+摘要+全文）。"""
    blob, blob_l = editorial_content_blob(title=title, snippet=snippet, text=text)
    if _has_civil_industry_exemption(blob, blob_l):
        return False
    if _aam_industry_density(blob, blob_l) >= 3 and _marker_hits(blob, blob_l, _WAR_GEO_STRICT) == 0:
        return False
    if any(rx.search(blob) for rx in _WAR_CONFLICT_TITLE_RES):
        return True
    strict_hits = _marker_hits(blob, blob_l, _WAR_GEO_STRICT)
    soft_hits = _marker_hits(blob, blob_l, _WAR_GEO_SOFT)
    action_hits = _marker_hits(blob, blob_l, _WAR_CONFLICT_ACTION)
    if strict_hits >= 1 and action_hits >= 1:
        return True
    if strict_hits >= 2:
        return True
    if soft_hits >= 1 and action_hits >= 2 and _aam_industry_density(blob, blob_l) < 2:
        return True
    if any(x in blob for x in ("俄乌", "乌军", "俄军", "北约秘书长")) and (
        action_hits >= 1 or "无人机" in blob or "drone" in blob_l
    ):
        return True
    return False


def is_military_war_drone_content(*, title: str, snippet: str = "", text: str = "") -> bool:
    """战场中的军用无人机（全文检测，含仅标题含无人机的长文战争稿）。"""
    blob, blob_l = editorial_content_blob(title=title, snippet=snippet, text=text)
    has_drone = "drone" in blob_l or "uav" in blob_l or "无人机" in blob
    if not has_drone:
        return False
    if _has_civil_industry_exemption(blob, blob_l):
        return False
    if is_war_conflict_content(title=title, snippet=snippet, text=text):
        return True
    if _marker_hits(blob, blob_l, _WAR_GEO_STRICT) >= 1 and _marker_hits(blob, blob_l, _WAR_CONFLICT_ACTION) >= 1:
        return True
    return False


# 兼容旧名
is_war_conflict_headline = is_war_conflict_content
is_military_war_drone_headline = is_military_war_drone_content


def is_vocational_education_offtopic(*, title: str, snippet: str = "", text: str = "") -> bool:
    blob, blob_l = editorial_content_blob(title=title, snippet=snippet, text=text)
    if not any(rx.search(blob) for rx in _VOCATIONAL_OFFTOPIC_RES):
        return False
    if any(k in blob for k in _CJK_KEYWORDS):
        return False
    if latin_low_altitude_keyword_hit(title=title, snippet=snippet, text=text):
        return False
    if "drone" in blob_l or "uav" in blob_l or "evtol" in blob_l:
        return False
    return True


def is_low_altitude_relevant_snippet(*, title: str, snippet: str, text: str = "") -> bool:
    blob, _ = editorial_content_blob(title=title, snippet=snippet, text=text)
    if any(k in blob for k in _CJK_KEYWORDS):
        return True
    return latin_low_altitude_keyword_hit(title=title, snippet=snippet, text=text)


def is_commerce_promo_headline(*, title: str, snippet: str, url: str = "", text: str = "") -> bool:
    blob, _ = editorial_content_blob(title=title, snippet=snippet, text=text, max_chars=4000)
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


def is_prison_crime_drone_headline(*, title: str, snippet: str, text: str = "") -> bool:
    blob, blob_l = editorial_content_blob(title=title, snippet=snippet, text=text)
    if not _marker_hits(blob, blob_l, _PRISON_CRIME_MARKERS):
        return False
    if "drone" in blob_l or "无人机" in blob or "uav" in blob_l:
        return not _has_civil_industry_exemption(blob, blob_l)
    return False


def is_consumer_gaming_drone_bait_content(
    *, title: str, snippet: str = "", text: str = ""
) -> bool:
    """
    消费级游戏/AR 应用稿：标题或摘要带 drone，正文主轴却是手游扫描、玩家贡献地图等。

    典型误召回：Pokémon Go / Niantic Spatial 用手机 AR 扫描训练 AI，标题却写
    「drone photos」；与低空经济/民用无人机产业无关。
    """
    blob, blob_l = editorial_content_blob(title=title, snippet=snippet, text=text)
    if _has_civil_industry_exemption(blob, blob_l):
        return False
    if _aam_industry_density(blob, blob_l) >= 2:
        return False
    gaming_hits = _marker_hits(blob, blob_l, _CONSUMER_GAMING_DRONE_BAIT_MARKERS)
    gaming_regex = any(rx.search(blob) for rx in _CONSUMER_GAMING_DRONE_BAIT_RES)
    if gaming_hits < 1 and not gaming_regex:
        return False
    has_drone = "drone" in blob_l or "uav" in blob_l or "无人机" in blob
    title_blob = f"{title}\n{snippet}".lower()
    title_drone_bait = "drone" in title_blob or "无人机" in title or "uav" in title_blob
    if has_drone:
        if title_drone_bait or gaming_hits >= 2:
            return True
        return bool(gaming_regex and gaming_hits >= 1)
    # 中文标题常不含 drone，但 Niantic/宝可梦/实景扫描等游戏主轴仍须拦
    if gaming_hits >= 2 or (gaming_regex and gaming_hits >= 1):
        return _aam_industry_density(blob, blob_l) < 1
    return False


def is_non_industry_narrative_drone_content(
    *, title: str, snippet: str = "", text: str = ""
) -> bool:
    """
    主轴为治安/灾难/选举/体育，仅因出现 drone 而入库的非产业叙事。

    编辑原则：主轴须为低空经济/民用无人机产业；产业监管/适航/商业化语境可豁免。
    """
    blob, blob_l = editorial_content_blob(title=title, snippet=snippet, text=text)
    has_drone = "drone" in blob_l or "uav" in blob_l or "无人机" in blob
    if not has_drone:
        return False
    if _has_civil_industry_exemption(blob, blob_l):
        return False
    if _aam_industry_density(blob, blob_l) >= 2:
        return False
    if _marker_hits(blob, blob_l, _NON_INDUSTRY_NARRATIVE_MARKERS) >= 1:
        return True
    return any(rx.search(blob) for rx in _NON_INDUSTRY_NARRATIVE_RES)


def is_taiwan_politics_headline(*, title: str, snippet: str, url: str = "", text: str = "") -> bool:
    blob, blob_l = editorial_content_blob(title=title, snippet=snippet, text=text)
    try:
        from urllib.parse import urlparse

        host = (urlparse(url).hostname or "").lower()
    except Exception:
        host = ""
    if host and any(host.endswith(s) for s in _TW_HK_HOST_SUFFIXES):
        if not _has_civil_industry_exemption(blob, blob_l):
            return True
    tw_hits = _marker_hits(blob, blob_l, _TAIWAN_POLITICS_MARKERS)
    if tw_hits >= 1 and not _has_civil_industry_exemption(blob, blob_l):
        return True
    if any(m in blob for m in _TRAD_MEDIA_MARKERS) and not _has_civil_industry_exemption(blob, blob_l):
        return True
    return False


def is_traditional_chinese_dominant(*, title: str, snippet: str = "", text: str = "", max_ratio: float = 0.12) -> bool:
    blob, _ = editorial_content_blob(title=title, snippet=snippet, text=text, max_chars=2000)
    cjk = [c for c in blob if "\u4e00" <= c <= "\u9fff"]
    if len(cjk) < 6:
        return False
    trad = sum(1 for c in cjk if c in _TRAD_ONLY_CHARS)
    return (trad / len(cjk)) >= max_ratio


def is_anti_china_smear_headline(*, title: str, snippet: str, text: str = "") -> bool:
    blob, blob_l = editorial_content_blob(title=title, snippet=snippet, text=text)
    if not any(rx.search(blob) for rx in _ANTI_CHINA_NARRATIVE_RES):
        return False
    return not _has_civil_industry_exemption(blob, blob_l)


def is_negative_regulation_clickbait(*, title: str, snippet: str, text: str = "") -> bool:
    blob, blob_l = editorial_content_blob(title=title, snippet=snippet, text=text)
    if not any(
        p in blob or p in blob_l
        for p in ("china crackdown", "china ban", "beijing crackdown", "严管", "打压", "封杀")
    ):
        return False
    if _has_civil_industry_exemption(blob, blob_l):
        return False
    if any(k in blob for k in _CJK_KEYWORDS) or "drone" in blob_l or "evtol" in blob_l:
        return False
    return True


def is_obvious_offtopic_headline(*, title: str, snippet: str, text: str = "") -> bool:
    blob, blob_l = editorial_content_blob(title=title, snippet=snippet, text=text)
    if is_consumer_gaming_drone_bait_content(title=title, snippet=snippet, text=text):
        return True
    if is_non_industry_narrative_drone_content(title=title, snippet=snippet, text=text):
        return True
    if is_war_conflict_content(title=title, snippet=snippet, text=text):
        return True
    if ("mining" in blob_l or "矿产" in blob or "矿业" in blob) and (
        "subsidy" in blob_l or "补贴" in blob
    ):
        if not is_low_altitude_relevant_snippet(title=title, snippet=snippet, text=text):
            return True
    cross = _marker_hits(blob, blob_l, _CROSS_DOMAIN_NOISE)
    low_count = sum(blob.count(k) for k in _CJK_KEYWORDS)
    low_count += sum(len(re.findall(rf"\b{re.escape(k)}\b", blob_l)) for k in _LATIN_KEYWORDS)
    if cross >= 2 and low_count <= 2:
        return True
    return False


def should_keep_stored_record(
    *,
    title: str,
    snippet: str = "",
    text: str = "",
    url: str = "",
) -> bool:
    """
    已入库数据清理用：有抓取正文则走完整门禁；正文为空（如已推微信后清空）
    时仅执行战争/职业技能/监狱等硬规则，不因标题未含「无人机」误删投资稿。
    """
    body = (text or "").strip()
    if len(body) >= 200:
        return should_keep_editorial_content(
            title=title, snippet=snippet, text=text, url=url
        )
    if is_war_conflict_content(title=title, snippet=snippet, text=body):
        return False
    if is_military_war_drone_content(title=title, snippet=snippet, text=body):
        return False
    if is_vocational_education_offtopic(title=title, snippet=snippet, text=body):
        return False
    if is_prison_crime_drone_headline(title=title, snippet=snippet, text=body):
        return False
    if is_non_industry_narrative_drone_content(title=title, snippet=snippet, text=body):
        return False
    if is_consumer_gaming_drone_bait_content(title=title, snippet=snippet, text=body):
        return False
    if is_taiwan_politics_headline(title=title, snippet=snippet, text=body, url=url):
        return False
    if is_traditional_chinese_dominant(title=title, snippet=snippet, text=body):
        return False
    if is_anti_china_smear_headline(title=title, snippet=snippet, text=body):
        return False
    if is_negative_regulation_clickbait(title=title, snippet=snippet, text=body):
        return False
    if is_commerce_promo_headline(title=title, snippet=snippet, text=body, url=url):
        return False
    if is_obvious_offtopic_headline(title=title, snippet=snippet, text=body):
        return False
    return True


def should_keep_editorial_content(
    *,
    title: str,
    snippet: str = "",
    text: str = "",
    url: str = "",
) -> bool:
    """抓正文前/后、聚类、IMP 复用：战争、非产业叙事、监狱、台湾时政、繁体、抹黑等。"""
    if is_war_conflict_content(title=title, snippet=snippet, text=text):
        return False
    if is_military_war_drone_content(title=title, snippet=snippet, text=text):
        return False
    if is_vocational_education_offtopic(title=title, snippet=snippet, text=text):
        return False
    if is_prison_crime_drone_headline(title=title, snippet=snippet, text=text):
        return False
    if is_non_industry_narrative_drone_content(title=title, snippet=snippet, text=text):
        return False
    if is_consumer_gaming_drone_bait_content(title=title, snippet=snippet, text=text):
        return False
    if is_taiwan_politics_headline(title=title, snippet=snippet, text=text, url=url):
        return False
    if is_traditional_chinese_dominant(title=title, snippet=snippet, text=text):
        return False
    if is_anti_china_smear_headline(title=title, snippet=snippet, text=text):
        return False
    if is_negative_regulation_clickbait(title=title, snippet=snippet, text=text):
        return False
    if is_commerce_promo_headline(title=title, snippet=snippet, text=text, url=url):
        return False
    if not _url_suggests_low_altitude(url):
        if not is_low_altitude_relevant_snippet(title=title, snippet=snippet, text=text):
            return False
    if is_obvious_offtopic_headline(title=title, snippet=snippet, text=text):
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
    title = (hit.title or "").strip()
    snippet = (hit.snippet or "").strip()
    url = hit.url or ""
    return should_keep_editorial_content(title=title, snippet=snippet, url=url)


def should_fetch_search_hit(hit: SearchHit) -> bool:
    title = (hit.title or "").strip()
    snippet = (hit.snippet or "").strip()
    url = hit.url or ""
    if _url_suggests_low_altitude(url):
        return should_keep_editorial_content(
            title=title or "（待抓取标题）",
            snippet=snippet,
            url=url,
        )
    return should_keep_editorial_content(title=title, snippet=snippet, url=url)
