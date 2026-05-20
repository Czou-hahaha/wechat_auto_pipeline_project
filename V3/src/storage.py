from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from urllib.parse import urlparse


@dataclass
class ArticleRecord:
    id: str
    title: str
    source_url: str
    source_published_at: str
    extracted_text: str
    summary: str
    status: str
    created_at: str
    published_at: str
    # True：原文时间仅精确到「日历日」，与 MAX_ARTICLE_AGE_HOURS 组合时使用日历窗（见 pipeline）
    source_published_at_date_only: bool = False
    # 抓取最终 URL（与 RSS/跳转入口 source_url 可能不同），用于落地页去重
    resolved_url: str = ""
    source_host: str = ""
    topic_key: str = ""
    topic_category: str = ""
    topic_is_important: bool = False
    topic_source_count: int = 0
    deepseek_semantic_decision: str = ""
    novelty_passed: bool = False
    wechat_draft_pushed_at: str = ""
    cluster_size: int = 0
    synthesis_multi_source: bool = False
    # 事件聚类落库（可选）
    event_id: str = ""
    summary_zh: str = ""


@dataclass
class EventRecord:
    """一条「事件」：多篇文章聚类后的摘要层（与 articles.json 并行）。"""

    id: str
    title: str
    summary: str
    summary_zh: str
    dominant_topic_key: str
    created_at: str
    # 阶段四：多源中文通稿（DeepSeek；与 cluster 摘要独立）
    event_press_zh: str = ""
    event_press_generated_at: str = ""
    # 阶段五：通稿 QA（在 event_press_zh 落库前可能经重写）
    event_press_qa_score: int = 0
    event_press_qa_approved: bool = False
    event_press_qa_hallucination: bool = False
    event_press_qa_rewrite_attempts: int = 0
    event_press_qa_stopped_reason: str = ""
    event_press_qa_at: str = ""


