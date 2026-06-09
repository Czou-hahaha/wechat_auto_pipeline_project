"""FAISS inner-product search on L2-normalized vectors (= cosine similarity)."""
from __future__ import annotations

import faiss
import numpy as np


def max_cosine_vs_bank(candidate: np.ndarray, bank: np.ndarray) -> float:
    """
    ``candidate`` shape (d,), ``bank`` shape (n, d), both float32.
    Returns max cosine similarity in [0,1] when vectors are L2-normalized.
    """
    if bank.size == 0:
        return 0.0
    c = np.asarray(candidate, dtype=np.float32).reshape(1, -1)
    b = np.asarray(bank, dtype=np.float32)
    faiss.normalize_L2(c)
    faiss.normalize_L2(b)
    d = b.shape[1]
    index = faiss.IndexFlatIP(int(d))
    index.add(b)
    sims, _ = index.search(c, min(int(b.shape[0]), 32))
    return float(sims[0, 0])
