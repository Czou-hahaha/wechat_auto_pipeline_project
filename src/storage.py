from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path


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


class JsonStore:
    def __init__(self, data_dir: Path):
        self._path = data_dir / "articles.json"
        if not self._path.exists():
            self._write([])

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

    def exists_duplicate(self, url: str, title: str, text: str) -> bool:
        norm_url = self._norm_url(url)
        norm_title = self._norm_text(title)
        norm_text = self._norm_text(text)[:3000]
        for row in self._read():
            if self._norm_url(str(row.get("source_url", ""))) == norm_url:
                return True
            t = self._norm_text(str(row.get("title", "")))
            if t and norm_title and SequenceMatcher(None, t, norm_title).ratio() >= 0.9:
                return True
            body = self._norm_text(str(row.get("extracted_text", "")))[:3000]
            if body and norm_text and SequenceMatcher(None, body, norm_text).ratio() >= 0.9:
                return True
        return False

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
