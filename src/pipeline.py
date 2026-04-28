from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from urllib.parse import urljoin
from uuid import uuid4
import re

import httpx
from bs4 import BeautifulSoup

from src.ai import SummaryService
from src.config import Settings
from src.search import SearchHit, filter_by_age, normalize_title, search_with_toolchain
from src.storage import ArticleRecord, JsonStore
from src.wechat import WeChatDraftClient

logger = logging.getLogger(__name__)


@dataclass
class RunStats:
    total_candidates: int = 0
    published: int = 0
    skipped_duplicate: int = 0
    skipped_policy: int = 0
    skipped_too_short: int = 0
    failed: int = 0


class PipelineRunner:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.store = JsonStore(settings.data_path())
        self.summarizer = SummaryService(
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url,
            model=settings.deepseek_model,
        )
        self.wechat = WeChatDraftClient(
            app_id=settings.wechat_mp_app_id,
            app_secret=settings.wechat_mp_app_secret,
            author=settings.wechat_mp_author,
        )

    async def run_once(self) -> RunStats:
        queries = self.settings.parsed_queries()
        target_sites = self.settings.parsed_target_sites()
        if not queries:
            raise ValueError("SEARCH_QUERIES 为空")
        if not self.settings.wechat_ready():
            raise ValueError("微信公众号参数未配置完整（WECHAT_MP_APP_ID / WECHAT_MP_APP_SECRET）")

        all_hits: list[SearchHit] = []
        for q in queries:
            rows, tool = await search_with_toolchain(
                query=q,
                max_results=self.settings.search_max_results,
                target_sites=target_sites,
                max_attempts_per_tool=3,
            )
            if not rows:
                raise RuntimeError(
                    f"外部搜索在 3 个工具链路内均失败或无结果，已暂停本次任务。query={q}, tool={tool}"
                )
            logger.info("query=%s selected_search_tool=%s rows=%d", q, tool, len(rows))
            all_hits.extend(rows)

        unique: dict[str, SearchHit] = {}
        for hit in all_hits:
            key = self._canonical_url(hit.url)
            if key and key not in unique:
                unique[key] = hit
        candidates = filter_by_age(list(unique.values()), self.settings.max_article_age_hours)
        candidates = candidates[: self.settings.max_publish_per_run]

        thumb = self.settings.wechat_mp_thumb_media_id.strip()
        if not thumb:
            thumb = await self.wechat.upload_local_cover(self.settings.wechat_mp_thumb_local_path)

        stats = RunStats(total_candidates=len(candidates))
        processed_keys: set[str] = set()
        processed_titles: set[str] = set()
        for hit in candidates:
            try:
                key = self._canonical_url(hit.url)
                if key and key in processed_keys:
                    stats.skipped_duplicate += 1
                    continue
                title, text, first_image_url = await self._fetch_text(
                    hit.url, fallback_title=hit.title, fallback_snippet=hit.snippet
                )
                title_key = "".join((title or "").lower().split())
                if title_key and title_key in processed_titles:
                    stats.skipped_duplicate += 1
                    continue
                if self.store.exists_duplicate(hit.url, title, text):
                    stats.skipped_duplicate += 1
                    continue
                if self._is_too_short(text):
                    stats.skipped_too_short += 1
                    logger.info("skip too short article (<100 chars): %s", hit.url)
                    continue
                if self._is_policy_blocked(title=title, text=text, source_url=hit.url):
                    stats.skipped_policy += 1
                    logger.info("skip policy-blocked article: %s", hit.url)
                    continue
                summary = await self.summarizer.summarize(title=title, text=text, max_chars=2200)
                thumb_media_id = thumb
                if first_image_url:
                    try:
                        thumb_media_id = await self.wechat.upload_cover_from_url(first_image_url)
                    except Exception:
                        logger.warning(
                            "first image cover upload failed, fallback to default thumb: %s",
                            first_image_url,
                            exc_info=True,
                        )
                else:
                    logger.info("no valid first-image candidate found, fallback to default thumb: %s", hit.url)
                try:
                    await self.wechat.add_draft(
                        title=title,
                        summary=summary,
                        source_url=hit.url,
                        thumb_media_id=thumb_media_id,
                    )
                except RuntimeError as exc:
                    # WeChat may accept upload but reject cover at draft/add with 53402.
                    # In that case retry once with default local thumb media id.
                    msg = str(exc)
                    if "53402" in msg and thumb_media_id != thumb:
                        logger.warning(
                            "draft add failed by cover crop (53402), retry with default thumb: %s",
                            hit.url,
                        )
                        await self.wechat.add_draft(
                            title=title,
                            summary=summary,
                            source_url=hit.url,
                            thumb_media_id=thumb,
                        )
                    else:
                        raise
                rec = ArticleRecord(
                    id=str(uuid4()),
                    title=title,
                    source_url=hit.url,
                    source_published_at=hit.published_at,
                    extracted_text=text,
                    summary=summary,
                    status="published",
                    created_at=datetime.now(timezone.utc).isoformat(),
                    published_at=datetime.now(timezone.utc).isoformat(),
                )
                self.store.add(rec)
                stats.published += 1
                if key:
                    processed_keys.add(key)
                if title_key:
                    processed_titles.add(title_key)
            except Exception:
                logger.exception("处理失败: %s", hit.url)
                stats.failed += 1
        return stats

    async def _fetch_text(self, url: str, fallback_title: str, fallback_snippet: str) -> tuple[str, str, str | None]:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            resp = await client.get(url, headers={"User-Agent": "Mozilla/5.0"})
            resp.raise_for_status()
        html_text = self._decode_html(resp)
        soup = BeautifulSoup(html_text, "html.parser")
        title = (soup.title.text.strip() if soup.title and soup.title.text else fallback_title).strip() or "来源文章"
        if title.lower() == "google news" and fallback_title.strip():
            title = fallback_title.strip()
        if self._looks_garbled_text(title) and fallback_title.strip():
            title = fallback_title.strip()
        title = normalize_title(title)
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()
        parts: list[str] = []
        for p in soup.find_all(["p", "li", "h2", "h3"]):
            txt = (p.get_text(" ", strip=True) or "").strip()
            if len(txt) >= 25:
                parts.append(txt)
        text = "\n".join(parts)[:20000].strip() or fallback_snippet
        if self._looks_garbled_text(text) and fallback_snippet.strip():
            text = fallback_snippet.strip()
        first_image_url = self._extract_first_image_url(soup, base_url=str(resp.url))
        return title, text, first_image_url

    @staticmethod
    def _decode_html(resp: httpx.Response) -> str:
        body = resp.content or b""
        if not body:
            return ""
        candidates: list[str] = []
        enc = (resp.encoding or "").strip()
        if enc:
            candidates.append(enc)
        ct = (resp.headers.get("content-type") or "").lower()
        m = re.search(r"charset=([a-z0-9_\\-]+)", ct)
        if m:
            candidates.append(m.group(1))
        candidates.extend(["utf-8", "gb18030", "gbk", "big5"])

        seen: set[str] = set()
        best_text = body.decode("utf-8", errors="ignore")
        best_score = -1.0
        for c in candidates:
            e = c.lower().strip()
            if not e or e in seen:
                continue
            seen.add(e)
            try:
                text = body.decode(e, errors="ignore")
            except Exception:
                continue
            if not text:
                continue
            chinese_count = len(re.findall(r"[\\u4e00-\\u9fff]", text))
            garbled_count = len(re.findall(r"[�Ãâ¤ï¿½]", text))
            score = float(chinese_count - 3 * garbled_count)
            if score > best_score:
                best_score = score
                best_text = text
        return best_text

    @staticmethod
    def _extract_first_image_url(soup: BeautifulSoup, base_url: str) -> str | None:
        article_scoped = soup.select(
            "article img, main img, [class*='content'] img, [class*='article'] img, [id*='content'] img, [id*='article'] img"
        )
        for img in article_scoped:
            candidate = PipelineRunner._normalize_img_src(str(img.get("src") or ""), base_url)
            if candidate and PipelineRunner._is_likely_content_image(img, candidate):
                return candidate

        og = soup.find("meta", attrs={"property": "og:image"})
        if og and og.get("content"):
            candidate = PipelineRunner._normalize_img_src(str(og.get("content") or ""), base_url)
            if candidate and PipelineRunner._is_likely_cover_url(candidate):
                return candidate
        tw = soup.find("meta", attrs={"name": "twitter:image"})
        if tw and tw.get("content"):
            candidate = PipelineRunner._normalize_img_src(str(tw.get("content") or ""), base_url)
            if candidate and PipelineRunner._is_likely_cover_url(candidate):
                return candidate

        for img in soup.find_all("img"):
            candidate = PipelineRunner._normalize_img_src(str(img.get("src") or ""), base_url)
            if candidate and PipelineRunner._is_likely_content_image(img, candidate):
                return candidate
        return None

    @staticmethod
    def _normalize_img_src(src: str, base_url: str) -> str:
        raw = (src or "").strip()
        if not raw or raw.startswith("data:"):
            return ""
        return urljoin(base_url, raw)

    @staticmethod
    def _is_likely_cover_url(image_url: str) -> bool:
        lowered = image_url.lower()
        bad_tokens = ("logo", "icon", "avatar", "sprite", "favicon")
        return not any(token in lowered for token in bad_tokens)

    @staticmethod
    def _is_likely_content_image(img_tag: BeautifulSoup, image_url: str) -> bool:
        if not PipelineRunner._is_likely_cover_url(image_url):
            return False
        width = PipelineRunner._to_int(img_tag.get("width"))
        height = PipelineRunner._to_int(img_tag.get("height"))
        # Skip tiny/static assets when dimensions are explicitly available.
        if width and width < 200:
            return False
        if height and height < 120:
            return False
        classes = " ".join(img_tag.get("class") or []).lower()
        alt = str(img_tag.get("alt") or "").lower()
        src_l = image_url.lower()
        if re.search(r"(logo|icon|avatar|qrcode|二维码)", f"{classes} {alt} {src_l}"):
            return False
        return True

    @staticmethod
    def _to_int(raw: object) -> int:
        if raw is None:
            return 0
        m = re.search(r"\d+", str(raw))
        return int(m.group(0)) if m else 0

    @staticmethod
    def _looks_garbled_text(text: str) -> bool:
        if not text:
            return False
        bad = len(re.findall(r"[�Ãâ¤ï¿½]", text))
        return bad >= 3

    @staticmethod
    def _canonical_url(url: str) -> str:
        raw = (url or "").strip()
        if not raw:
            return ""
        try:
            p = urlparse(raw)
            host = (p.netloc or "").lower()
            path = (p.path or "").rstrip("/")
            if host.endswith("news.google.com") and path.startswith("/rss/articles/"):
                # Remove transient params (hl/gl/ceid/etc), keep article identity by path.
                return urlunparse((p.scheme.lower() or "https", host, path, "", "", ""))
            qs = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=False) if not k.lower().startswith("utm_")]
            query = urlencode(sorted(qs))
            return urlunparse((p.scheme.lower() or "https", host, path, "", query, "")).rstrip("/")
        except Exception:
            return raw.lower().rstrip("/")

    @staticmethod
    def _is_too_short(text: str, min_chars: int = 100) -> bool:
        plain = re.sub(r"\s+", "", text or "")
        return len(plain) < min_chars

    @staticmethod
    def _is_policy_blocked(*, title: str, text: str, source_url: str) -> bool:
        content = f"{title}\n{text}".lower()
        host = (urlparse(source_url).hostname or "").lower()

        # Source-level strictness: Taiwan-local news domains are treated as higher risk.
        taiwan_domain_hints = (
            ".tw",
            "udn.com",
            "ltn.com.tw",
            "setn.com",
            "ettoday.net",
            "storm.mg",
            "newtalk.tw",
            "cts.com.tw",
            "tvbs.com.tw",
            "epochtimes.com",
            "epochtimes.com.tw",
        )
        if any(h in host for h in taiwan_domain_hints):
            return True

        smear_markers = (
            "抹黑大陆",
            "唱衰中国",
            "中国崩溃",
            "大陆崩溃",
            "看衰中国",
            "中国威胁论",
            "中国渗透",
            "中共渗透",
            "大陆打压",
            "妖魔化中国",
        )
        separatist_markers = (
            "台独",
            "两国论",
            "一边一国",
            "台湾国",
            "去中国化",
            "中国入侵台湾",
            "大陆入侵台湾",
        )
        if any(k in content for k in smear_markers):
            return True
        if any(k in content for k in separatist_markers):
            return True

        # Combination rule: anti-mainland negative framing around China/Mainland.
        mainland_refs = ("中国大陆", "大陆", "中国", "内地")
        negative_refs = ("专制", "独裁", "打压", "迫害", "扩张", "威胁", "渗透", "封锁", "侵略")
        has_mainland_ref = any(k in content for k in mainland_refs)
        has_negative_ref = any(k in content for k in negative_refs)
        return has_mainland_ref and has_negative_ref
