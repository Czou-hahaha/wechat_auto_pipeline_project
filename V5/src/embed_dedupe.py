"""批量向量（本机 sentence-transformers **或** OpenAI 兼容 HTTP）与余弦近重复剔除。"""
from __future__ import annotations

import asyncio
import logging
import math
from typing import Any

import httpx

from src.config import Settings

logger = logging.getLogger(__name__)

# model_id -> SentenceTransformer 实例（进程内单例，避免重复加载）
_ST_MODEL_CACHE: dict[str, Any] = {}


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if len(a) != len(b) or not a:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na <= 0.0 or nb <= 0.0:
        return 0.0
    return dot / (na * nb)


def truncate_for_embedding(text: str, max_chars: int) -> str:
    t = (text or "").strip()
    if len(t) <= max_chars:
        return t
    return t[:max_chars]


async def fetch_embeddings_openai_compatible(
    *,
    client: httpx.AsyncClient,
    base_url: str,
    api_key: str,
    model: str,
    inputs: list[str],
) -> list[list[float] | None]:
    """调用 ``POST {base}/embeddings``；与 OpenAI 官方响应结构兼容。失败项对应位置为 ``None``。"""
    if not inputs:
        return []
    root = (base_url or "").strip().rstrip("/")
    if not root:
        logger.warning("embedding: empty base_url")
        return [None for _ in inputs]
    url = f"{root}/embeddings"
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if api_key.strip():
        headers["Authorization"] = f"Bearer {api_key.strip()}"
    payload: dict[str, Any] = {"model": model.strip(), "input": inputs}
    try:
        resp = await client.post(url, headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        logger.warning("embedding request failed url=%s", url[:80], exc_info=True)
        return [None for _ in inputs]
    rows = data.get("data")
    if not isinstance(rows, list):
        logger.warning("embedding: unexpected response shape")
        return [None for _ in inputs]
    by_index: dict[int, list[float]] = {}
    for item in rows:
        if not isinstance(item, dict):
            continue
        idx = item.get("index")
        emb = item.get("embedding")
        if isinstance(idx, int) and isinstance(emb, list) and emb and all(isinstance(x, (int, float)) for x in emb):
            by_index[idx] = [float(x) for x in emb]
    out: list[list[float] | None] = []
    for i in range(len(inputs)):
        out.append(by_index.get(i))
    return out


def _embed_texts_sentence_transformers_sync(
    inputs: list[str],
    model_id: str,
    *,
    normalize_embeddings: bool = True,
) -> list[list[float] | None]:
    """
    本机 ``sentence_transformers`` 编码；与常见 bge 用法一致，默认 L2 归一化便于余弦相似度。

    首次调用会从 Hugging Face 拉取权重（需网络），之后走缓存目录。
    """
    if not inputs:
        return []
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        logger.warning(
            "sentence-transformers not installed; pip install sentence-transformers "
            "(see V3/requirements.txt). Skipping local embeddings."
        )
        return [None for _ in inputs]
    mid = (model_id or "BAAI/bge-m3").strip()
    if mid not in _ST_MODEL_CACHE:
        logger.info("loading local embedding model %s (first run may download weights)", mid)
        _ST_MODEL_CACHE[mid] = SentenceTransformer(mid)
    model = _ST_MODEL_CACHE[mid]
    # 空串会导致部分版本报错，用单空格占位
    clean = [(x or "").strip() or " " for x in inputs]
    try:
        arr = model.encode(
            clean,
            normalize_embeddings=normalize_embeddings,
            show_progress_bar=False,
        )
    except Exception:
        logger.exception("local SentenceTransformer.encode failed model=%s", mid)
        return [None for _ in inputs]
    out: list[list[float] | None] = []
    for row in arr:
        try:
            out.append([float(x) for x in row.tolist()])
        except Exception:
            out.append(None)
    return out


async def fetch_embeddings_batch(
    *,
    settings: Settings,
    inputs: list[str],
    client: httpx.AsyncClient | None,
) -> list[list[float] | None]:
    """
    按 ``settings.embedding_backend`` 选择本机或 HTTP。

    - ``local``：``asyncio.to_thread`` 中跑 ``SentenceTransformer.encode``（免 API KEY）。
    - ``http``：需非空 ``client`` 与 ``EMBEDDING_API_KEY``（若 KEY 为空则返回全 None）。
    """
    backend = (getattr(settings, "embedding_backend", None) or "local").strip().lower()
    if backend == "local":
        model_id = (settings.embedding_model or "BAAI/bge-m3").strip()
        return await asyncio.to_thread(
            _embed_texts_sentence_transformers_sync,
            inputs,
            model_id,
        )
    if not (settings.embedding_api_key or "").strip():
        logger.warning("embedding_backend=http but EMBEDDING_API_KEY empty")
        return [None for _ in inputs]
    if client is None:
        logger.warning("embedding_backend=http but httpx client is None")
        return [None for _ in inputs]
    return await fetch_embeddings_openai_compatible(
        client=client,
        base_url=settings.embedding_base_url,
        api_key=settings.embedding_api_key,
        model=settings.embedding_model,
        inputs=inputs,
    )


def dedupe_by_embedding_greedy(
    embeddings: list[list[float] | None],
    *,
    threshold: float,
) -> tuple[list[int], list[tuple[int, int, float]]]:
    """按输入顺序贪心保留：若与任一已保留向量余弦 ≥ ``threshold`` 则丢弃。

    返回 ``(保留的下标列表, [(被丢, 近邻已保留, 相似度), ...])``。
    ``embedding`` 为 ``None`` 的项一律保留（无法比较）。"""
    kept: list[int] = []
    dropped: list[tuple[int, int, float]] = []
    for i, vec in enumerate(embeddings):
        if vec is None:
            kept.append(i)
            continue
        best_j = -1
        best_sim = 0.0
        for j in kept:
            vj = embeddings[j]
            if vj is None:
                continue
            sim = cosine_similarity(vec, vj)
            if sim > best_sim:
                best_sim = sim
                best_j = j
        if best_j >= 0 and best_sim >= threshold:
            dropped.append((i, best_j, round(best_sim, 5)))
            continue
        kept.append(i)
    return kept, dropped
