from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
from difflib import SequenceMatcher

import httpx

from src.utils.prompt_load import load_prompt_file

logger = logging.getLogger(__name__)
_PROMPTS_DIR = Path(__file__).resolve().parents[1] / "docs" / "prompts"
_STYLE_GUIDE_PATH = _PROMPTS_DIR / "news_single_summary.md"
_QA_DOC_PATH = Path(__file__).resolve().parents[1] / "docs" / "上线前文章校验标准.md"


class SummaryService:
    def __init__(self, *, api_key: str, base_url: str, model: str):
        self._api_key = api_key.strip()
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._style_guide = self._load_style_guide()
        self._qa_guide = self._load_qa_guide()
        self._single_article_system = self._load_single_article_system()
        self._cluster_summary_system = self._load_cluster_summary_system()
        self._cluster_summary_user_tpl = self._load_cluster_summary_user_template()
        self._qa_review_system = self._load_qa_review_system()

    async def summarize(self, *, title: str, text: str, max_chars: int = 2200, min_chars: int = 400) -> str:
        clean_text = (text or "").strip()[:12000]
        if not clean_text:
            return f"【摘要】{title}\n原文正文不足，暂不生成摘要。"
        if not self._api_key:
            return self._fallback(title=title, text=clean_text, max_chars=max_chars)
        prompt = (
            self._style_guide.replace("{{MAX_CHARS}}", str(max_chars)).strip()
            + "\n\n"
            + f"标题：{title}\n\n原文：\n{clean_text}\n\n仅输出摘要正文。"
        )
        payload = self._chat_payload(
            system_prompt=self._single_article_system,
            user_prompt=prompt,
            max_tokens=min(4096, max_chars + 800),
            temperature=0.7,
        )
        try:
            content = await self._chat_text(payload=payload, timeout=90.0)
            if content:
                cleaned = self._sanitize_summary_text(content)[:max_chars]
                if self._summary_qualified(summary=cleaned, source_text=clean_text, min_chars=min_chars):
                    return cleaned
                rewrite = await self._rewrite_summary_with_constraints(
                    title=title, source_text=clean_text, summary=cleaned, min_chars=min_chars, max_chars=max_chars
                )
                if rewrite:
                    return rewrite
            return self._fallback(title=title, text=clean_text, max_chars=max_chars)
        except Exception:
            logger.exception("DeepSeek 摘要失败，回退本地摘要")
            return self._fallback(title=title, text=clean_text, max_chars=max_chars)

    async def summarize_cluster(
        self,
        *,
        items: list[dict[str, str]],
        max_chars: int = 2200,
        min_chars: int = 400,
    ) -> tuple[str, str]:
        """
        多源整合摘要：``items`` 每项建议包含 title/text/source_host（可选 source_label）。
        返回 (成稿标题, 摘要正文)。标题应概括整合后的主题，不与任一单行标题逐字相同。
        """
        if not items:
            return "", ""
        if len(items) == 1:
            one = items[0]
            body = await self.summarize(
                title=str(one.get("title", "")),
                text=str(one.get("text", "")),
                max_chars=max_chars,
                min_chars=min_chars,
            )
            return str(one.get("title", "")).strip(), body
        blocks: list[str] = []
        for i, it in enumerate(items, start=1):
            t = str(it.get("title", "")).strip()
            host = str(it.get("source_host", "") or it.get("source_label", "")).strip()
            tx = (str(it.get("text", "")).strip())[:3500]
            label = host or f"来源{i}"
            blocks.append(f"【{label}】\n标题：{t}\n正文摘录：\n{tx}")
        bundle = "\n\n".join(blocks)
        if not self._api_key:
            fb = self._fallback(title=str(items[0].get("title", "")), text=bundle, max_chars=max_chars)
            return str(items[0].get("title", "") or "").strip(), fb
        user_prompt = (
            self._cluster_summary_user_tpl.replace("{{MAX_CHARS}}", str(max_chars))
            .replace("{{MIN_CHARS}}", str(min_chars))
            .replace("{{BUNDLE}}", bundle)
        )
        data = await self._chat_json(
            system_prompt=self._cluster_summary_system,
            user_prompt=user_prompt,
            timeout=120.0,
        )
        if not isinstance(data, dict):
            fb = self._fallback(title=str(items[0].get("title", "")), text=bundle, max_chars=max_chars)
            return str(items[0].get("title", "") or "").strip(), fb
        out_title = str(data.get("title", "") or "").strip() or str(items[0].get("title", "")).strip()
        summary = str(data.get("summary", "") or "").strip()
        summary = self._sanitize_summary_text(summary)[:max_chars]
        plain = "".join(summary.split())
        if len(plain) < min_chars:
            fb = self._fallback(title=out_title, text=bundle, max_chars=max_chars)
            return out_title, fb
        return out_title, summary

    @staticmethod
    def _bundle_is_low_cjk(*, title: str, summary: str, max_cjk_ratio: float = 0.06) -> bool:
        """标题+摘要整体 CJK 占比低于阈值时视为「以外文为主」，可触发中译。"""
        bundle = f"{title}\n{summary}"
        stripped = "".join(bundle.split())
        if len(stripped) < 40:
            return False
        cjk = len(re.findall(r"[\u4e00-\u9fff]", stripped))
        return (cjk / len(stripped)) < max_cjk_ratio

    async def translate_title_summary_to_zh(self, *, title: str, summary: str) -> tuple[str, str]:
        """
        若成稿主要为非中文，将标题与摘要译为简体中文；否则返回 (\"\", \"\")。
        用于仅译「事件级」输出、不落库全文译文的成本策略。
        """
        if not self._api_key:
            return "", ""
        if not self._bundle_is_low_cjk(title=title, summary=summary):
            return "", ""
        user_prompt = (
            "将下列公众号成稿标题与摘要翻译成自然、流畅的简体中文，保持事实准确、语气中立。"
            "不要解释。仅输出 JSON：{\"title_zh\":\"...\",\"summary_zh\":\"...\"}\n\n"
            f"标题：\n{(title or '')[:220]}\n\n摘要：\n{(summary or '')[:8000]}"
        )
        data = await self._chat_json(
            system_prompt="你是专业翻译，只输出合法 JSON。",
            user_prompt=user_prompt,
            timeout=90.0,
        )
        if not isinstance(data, dict):
            return "", ""
        tzh = str(data.get("title_zh", "") or "").strip()
        szh = str(data.get("summary_zh", "") or "").strip()
        return tzh, szh

    async def classify_topic(self, *, title: str, text: str) -> dict:
        """
        返回:
        {
          "is_important": bool,
          "category": "policy|intl|other",
          "topic_key": str
        }
        """
        fallback = self._fallback_topic_classification(title=title, text=text)
        if not self._api_key:
            return fallback
        user_prompt = (
            "请判断新闻是否属于重要topic。\n"
            "重要topic仅两类：\n"
            "1) 国家直接政策类（禁飞/禁售/禁运/监管规定/执法新规）\n"
            "2) 中外合作类（中国与其他国家/国际机构的合作）\n\n"
            "请只返回 JSON，字段：is_important(boolean), category(string), topic_key(string)。\n"
            "topic_key 需是可稳定复用的语义键，尽量短，如“beijing_drone_ban_2026”。\n"
            "若非重要topic，category=other，topic_key 置空字符串。\n\n"
            f"标题：{title}\n\n正文前2000字：\n{(text or '')[:2000]}"
        )
        data = await self._chat_json(
            system_prompt="你是新闻主题分类器，只输出 JSON。",
            user_prompt=user_prompt,
            timeout=45.0,
        )
        if not data:
            return fallback
        try:
            is_important = bool(data.get("is_important", False))
            category = str(data.get("category", "other") or "other").strip().lower()
            topic_key = str(data.get("topic_key", "") or "").strip().lower()
            if category not in {"policy", "intl", "other"}:
                category = "other"
            if not is_important:
                category = "other"
                topic_key = ""
            return {
                "is_important": is_important and bool(topic_key),
                "category": category,
                "topic_key": topic_key,
            }
        except Exception:
            return fallback

    async def semantic_duplicate_decision(
        self,
        *,
        title: str,
        text: str,
        candidates: list[dict],
    ) -> dict:
        """
        返回:
        {
          "is_duplicate": bool,
          "has_new_info": bool,
          "reason": str
        }
        """
        if not candidates:
            return {"is_duplicate": False, "has_new_info": True, "reason": "no_candidates"}
        fallback = self._fallback_semantic_duplicate(title=title, text=text, candidates=candidates)
        if not self._api_key:
            return fallback
        compact = []
        for row in candidates[:5]:
            compact.append(
                {
                    "title": str(row.get("title", ""))[:120],
                    "source_url": str(row.get("source_url", ""))[:200],
                    "text": str(row.get("extracted_text", ""))[:700],
                }
            )
        user_prompt = (
            "判断候选新文章与历史文章是否语义重复。重复定义：描述的是同一事件且没有新增关键信息。\n"
            "若存在新增关键事实（新增政策条款、新增数据、新增时间节点、新增监管动作），则 has_new_info=true。\n"
            "仅输出 JSON：is_duplicate(boolean), has_new_info(boolean), reason(string)。\n\n"
            f"新文章标题：{title}\n新文章正文前1500字：\n{(text or '')[:1500]}\n\n"
            f"历史候选（最多5条）：\n{json.dumps(compact, ensure_ascii=False)}"
        )
        data = await self._chat_json(
            system_prompt="你是新闻语义去重器，只输出 JSON。",
            user_prompt=user_prompt,
            timeout=60.0,
        )
        if not data:
            return fallback
        try:
            is_dup = bool(data.get("is_duplicate", False))
            has_new = bool(data.get("has_new_info", not is_dup))
            reason = str(data.get("reason", "") or "").strip()[:200]
            return {"is_duplicate": is_dup, "has_new_info": has_new, "reason": reason}
        except Exception:
            return fallback

    async def review_summary_for_publish(
        self,
        *,
        title: str,
        source_url: str,
        source_published_at: str,
        source_text: str,
        summary: str,
        max_article_age_hours: int,
        min_score: int = 80,
        enabled: bool = True,
        source_published_at_date_only: bool = False,
        date_only_max_calendar_age_days: int = 3,
        schedule_timezone: str = "Asia/Shanghai",
    ) -> dict:
        """
        对摘要执行 DeepSeek 自动复核。用于发布前最后一道质量门禁。
        """
        if not enabled:
            return {
                "pass": True,
                "score": 100,
                "reasons": ["qa_disabled"],
                "hard_fail_items": [],
                "quick_verdict": "qa disabled",
            }
        deterministic = self._deterministic_summary_checks(
            title=title,
            source_published_at=source_published_at,
            max_article_age_hours=max_article_age_hours,
            source_text=source_text,
            summary=summary,
            source_published_at_date_only=source_published_at_date_only,
            date_only_max_calendar_age_days=date_only_max_calendar_age_days,
            schedule_timezone=schedule_timezone,
        )
        if deterministic["hard_fail_items"]:
            return {
                "pass": False,
                "score": 0,
                "reasons": deterministic["reasons"],
                "hard_fail_items": deterministic["hard_fail_items"],
                "quick_verdict": "deterministic hard-fail",
            }
        if not self._api_key:
            return {
                "pass": False,
                "score": 0,
                "reasons": ["qa_unavailable_no_api_key"],
                "hard_fail_items": ["qa_unavailable"],
                "quick_verdict": "qa unavailable",
            }
        user_prompt = (
            "你是上线前内容审核员。请严格按两份规则判断是否可发布，并只输出 JSON。\n\n"
            f"【摘要规则】\n{self._style_guide}\n\n"
            f"【上线校验标准】\n{self._qa_guide}\n\n"
            "审核对象：\n"
            f"- 标题: {title}\n"
            f"- 来源: {source_url}\n"
            f"- source_published_at: {source_published_at}\n"
            f"- 摘要: {(summary or '')[:3500]}\n"
            f"- 原文(截断): {(source_text or '')[:4500]}\n\n"
            "机器检查（仅供参考）：\n"
            f"- in_time_window: {deterministic['in_time_window']}\n"
            f"- overlap_ratio: {deterministic['overlap_ratio']}\n"
            f"- first_paragraph_similarity: {deterministic['first_paragraph_similarity']}\n"
            f"- summary_len_no_whitespace: {deterministic['summary_len_no_whitespace']}\n"
            f"- has_raw_link_or_原文链接: {deterministic['has_raw_link_or_原文链接']}\n"
            f"- fallback_prefix_【摘要】: {deterministic['fallback_prefix_【摘要']}\n\n"
            "输出 JSON schema:\n"
            "{\n"
            '  "pass": true/false,\n'
            '  "score": 0-100,\n'
            '  "reasons": ["..."],\n'
            '  "hard_fail_items": ["..."],\n'
            '  "quick_verdict": "一句话结论"\n'
            "}"
        )
        data = await self._chat_json(
            system_prompt=self._qa_review_system,
            user_prompt=user_prompt,
            timeout=90.0,
        )
        if not isinstance(data, dict):
            return {
                "pass": False,
                "score": 0,
                "reasons": ["qa_response_invalid"],
                "hard_fail_items": ["qa_invalid_output"],
                "quick_verdict": "qa invalid output",
            }
        score = self._safe_int(data.get("score", 0))
        pass_flag = bool(data.get("pass", False)) and score >= min_score
        reasons = self._safe_list(data.get("reasons"))
        hard_fails = self._safe_list(data.get("hard_fail_items"))
        verdict = str(data.get("quick_verdict", "") or "").strip()[:200]
        if score < min_score:
            hard_fails.append(f"score_below_threshold:{score}<{min_score}")
        return {
            "pass": pass_flag and not hard_fails,
            "score": score,
            "reasons": reasons,
            "hard_fail_items": hard_fails,
            "quick_verdict": verdict,
        }

    @staticmethod
    def _load_style_guide() -> str:
        default_prompt = (
            "你是中文公众号编辑。只基于原文写摘要，不要扩写，不要编造，不要增加原文不存在的数据。\n"
            "长度不超过 {{MAX_CHARS}} 字。"
        )
        try:
            text = load_prompt_file("news_single_summary")
            if text:
                return text
        except Exception:
            logger.warning("摘要规范文档读取失败，使用内置默认 prompt: %s", _STYLE_GUIDE_PATH)
        return default_prompt

    @staticmethod
    def _load_single_article_system() -> str:
        default_sys = "你是中国科技产业媒体的资深编辑；遵循用户消息中的体例，输出整稿逻辑下的正文，不是文章摘要。"
        try:
            return load_prompt_file("news_single_system")
        except Exception:
            logger.warning("单篇摘要 system 读取失败，使用默认: %s", _PROMPTS_DIR / "news_single_system.md")
            return default_sys

    @staticmethod
    def _load_cluster_summary_system() -> str:
        default_sys = "你是严谨的中文编辑，只输出合法 JSON。"
        try:
            return load_prompt_file("cluster_summary_system")
        except Exception:
            logger.warning("簇摘要 system 读取失败，使用默认")
            return default_sys

    @staticmethod
    def _load_cluster_summary_user_template() -> str:
        fallback = (
            "你是中文公众号编辑。下面给出同一主题下多篇报道的摘录（不同角度、不同站点）。\n"
            "请综合成一篇可发布的摘要：只使用摘录中事实；冲突写明报道口径不一致；"
            "转述归纳；首段概括；段落间空行；不写小标题。\n"
            "总长度不超过 {{MAX_CHARS}} 字，不少于 {{MIN_CHARS}} 字。\n"
            "文末「信息来源：」列举媒体名。输出 JSON："
            '{"title":"...","summary":"..."}\n\n材料：\n{{BUNDLE}}'
        )
        try:
            return load_prompt_file("cluster_summary_user")
        except Exception:
            logger.warning("簇摘要 user 模板读取失败，使用内置兜底")
            return fallback

    @staticmethod
    def _load_qa_review_system() -> str:
        default_sys = "你是严谨的中文内容审核员。只输出 JSON。"
        try:
            return load_prompt_file("qa_review_system")
        except Exception:
            logger.warning("QA system 读取失败，使用默认")
            return default_sys

    @staticmethod
    def _load_qa_guide() -> str:
        default_rules = "只发布符合时间窗口、主题范围、摘要规范的文章。"
        try:
            text = _QA_DOC_PATH.read_text(encoding="utf-8").strip()
            if text:
                return text
        except Exception:
            logger.warning("上线校验标准文档读取失败，使用内置默认规则: %s", _QA_DOC_PATH)
        return default_rules

    @staticmethod
    def _fallback(*, title: str, text: str, max_chars: int) -> str:
        body = " ".join(text.split())[: max_chars - 20]
        return SummaryService._sanitize_summary_text(f"【摘要】{title}\n{body}")

    @staticmethod
    def _summary_qualified(*, summary: str, source_text: str, min_chars: int) -> bool:
        plain_summary = "".join((summary or "").split())
        plain_source = "".join((source_text or "").split())
        if len(plain_summary) < min_chars:
            return False
        overlap = SequenceMatcher(None, plain_summary[:2200], plain_source[:2200]).ratio()
        if overlap > 0.6:
            return False
        first_summary = (summary.strip().split("\n\n", 1)[0] or "").strip()
        first_source = (source_text.strip().split("\n", 1)[0] or "").strip()
        if first_summary and first_source:
            if SequenceMatcher(None, first_summary[:180], first_source[:180]).ratio() > 0.75:
                return False
        return True

    @staticmethod
    def _deterministic_summary_checks(
        *,
        title: str,
        source_published_at: str,
        max_article_age_hours: int,
        source_text: str,
        summary: str,
        source_published_at_date_only: bool = False,
        date_only_max_calendar_age_days: int = 3,
        schedule_timezone: str = "Asia/Shanghai",
    ) -> dict:
        plain_summary = "".join((summary or "").split())
        plain_source = "".join((source_text or "").split())
        overlap = SequenceMatcher(None, plain_summary[:2200], plain_source[:2200]).ratio() if plain_source else 1.0
        first_summary = (summary.strip().split("\n\n", 1)[0] or "").strip()
        first_source = (source_text.strip().split("\n", 1)[0] or "").strip()
        first_ratio = (
            SequenceMatcher(None, first_summary[:180], first_source[:180]).ratio()
            if first_summary and first_source
            else 1.0
        )
        has_raw_link = ("http://" in summary) or ("https://" in summary) or ("原文链接" in summary)
        fallback_prefix = summary.lstrip().startswith("【摘要】")
        in_time = SummaryService._source_published_in_window(
            source_published_at=source_published_at,
            max_article_age_hours=max_article_age_hours,
            date_only_coarse=source_published_at_date_only,
            date_only_max_calendar_age_days=date_only_max_calendar_age_days,
            schedule_timezone=schedule_timezone,
        )
        hard_fails: list[str] = []
        reasons: list[str] = []
        if not in_time:
            hard_fails.append("source_published_at_outside_window_or_invalid")
        if fallback_prefix:
            hard_fails.append("fallback_prefix_【摘要】")
        if len(plain_summary) > 2000:
            hard_fails.append("summary_length_over_2000")
        if len(plain_summary) < 300:
            hard_fails.append("summary_length_under_300")
        if overlap > 0.6:
            hard_fails.append(f"overlap_ratio_over_0.6:{overlap:.4f}")
        if first_ratio > 0.75:
            hard_fails.append(f"first_paragraph_similarity_over_0.75:{first_ratio:.4f}")
        if has_raw_link:
            hard_fails.append("contains_raw_link_or_原文链接")
        if SummaryService._is_roundup_fastnews(title=title, source_text=source_text, summary=summary):
            hard_fails.append("roundup_or_fastnews_not_domain_primary")
        if hard_fails:
            reasons.append("deterministic quality guard failed")
        return {
            "in_time_window": in_time,
            "overlap_ratio": round(overlap, 4),
            "first_paragraph_similarity": round(first_ratio, 4),
            "summary_len_no_whitespace": len(plain_summary),
            "has_raw_link_or_原文链接": has_raw_link,
            "fallback_prefix_【摘要】": fallback_prefix,
            "hard_fail_items": hard_fails,
            "reasons": reasons,
        }

    @staticmethod
    def _source_published_in_window(
        *,
        source_published_at: str,
        max_article_age_hours: int,
        date_only_coarse: bool,
        date_only_max_calendar_age_days: int,
        schedule_timezone: str,
    ) -> bool:
        try:
            dt = datetime.fromisoformat(str(source_published_at or "").replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
        except Exception:
            return False
        if max_article_age_hours <= 0:
            return True
        if date_only_coarse:
            tz = ZoneInfo((schedule_timezone or "Asia/Shanghai").strip() or "Asia/Shanghai")
            today = datetime.now(timezone.utc).astimezone(tz).date()
            art_day = dt.astimezone(tz).date()
            oldest = today - timedelta(days=max(1, int(date_only_max_calendar_age_days)))
            return oldest <= art_day <= today + timedelta(days=1)
        return dt >= (datetime.now(timezone.utc) - timedelta(hours=max_article_age_hours))

    @staticmethod
    def _is_roundup_fastnews(*, title: str, source_text: str, summary: str) -> bool:
        t = (title or "").strip()
        blob = f"{t}\n{summary[:2200]}\n{source_text[:2600]}"
        if not blob:
            return False
        if any(k in t for k in ("新规来了", "这些新规将施行", "重磅新规落地", "今起")):
            return True
        if "影响你我生活" in t:
            return True
        if ("一批涉及" in blob and "多个领域" in blob) or "涉及商业短信、网售食品、无人机激活等" in blob:
            return True
        cross_terms = (
            "通信短信息",
            "烟花爆竹",
            "渔业法",
            "网络食品",
            "殡葬",
            "商事调解",
            "特种设备",
            "基金",
            "反腐",
            "药品",
        )
        low_alt_terms = ("低空", "无人机", "无人驾驶航空器", "通用航空", "eVTOL", "UAM")
        cross_count = sum(1 for x in cross_terms if x in blob)
        low_count = sum(blob.count(x) for x in low_alt_terms)
        if cross_count >= 3 and low_count <= cross_count + 1:
            return True
        return False

    @staticmethod
    def _safe_int(v: object) -> int:
        try:
            n = int(v)
            if n < 0:
                return 0
            if n > 100:
                return 100
            return n
        except Exception:
            return 0

    @staticmethod
    def _safe_list(v: object) -> list[str]:
        if not isinstance(v, list):
            return []
        out: list[str] = []
        for item in v:
            s = str(item or "").strip()
            if s:
                out.append(s[:200])
        return out

    async def _rewrite_summary_with_constraints(
        self, *, title: str, source_text: str, summary: str, min_chars: int, max_chars: int
    ) -> str:
        prompt = (
            "请重写下面摘要，满足：\n"
            f"1) 字数不少于 {min_chars} 字；\n"
            "2) 与原文重合度不超过60%；\n"
            "3) 首段必须重写，不能照抄原文首段；\n"
            "4) 只基于原文事实，不得编造。\n"
            "仅输出重写后的摘要正文。\n\n"
            f"标题：{title}\n\n原文前3000字：\n{source_text[:3000]}\n\n待重写摘要：\n{summary}"
        )
        payload = self._chat_payload(
            system_prompt=self._single_article_system,
            user_prompt=prompt,
            max_tokens=min(4096, max_chars + 800),
            temperature=0.5,
        )
        try:
            content = await self._chat_text(payload=payload, timeout=90.0)
            rewritten = self._sanitize_summary_text(content)[:max_chars]
            if self._summary_qualified(summary=rewritten, source_text=source_text, min_chars=min_chars):
                return rewritten
        except Exception:
            logger.warning("summary rewrite failed", exc_info=True)
        return ""

    def _chat_payload(self, *, system_prompt: str, user_prompt: str, max_tokens: int, temperature: float) -> dict:
        return {
            "model": self._model,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }

    async def _chat_text(self, *, payload: dict, timeout: float) -> str:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(
                f"{self._base_url}/v1/chat/completions",
                headers={"Authorization": f"Bearer {self._api_key}"},
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
        return (data.get("choices", [{}])[0].get("message", {}).get("content", "") or "").strip()

    async def _chat_json(self, *, system_prompt: str, user_prompt: str, timeout: float) -> dict | None:
        try:
            text = await self._chat_text(
                payload=self._chat_payload(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    max_tokens=1200,
                    temperature=0.1,
                ),
                timeout=timeout,
            )
        except Exception:
            logger.warning("chat json request failed", exc_info=True)
            return None
        if not text:
            return None
        raw = text.strip()
        if raw.startswith("```"):
            raw = raw.strip("`")
            if "\n" in raw:
                raw = raw.split("\n", 1)[1].strip()
        if raw.endswith("```"):
            raw = raw[:-3].strip()
        try:
            return json.loads(raw)
        except Exception:
            pass
        start = raw.find("{")
        end = raw.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(raw[start : end + 1])
            except Exception:
                return None
        return None

    @staticmethod
    def _fallback_topic_classification(*, title: str, text: str) -> dict:
        blob = f"{title}\n{text[:800]}".lower()
        policy_hit = any(k in blob for k in ("禁飞", "禁售", "禁运", "管理规定", "实施", "监管"))
        intl_hit = any(k in blob for k in ("中美", "中欧", "国际合作", "合作协议", "联合", "双边"))
        if policy_hit:
            return {"is_important": True, "category": "policy", "topic_key": "policy_" + str(abs(hash(title)) % 100000)}
        if intl_hit:
            return {"is_important": True, "category": "intl", "topic_key": "intl_" + str(abs(hash(title)) % 100000)}
        return {"is_important": False, "category": "other", "topic_key": ""}

    @staticmethod
    def _fallback_semantic_duplicate(*, title: str, text: str, candidates: list[dict]) -> dict:
        base = "".join(f"{title}\n{text[:1000]}".split()).lower()
        for row in candidates[:5]:
            comp = "".join(f"{row.get('title','')}\n{str(row.get('extracted_text',''))[:1000]}".split()).lower()
            if not comp:
                continue
            if SequenceMatcher(None, base[:1800], comp[:1800]).ratio() >= 0.82:
                return {"is_duplicate": True, "has_new_info": False, "reason": "fallback_similarity"}
        return {"is_duplicate": False, "has_new_info": True, "reason": "fallback_not_duplicate"}

    @staticmethod
    def _sanitize_summary_text(text: str) -> str:
        out = text or ""
        # Product requirement: do not expose markdown emphasis markers.
        out = out.replace("**", "")
        out = out.replace("\r\n", "\n").replace("\r", "\n")
        out = "\n".join(line.rstrip() for line in out.split("\n"))
        return out.strip()