class JsonStore:
    def __init__(self, data_dir: Path):
        self._data_dir = data_dir
        self._path = data_dir / "articles.json"
        self._events_path = data_dir / "events.json"
        self._event_map_path = data_dir / "event_article_map.json"
        if not self._path.exists():
            self._write([])
        if not self._events_path.exists():
            self._events_path.write_text("[]", encoding="utf-8")
        if not self._event_map_path.exists():
            self._event_map_path.write_text("[]", encoding="utf-8")

    @property
    def data_dir(self) -> Path:
        """可写数据目录（``articles.json`` / ``events.json`` 所在目录）。"""
        return self._data_dir

    def _read(self) -> list[dict]:
        try:
            return json.loads(self._path.read_text(encoding="utf-8"))
        except Exception:
            return []

    def _write(self, rows: list[dict]) -> None:
        self._path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")

    def list_all(self) -> list[dict]:
        return self._read()

    def add(self, rec: ArticleRecord) -> None:
        rows = self._read()
        rows.append(asdict(rec))
        self._write(rows)

    def append_event(self, rec: EventRecord) -> None:
        rows = self._read_events()
        rows.append(asdict(rec))
        self._write_events(rows)

    def append_event_article_map(self, entries: list[dict]) -> None:
        if not entries:
            return
        rows = self._read_event_map()
        rows.extend(entries)
        self._write_event_map(rows)

    def list_events(self) -> list[dict]:
        """``events.json`` 全量（dict 列表）。"""
        return self._read_events()

    def get_event(self, event_id: str) -> dict | None:
        """按 ``id`` 返回单条事件，不存在则 ``None``。"""
        eid = (event_id or "").strip()
        if not eid:
            return None
        for row in self._read_events():
            if isinstance(row, dict) and str(row.get("id", "")).strip() == eid:
                return row
        return None

    def articles_for_event(self, event_id: str) -> list[dict]:
        """``event_id`` 关联的全部 ``articles.json`` 行。"""
        eid = (event_id or "").strip()
        if not eid:
            return []
        return [r for r in self._read() if isinstance(r, dict) and str(r.get("event_id") or "").strip() == eid]

    def patch_event(self, event_id: str, updates: dict) -> bool:
        """将 ``updates`` merge 到首条匹配 ``id==event_id`` 的事件行。"""
        eid = (event_id or "").strip()
        if not eid or not isinstance(updates, dict):
            return False
        rows = self._read_events()
        for row in rows:
            if str(row.get("id", "")).strip() == eid:
                row.update(updates)
                self._write_events(rows)
                return True
        return False

    def _read_events(self) -> list[dict]:
        try:
            data = json.loads(self._events_path.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except Exception:
            return []

    def _write_events(self, rows: list[dict]) -> None:
        self._events_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")

    def _read_event_map(self) -> list[dict]:
        try:
            data = json.loads(self._event_map_path.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except Exception:
            return []

    def _write_event_map(self, rows: list[dict]) -> None:
        self._event_map_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")

    def find_by_topic_key(self, topic_key: str) -> list[dict]:
        key = (topic_key or "").strip().lower()
        if not key:
            return []
        out: list[dict] = []
        for row in self._read():
            if str(row.get("topic_key", "")).strip().lower() == key:
                out.append(row)
        return out

    def count_unique_sources_for_topic(self, topic_key: str) -> int:
        seen: set[str] = set()
        for row in self.find_by_topic_key(topic_key):
            host = str(row.get("source_host", "")).strip().lower()
            if not host:
                host = self.url_fingerprint(str(row.get("resolved_url", "") or row.get("source_url", "")))
            if host:
                seen.add(host)
        return len(seen)

    def semantic_candidates(self, *, limit: int = 12, important_only: bool | None = None) -> list[dict]:
        rows = self._read()
        out: list[dict] = []
        for row in reversed(rows):
            if important_only is not None and bool(row.get("topic_is_important", False)) != important_only:
                continue
            out.append(row)
            if len(out) >= limit:
                break
        return out

    def patch_article(self, article_id: str, updates: dict) -> bool:
        """Merge ``updates`` into the first row matching ``article_id``."""
        rows = self._read()
        for row in rows:
            if str(row.get("id", "")) != article_id:
                continue
            row.update(updates)
            self._write(rows)
            return True
        return False

    def clear_extracted_text_for_article(self, article_id: str) -> bool:
        """清空单条稿件正文（草稿已推送后瘦身库）。"""
        aid = (article_id or "").strip()
        if not aid:
            return False
        rows = self._read()
        changed = False
        for row in rows:
            if str(row.get("id", "")) != aid:
                continue
            if not str(row.get("extracted_text", "") or "").strip():
                return False
            row["extracted_text"] = ""
            changed = True
            break
        if changed:
            self._write(rows)
        return changed

    def clear_extracted_text_for_event(self, event_id: str) -> int:
        """清空同一 event 下所有稿件正文；返回实际清空条数。"""
        eid = (event_id or "").strip()
        if not eid:
            return 0
        rows = self._read()
        n = 0
        for row in rows:
            if str(row.get("event_id", "") or "").strip() != eid:
                continue
            if not str(row.get("extracted_text", "") or "").strip():
                continue
            row["extracted_text"] = ""
            n += 1
        if n:
            self._write(rows)
        return n

    def title_duplicate_against_history(self, title: str) -> bool:
        """仅看标题：与库中任一条标题相同或高度相似则视为重复（可跳过抓取/入稿）。"""
        norm = self._norm_text(title)
        if not norm:
            return False
        for row in self._read():
            t = self._norm_text(str(row.get("title", "")))
            if self.titles_duplicated(norm, t):
                return True
        return False

    def exists_duplicate(
        self, url: str, title: str, text: str, landing_url: str | None = None
    ) -> bool:
        """与历史库比对重复：标题 -> URL（含落地页指纹）-> 正文。"""
        norm_url = self._norm_url(url)
        norm_title = self._norm_text(title)
        norm_text = self._norm_text(text)[:3000]
        candidate_fps = self._url_fingerprints(url, landing_url)
        prefix_len = 400
        norm_prefix = norm_text[:prefix_len] if norm_text else ""

        for row in self._read():
            t = self._norm_text(str(row.get("title", "")))
            # 1) 标题相同或相似度 >= 90%：整篇视为重复，不再比对 URL/正文
            if self.titles_duplicated(norm_title, t):
                return True
            su = str(row.get("source_url", ""))
            ru = str(row.get("resolved_url", "") or "")
            # 2) 入口 URL 字符串一致，或落地页 host+path 指纹一致（忽略 query）
            if self._norm_url(su) == norm_url:
                return True
            row_fps = self._url_fingerprints(su, ru)
            if candidate_fps and row_fps and (candidate_fps & row_fps):
                return True
            body = self._norm_text(str(row.get("extracted_text", "")))[:3000]
            # 3) 正文相似度 >= 80%，或规范化后前缀足够长且一致（同稿不同版式）
            if body and norm_text:
                if SequenceMatcher(None, body, norm_text).ratio() >= 0.8:
                    return True
                bp = body[:prefix_len]
                if len(norm_prefix) >= 120 and len(bp) >= 120 and norm_prefix == bp:
                    return True
                # 3b) 同源通稿：全文尾部差异大但开头高度一致（如不同站转载同一稿）
                early = 900
                eb = body[:early]
                en = norm_text[:early]
                if len(en) >= 360 and len(eb) >= 360 and SequenceMatcher(None, eb, en).ratio() >= 0.82:
                    return True
        return False

    @staticmethod
    def titles_duplicated(
        norm_a: str,
        norm_b: str,
        *,
        min_norm_len: int = 8,
        similarity: float = 0.9,
    ) -> bool:
        """规范化标题是否算重复：等长串一致、相似度达标，或一方为另一方子串且多出的仅像地域/栏目前缀。"""
        if not norm_a or not norm_b:
            return False
        if norm_a == norm_b:
            return len(norm_a) >= min_norm_len
        if len(norm_a) < min_norm_len or len(norm_b) < min_norm_len:
            return False
        if SequenceMatcher(None, norm_a, norm_b).ratio() >= similarity:
            return True
        shorter, longer = (norm_a, norm_b) if len(norm_a) <= len(norm_b) else (norm_b, norm_a)
        # 同一事件长标题：短串为长串前缀（如「…通航」vs「…通航 大连至青岛单程约2小时」）
        if len(shorter) >= min_norm_len and longer.startswith(shorter):
            extra = len(longer) - len(shorter)
            allowed = max(18, int(0.5 * len(longer)))
            return extra <= allowed
        # 例：「兰州新区：无人机…」与「无人机…」ratio≈0.85，但短串为长串连续子串（非前缀）
        if len(shorter) >= min_norm_len and shorter in longer:
            extra = len(longer) - len(shorter)
            allowed = max(10, int(0.45 * len(shorter)))
            return extra <= allowed
        # 4) 不同站短标题措辞差异大，但存在较长公共子串（同一新闻多标题）
        if JsonStore._titles_share_long_common_substring(norm_a, norm_b, min_len=11):
            return True
        return False

    @staticmethod
    def _titles_share_long_common_substring(norm_a: str, norm_b: str, *, min_len: int = 11) -> bool:
        if len(norm_a) < min_len or len(norm_b) < min_len:
            return False
        shorter, longer = (norm_a, norm_b) if len(norm_a) <= len(norm_b) else (norm_b, norm_a)
        upper_k = min(len(shorter), 36)
        for k in range(min_len, upper_k + 1):
            lim = len(shorter) - k
            if lim < 0:
                break
            step = max(1, k // 5)
            for i in range(0, lim + 1, step):
                if shorter[i : i + k] in longer:
                    return True
        return False

    @staticmethod
    def url_fingerprint(url: str) -> str:
        """用于去重：scheme/query/fragment 忽略，host 去 www，path 小写去尾 /。"""
        raw = (url or "").strip()
        if not raw:
            return ""
        try:
            p = urlparse(raw)
            host = (p.netloc or "").lower().split(":")[0]
            if host.startswith("www."):
                host = host[4:]
            path = (p.path or "").rstrip("/").lower()
            return f"{host}{path}"
        except Exception:
            return raw.lower()[:240]

    @staticmethod
    def _url_fingerprints(*urls: str | None) -> set[str]:
        out: set[str] = set()
        for u in urls:
            fp = JsonStore.url_fingerprint(u or "")
            if fp:
                out.add(fp)
        return out

    @staticmethod
    def _norm_url(url: str) -> str:
        return url.strip().lower().rstrip("/")

    @staticmethod
    def _norm_text(text: str) -> str:
        x = re.sub(r"\s+", "", (text or "").lower())
        return re.sub(r"[^\w\u4e00-\u9fff]", "", x)

    @staticmethod
    def now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()
