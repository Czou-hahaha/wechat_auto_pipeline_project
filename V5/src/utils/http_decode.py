"""HTTP 响应体 → HTML 文本：优先 UTF-8，避免 Latin-1 误解码 UTF-8 导致整页乱码。"""
from __future__ import annotations

import logging
import re
from typing import Iterable

logger = logging.getLogger(__name__)

_CJK_RE = re.compile("[\u4e00-\u9fff]")
# UTF-8 字节被误用 Big5/CP950 等解码时常见的「假汉字」碎片，用于候选打分惩罚
_MOJI_HINT = re.compile("[銝鈭箸瘜蝳撠銵銋剖啣撅踹餃餈颲湛寞柴]")

_LATIN1_NAMES = frozenset(
    {
        "ascii",
        "latin-1",
        "iso-8859-1",
        "iso8859-1",
        "windows-1252",
        "cp1252",
    }
)


def _meta_charset_declared(body: bytes) -> str | None:
    """从 HTML 头部片段解析 ``charset=...``（仅 ASCII 子集，避免先有解码）。"""
    chunk = body[:98304]
    m = re.search(rb'charset\s*=\s*["\']?([a-z0-9_\-]+)', chunk, flags=re.I)
    if m:
        return m.group(1).decode("ascii", errors="ignore").strip().lower()
    return None


def _header_charset(content_type: str) -> str | None:
    ct = (content_type or "").lower()
    m = re.search(r"charset=([a-z0-9_\-]+)", ct)
    if m:
        return m.group(1).strip().lower()
    return None


def _decode_quality_score(text: str) -> float:
    """越高越像正常自然语言（中/英）；惩罚替换符与典型 UTF-8→Big5 乱码碎片。"""
    if not text:
        return -1e12
    sample = text[:12000]
    n_cjk = len(_CJK_RE.findall(sample))
    n_bad = sample.count("\ufffd")
    n_moji = len(_MOJI_HINT.findall(sample))
    n_latin = len(re.findall(r"[A-Za-z]{4,}", sample))
    return float(n_cjk + 0.06 * n_latin - 8.0 * n_bad - 0.55 * n_moji)


def _try_strict(enc: str, body: bytes) -> str | None:
    e = (enc or "").strip()
    if not e:
        return None
    try:
        return body.decode(e, errors="strict")
    except (UnicodeDecodeError, LookupError):
        return None


def _unique_encodings(seq: Iterable[str | None]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in seq:
        e = (raw or "").strip().lower()
        if not e or e in seen:
            continue
        seen.add(e)
        out.append(e)
    return out


def decode_http_html_bytes(
    body: bytes,
    *,
    content_type: str = "",
    httpx_encoding: str = "",
) -> str:
    """
    将 HTML 字节解码为 ``str``。

    历史上 ``httpx`` 在缺省 charset 时常回落到 ``iso-8859-1``；若用该编码去解
    实为 UTF-8 的页面，会得到「看起来像 CJK 但全错」的正文（如 RFI 中文站）。
    本函数优先 ``utf-8`` / ``utf-8-sig`` **严格**解码，失败后再尝试声明 charset、
    ``charset_normalizer``、以及 ``gb18030`` / ``gbk`` / ``big5`` 等中文编码。
    """
    if not body:
        return ""

    for enc in ("utf-8-sig", "utf-8"):
        t = _try_strict(enc, body)
        if t is not None:
            return t

    meta_enc = _meta_charset_declared(body)
    hdr_enc = _header_charset(content_type)
    hint = (httpx_encoding or "").strip().lower()
    candidates = _unique_encodings(
        [
            meta_enc,
            hdr_enc,
            None if hint in _LATIN1_NAMES else hint,
            "gb18030",
            "gbk",
            "big5",
        ]
    )

    best: str | None = None
    best_sc = -1e12
    for enc in candidates:
        t = _try_strict(enc, body)
        if t is None:
            continue
        sc = _decode_quality_score(t)
        if sc > best_sc:
            best_sc = sc
            best = t

    if best is not None:
        return best

    try:
        from charset_normalizer import from_bytes

        guess = from_bytes(body).best()
        if guess is not None:
            out = str(guess)
            if out.strip():
                return out
    except ImportError:
        logger.debug("charset_normalizer not installed; skipping charset sniff")
    except Exception:
        logger.debug("charset_normalizer failed", exc_info=True)

    return body.decode("utf-8", errors="replace")
