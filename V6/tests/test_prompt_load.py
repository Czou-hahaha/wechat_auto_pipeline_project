"""``docs/prompts`` 与 prompt_builder 拼装。"""

from __future__ import annotations

from src.services.ai_press_writer import prompt_builder
from src.utils.prompt_load import clear_prompt_cache, load_prompt_file, prompts_dir


def test_prompts_dir_exists() -> None:
    d = prompts_dir()
    assert d.is_dir()
    assert (d / "event_press_user.md").is_file()


def test_load_event_press_user_format() -> None:
    clear_prompt_cache()
    s = prompt_builder.build_user_prompt(
        event_title="测 试 事 件",
        keywords="低空,监管",
        articles_block="【来源A】\n正文摘录",
    )
    assert "测 试 事 件" in s
    assert "低空,监管" in s
    assert "【来源A】" in s
    assert "产业新闻通讯" in s or "微信公众号" in s or "文章摘要" in s
    assert "报道口径不一致" not in s or "禁止" in s


def test_load_event_press_system_bans_inconsistency_meta() -> None:
    clear_prompt_cache()
    body = load_prompt_file("event_press_system")
    assert "禁止" in body and "报道口径不一致" in body
    assert "<strong>" in body
    assert "国内参照" in body


def test_load_news_single_summary_has_placeholder() -> None:
    clear_prompt_cache()
    body = load_prompt_file("news_single_summary")
    assert "{{MAX_CHARS}}" in body


def test_load_cluster_summary_user_has_editorial_rules_slot() -> None:
    clear_prompt_cache()
    body = load_prompt_file("cluster_summary_user")
    assert "{{EDITORIAL_RULES}}" in body
    assert "报道口径不一致" not in body or "禁止" in body


def test_load_summary_editorial_rules() -> None:
    clear_prompt_cache()
    body = load_prompt_file("summary_editorial_rules")
    assert "<strong>" in body
    assert "国内参照" in body
