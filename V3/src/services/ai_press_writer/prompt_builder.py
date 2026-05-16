"""系统与用户 prompt 拼装（事件通稿）；正文来自 ``docs/prompts/*.md``。"""

from __future__ import annotations

import logging

from src.utils.prompt_load import load_prompt_file

logger = logging.getLogger(__name__)

_FALLBACK_EVENT_PRESS_SYSTEM = """
你是中国科技产业媒体的资深编辑。任务不是摘要，而是基于同一事件多篇报道整理完整、自然、具新闻编辑逻辑的中文稿；
只使用材料中明确信息；不补充外部知识、不推测、不编造细节、不照抄原句、不逐句译英、不写摘要体；多源融合、不重复罗列来源；
600~1000 字；只输出正文、无 markdown、无 JSON；不使用破折号、不写小标题；不足则输出：【信息不足，无法生成高质量通稿】
""".strip()

_FALLBACK_EVENT_PRESS_USER = """
事件标题：
{event_title}

事件关键词：
{keywords}

以下是该事件的相关文章：

{articles}

请基于整个事件生成一篇中文新闻稿。
""".strip()


try:
    SYSTEM_PROMPT = load_prompt_file("event_press_system")
except Exception:
    logger.exception("读取 event_press_system 失败，使用内置兜底 system")
    SYSTEM_PROMPT = _FALLBACK_EVENT_PRESS_SYSTEM


def get_event_press_system_prompt() -> str:
    """与 ``SYSTEM_PROMPT`` 相同；便于显式调用。"""
    return SYSTEM_PROMPT


def get_event_press_user_template() -> str:
    """user 模板全文（与 ``docs/prompts/event_press_user.md`` 一致）；供批量循环内复用，避免每事件重复读盘。"""
    try:
        return load_prompt_file("event_press_user")
    except Exception:
        logger.exception("读取 event_press_user 失败，使用内置兜底模板")
        return _FALLBACK_EVENT_PRESS_USER


def format_event_press_user(
    template: str,
    *,
    event_title: str,
    keywords: str,
    articles_block: str,
) -> str:
    """将已加载的 user 模板与具体事件字段拼装（模板内占位符为 ``event_title`` / ``keywords`` / ``articles``）。"""
    return template.format(
        event_title=(event_title or "").strip() or "（未命名事件）",
        keywords=(keywords or "").strip() or "（无）",
        articles=(articles_block or "").strip() or "（无正文材料）",
    )


def build_user_prompt(*, event_title: str, keywords: str, articles_block: str) -> str:
    """拼装动态 user prompt（等价于 ``format_event_press_user(get_event_press_user_template(), ...)``）。"""
    return format_event_press_user(
        get_event_press_user_template(),
        event_title=event_title,
        keywords=keywords,
        articles_block=articles_block,
    )
