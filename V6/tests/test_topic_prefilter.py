"""抓正文前主题过滤。"""
from __future__ import annotations

from src.search import SearchHit
from src.utils.topic_prefilter import (
    is_consumer_gaming_drone_bait_content,
    is_military_war_drone_content,
    is_non_industry_narrative_drone_content,
    is_obvious_offtopic_headline,
    is_prison_crime_drone_headline,
    is_taiwan_politics_headline,
    is_traditional_chinese_dominant,
    is_vocational_education_offtopic,
    is_war_conflict_content,
    should_fetch_search_hit,
    should_keep_editorial_content,
)


def test_rejects_war_drone_strike_without_industry_context() -> None:
    hit = SearchHit(
        title="Iran drone strike hits UAE nuclear plant",
        url="https://example.com/a",
        snippet="Middle East conflict escalates",
        published_at="2026-05-19T00:00:00Z",
    )
    assert not should_fetch_search_hit(hit)


def test_keeps_evtol_headline() -> None:
    hit = SearchHit(
        title="FAA advances eVTOL air taxi certification path",
        url="https://example.com/b",
        snippet="Urban air mobility operators await rulemaking",
        published_at="2026-05-19T00:00:00Z",
    )
    assert should_fetch_search_hit(hit)


def test_rejects_mining_subsidy_noise() -> None:
    assert is_obvious_offtopic_headline(
        title="Mining subsidy overhaul in iron ore sector",
        snippet="Government adjusts coal subsidy rules",
    )


def test_rejects_forbes_war_corridor() -> None:
    hit = SearchHit(
        title="Russians Establish Drone Corridors Through Ukrainian Kill Zones",
        url="https://www.forbes.com/example",
        snippet="",
        published_at="2026-05-19T00:00:00Z",
    )
    assert not should_fetch_search_hit(hit)


def test_rejects_mashable_deal() -> None:
    hit = SearchHit(
        title="The DJI Neo drone hits record - low price at Amazon - save $30",
        url="https://mashable.com/article/deal",
        snippet="Memorial Day sale",
        published_at="2026-05-19T00:00:00Z",
    )
    assert not should_fetch_search_hit(hit)


def test_rejects_police_chase_drone_spot_news() -> None:
    title = (
        "K-9 and drone teams track down teen after I-94 crash "
        "and foot chase in Battle Creek"
    )
    assert is_non_industry_narrative_drone_content(title=title, snippet="wwmt.com")
    assert not should_fetch_search_hit(
        SearchHit(
            title=title,
            url="https://wwmt.com/news/local/k-9-and-drone-teams",
            snippet="Calhoun County Sheriff",
            published_at="2026-05-24T00:00:00Z",
        )
    )


def test_rejects_sports_drone_flyover() -> None:
    title = "Drone flies over Super Bowl halftime show"
    assert is_non_industry_narrative_drone_content(title=title, snippet="NFL championship")
    assert not should_keep_editorial_content(title=title, snippet="")


def test_keeps_law_enforcement_bvlos_policy() -> None:
    title = "FAA grants BVLOS waiver for police department drone dock inspections"
    assert not is_non_industry_narrative_drone_content(
        title=title,
        snippet="Part 107 rulemaking certification",
    )
    assert should_keep_editorial_content(title=title, snippet="FAA BVLOS waiver")


def test_rejects_prison_drone_operator() -> None:
    assert is_prison_crime_drone_headline(
        title="Prison ‘drone operator’ held",
        snippet="contraband smuggled into jail",
    )
    assert not should_keep_editorial_content(
        title="Prison ‘drone operator’ held",
        snippet="contraband",
        url="https://example.com/p",
    )


def test_rejects_taiwan_politics_without_industry() -> None:
    assert is_taiwan_politics_headline(
        title="台海局势最新：军方回应",
        snippet="两岸关系",
        url="https://news.example.tw/a",
    )


def test_rejects_traditional_chinese_headline() -> None:
    assert is_traditional_chinese_dominant(
        title="無人機產業在臺灣的發展與挑戰",
        snippet="",
    )


def test_keeps_fcc_drone_policy() -> None:
    assert should_keep_editorial_content(
        title="FCC just saved millions of DJI drones from going obsolete",
        snippet="firmware waiver drone operators",
        url="https://dronedj.com/a",
    )


def test_rejects_ukraine_oil_export_drone_war() -> None:
    title = "Europe faces stray Ukrainian drones as Kyiv targets Russian oil exports"
    assert is_military_war_drone_content(title=title, snippet="NATO F-16 shot down drone")
    assert not should_keep_editorial_content(title=title, snippet="Baltic stray drones")


def test_rejects_chinese_war_in_full_body_neutral_title() -> None:
    title = "空域安全观察"
    body = (
        "乌克兰无人机在打击俄罗斯石油出口设施的过程中，因俄方电子干扰偏离航线，"
        "近期多次侵入波罗的海三国及芬兰领空。北约调动战斗机击落进入爱沙尼亚领空的无人机。"
        "拉脱维亚政府垮台。乌克兰副国防部长称2026年将生产超过700万架无人机。"
    ) * 3
    assert is_war_conflict_content(title=title, text=body)
    assert not should_keep_editorial_content(title=title, text=body)


