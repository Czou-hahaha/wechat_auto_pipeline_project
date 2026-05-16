"""Local BAAI/bge-m3 embeddings via sentence-transformers (async-friendly)."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

_MODEL_CACHE: dict[str, Any] = {}


def _get_model(model_id: str) -> Any:
    if model_id not in _MODEL_CACHE:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as e:
            raise RuntimeError(
                "sentence-transformers is required for local embeddings; "
                "pip install sentence-transformers"
            ) from e
        logger.info("loading embedding model model_id=%s", model_id)
        _MODEL_CACHE[model_id] = SentenceTransformer(model_id)
    return _MODEL_CACHE[model_id]


def encode_texts_sync(
    texts: list[str],
    model_id: str,
    *,
    normalize_embeddings: bool = True,
) -> list[np.ndarray]:
    model = _get_model(model_id)
    if not texts:
        return []
    vectors = model.encode(
        texts,
        normalize_embeddings=normalize_embeddings,
        show_progress_bar=False,
    )
    out: list[np.ndarray] = []
    for row in vectors:
        arr = np.asarray(row, dtype=np.float32).reshape(-1)
        out.append(arr)
    return out


async def encode_texts(
    texts: list[str],
    model_id: str,
    *,
    normalize_embeddings: bool = True,
) -> list[np.ndarray]:
    return await asyncio.to_thread(
        encode_texts_sync,
        texts,
        model_id,
        normalize_embeddings=normalize_embeddings,
    )


def embedding_to_bytes(vec: np.ndarray) -> bytes:
    v = np.asarray(vec, dtype=np.float32).reshape(-1)
    return v.tobytes()


def bytes_to_embedding(data: bytes) -> np.ndarray:
    return np.frombuffer(data, dtype=np.float32).copy()
