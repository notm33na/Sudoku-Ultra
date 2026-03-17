"""
Sentence-transformer embedding singleton.

Wraps all-MiniLM-L6-v2 (384-dim) with lazy loading so the model is only
downloaded/loaded once per process lifetime.
"""

from __future__ import annotations

import threading
from typing import Sequence

import numpy as np
from sentence_transformers import SentenceTransformer

from app.config import settings

_lock = threading.Lock()
_model: SentenceTransformer | None = None


def _get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        with _lock:
            if _model is None:
                _model = SentenceTransformer(settings.EMBEDDING_MODEL)
    return _model


def embed_one(text: str) -> list[float]:
    """Return a normalised 384-dim embedding for a single string."""
    vec: np.ndarray = _get_model().encode(
        text, normalize_embeddings=True, show_progress_bar=False
    )
    return vec.tolist()


def embed_batch(texts: Sequence[str]) -> list[list[float]]:
    """Return normalised embeddings for a batch of strings."""
    vecs: np.ndarray = _get_model().encode(
        list(texts), normalize_embeddings=True, show_progress_bar=False, batch_size=32
    )
    return vecs.tolist()