def test_rejects_skillsusa_full_welding_body() -> None:
    title = "校园科技活动报道"
    body = (
        "Five UAM-CTC Welding Students dominate at 2026 SkillsUSA. "
        "Joseph Kyle Petrus won gold in pipe welding. Donnie DuBose praised welding students."
    ) * 2
    assert is_vocational_education_offtopic(title=title, text=body)
    assert not should_keep_editorial_content(title=title, text=body)


def test_rejects_skillsusa_uam_ctc_welding() -> None:
    title = "Five UAM-CTC Welding Students dominate at 2026 SkillsUSA"
    assert is_vocational_education_offtopic(title=title, snippet="pipe welding gold medal")
    assert not should_fetch_search_hit(
        SearchHit(
            title=title,
            url="https://stuttgartdailyleader.com/skillsusa",
            snippet="Arkansas welding competition",
            published_at="2026-05-21T00:00:00Z",
        )
    )


def test_keeps_fcc_drone_not_war_ukraine() -> None:
    assert should_keep_editorial_content(
        title="FCC just saved millions of DJI drones from going obsolete",
        snippet="firmware waiver drone operators",
        url="https://dronedj.com/a",
    )
    assert not is_military_war_drone_content(
        title="FCC firmware waiver for DJI and Autel drones",
        snippet="Covered List operators",
    )


def test_supernal_article_kept_after_stripping_sidebar_war_listicle() -> None:
    title = "Hyundai's air mobility firm Supernal sets sights on US air taxi plant"
    body = (
        "Hyundai's Supernal plans eVTOL air taxis targeting FAA certification. " * 12
        + "\nRecommended Articles\n"
        + "- 1Ukraine hits Russia with massive 500-drone strike in Moscow\n"
    )
    assert should_keep_editorial_content(title=title, text=body)


def test_keeps_evtol_middle_east_vertiport_fulltext() -> None:
    title = "Bayanat Engineering meteorological sensing at Dubai eVTOL vertiport"
    body = (
        "Advanced Air Mobility vertiport in Dubai United Arab Emirates. "
        "Middle East deployment of eVTOL weather sensors for commercial air taxi operations. " * 5
    )
    assert not is_war_conflict_content(title=title, text=body)
    assert should_keep_editorial_content(title=title, text=body)


def test_keeps_airbility_uav_press_with_preview_wall() -> None:
    title = "Airbility , KARI Sign UAV Hybrid Power System Tech Transfer Deal"
    body = (
        "Airbility announced technology transfer with KARI for hybrid UAV eVTOL platforms. "
        "The AB-U60 is a vectored-thrust eVTOL for surveillance and anti-drone operations. "
    ) * 8 + "\nYou've reached your free preview limit\nCreate an account to continue"
    assert should_keep_editorial_content(title=title, text=body)


def test_keeps_uk_sora_bvlos_fulltext() -> None:
    title = "DJI Dock 3 and UK SORA: Unlock BVLOS drone-in-a-box deployment"
    body = (
        "UK SORA offers a structured approach to BVLOS drone operations. "
        "DJI Dock 3 mitigates ground and air risk for civil certification. " * 8
    )
    assert should_keep_editorial_content(title=title, text=body)


def test_keeps_pinned_url_without_title() -> None:
    hit = SearchHit(
        title="",
        url="https://dronedj.com/2026/05/18/dji-autel-fcc-drone-firmware/",
        snippet="",
        published_at="2026-05-19T00:00:00Z",
    )
    assert should_fetch_search_hit(hit)


def test_rejects_pokemon_go_drone_photos_bait_title() -> None:
    title = "Pokémon Go creator wants your drone photos to train AI"
    snippet = "Niantic Spatial uses player AR scans for robotics maps"
    body = (
        "The company behind Pokémon Go is making a bet on artificial intelligence. "
        "Niantic Spatial, the spinoff from the creator of the global mobile gaming phenomenon "
        "Pokémon Go, has partnered with Spexi. Players upload AR scan videos at level 20. "
    ) * 4
    assert is_consumer_gaming_drone_bait_content(title=title, snippet=snippet, text=body)
    assert not should_fetch_search_hit(
        SearchHit(
            title=title,
            url="https://dronedj.com/2026/05/29/drone-photos-ai-niantic-spexi/",
            snippet=snippet,
            published_at="2026-05-29T00:00:00Z",
        )
    )
    assert not should_keep_editorial_content(title=title, snippet=snippet, text=body)


def test_rejects_niantic_zh_title_with_full_body() -> None:
    title = "Niantic用玩家实景扫描图像训练AI模型"
    body = (
        "Niantic（《Pokémon Go》开发商）正通过其分拆的AI公司Niantic Spatial，"
        "将约300亿张由玩家在游戏中自愿提交的实景扫描图像，转化为供机器人使用的世界模型。"
        "玩家在达到游戏20级后，通过主动选择AR扫描功能上传视频片段。"
    ) * 3
    assert is_consumer_gaming_drone_bait_content(title=title, text=body)
    assert not should_keep_editorial_content(title=title, text=body)
