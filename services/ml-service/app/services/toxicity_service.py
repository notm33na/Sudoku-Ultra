"""
toxicity_service.py — 3-tier inference chain for chat moderation.

Tier 1 : Fine-tuned DistilBERT at ml/models/toxicity_classifier/
Tier 2 : Pre-trained HuggingFace `unitary/toxic-bert` (downloads on first use)
Tier 3 : Keyword-based filter (always available, no external dependencies)

Result schema:
    { is_toxic: bool, confidence: float, category: str }

Categories (for informational purposes — not used for block decision):
    clean | toxic | severe_toxic | obscene | threat | insult | identity_hate
"""

from __future__ import annotations

import logging
import pathlib
import re
import threading
from typing import Optional

logger = logging.getLogger(__name__)

_MODEL_DIR = pathlib.Path("ml/models/toxicity_classifier")
_PRETRAINED_FALLBACK = "unitary/toxic-bert"

try:
    import transformers  # noqa: F401
    _TRANSFORMERS_AVAILABLE = True
except ImportError:
    _TRANSFORMERS_AVAILABLE = False
    logger.info("transformers not installed — toxicity service will use keyword fallback only")

# ── Keyword lists (fast, zero-dependency fallback) ────────────────────────────

_TOXIC_PATTERNS: list[re.Pattern] = [
    re.compile(r"\b" + word + r"\b", re.IGNORECASE)
    for word in [
        "fuck", "shit", "bitch", "asshole", "bastard", "cunt", "damn",
        "idiot", "moron", "retard", "kill", "die", "hate", "racist",
        "nigger", "faggot", "slut", "whore",
    ]
]

_SEVERE_PATTERNS: list[re.Pattern] = [
    re.compile(r"\b" + word + r"\b", re.IGNORECASE)
    for word in ["kill yourself", "kys", "go die", "i will kill"]
]

_THREAT_PATTERNS: list[re.Pattern] = [
    re.compile(p, re.IGNORECASE) for p in [r"i (will|ll) (kill|hurt|destroy|find) you"]
]


def _keyword_category(text: str) -> str:
    for p in _SEVERE_PATTERNS:
        if p.search(text):
            return "severe_toxic"
    for p in _THREAT_PATTERNS:
        if p.search(text):
            return "threat"
    return "toxic"


class ToxicityService:
    """
    Thread-safe singleton service.  Models are loaded lazily on first predict() call
    and cached in memory.  The pipeline lock prevents concurrent loading races.
    """

    def __init__(self) -> None:
        self._pipeline: Optional[object] = None
        self._loading_lock = threading.Lock()
        self._loaded = False

    # ─── Public API ───────────────────────────────────────────────────────────

    def predict(self, text: str) -> dict:
        """
        Returns { is_toxic: bool, confidence: float, category: str }.
        Never raises — falls back to keyword filter on any error.
        """
        if not text or not text.strip():
            return {"is_toxic": False, "confidence": 1.0, "category": "clean"}

        text = text.strip()[:512]

        try:
            self._ensure_loaded()
            if self._pipeline is not None:
                return self._predict_pipeline(text)
        except Exception as exc:
            logger.warning("Pipeline predict failed, falling back to keyword: %s", exc)

        return self._keyword_predict(text)

    # ─── Model Loading ────────────────────────────────────────────────────────

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        with self._loading_lock:
            if self._loaded:
                return
            self._pipeline = self._build_pipeline()
            self._loaded = True

    def _build_pipeline(self) -> Optional[object]:
        if not _TRANSFORMERS_AVAILABLE:
            return None

        from transformers import pipeline as hf_pipeline

        # Tier 1: fine-tuned model
        if (_MODEL_DIR / "config.json").exists():
            try:
                p = hf_pipeline(
                    "text-classification",
                    model=str(_MODEL_DIR),
                    device=-1,
                    truncation=True,
                    max_length=128,
                )
                logger.info("Loaded fine-tuned toxicity model from %s", _MODEL_DIR)
                return p
            except Exception as exc:
                logger.warning("Failed to load fine-tuned model: %s", exc)

        # Tier 2: pre-trained toxic-bert from HuggingFace Hub
        try:
            p = hf_pipeline(
                "text-classification",
                model=_PRETRAINED_FALLBACK,
                device=-1,
                truncation=True,
                max_length=512,
            )
            logger.info("Loaded pre-trained fallback: %s", _PRETRAINED_FALLBACK)
            return p
        except Exception as exc:
            logger.warning("Failed to load %s: %s", _PRETRAINED_FALLBACK, exc)

        return None  # will use keyword filter

    # ─── Pipeline Inference ───────────────────────────────────────────────────

    def _predict_pipeline(self, text: str) -> dict:
        results = self._pipeline(text)  # type: ignore[operator]
        result = results[0] if isinstance(results, list) else results
        label: str = result["label"].upper()
        score: float = float(result["score"])

        # unitary/toxic-bert uses label "toxic" / "non-toxic"
        # Fine-tuned model uses "LABEL_0" (clean) / "LABEL_1" (toxic)
        is_toxic = label in ("TOXIC", "LABEL_1")
        confidence = score if is_toxic else 1.0 - score

        category = "clean"
        if is_toxic:
            category = _keyword_category(text)

        return {
            "is_toxic":   is_toxic,
            "confidence": round(confidence, 4),
            "category":   category,
        }

    # ─── Keyword Fallback ─────────────────────────────────────────────────────

    def _keyword_predict(self, text: str) -> dict:
        for p in _SEVERE_PATTERNS:
            if p.search(text):
                return {"is_toxic": True, "confidence": 1.0, "category": "severe_toxic"}
        for p in _THREAT_PATTERNS:
            if p.search(text):
                return {"is_toxic": True, "confidence": 1.0, "category": "threat"}
        for p in _TOXIC_PATTERNS:
            if p.search(text):
                return {"is_toxic": True, "confidence": 1.0, "category": "toxic"}
        return {"is_toxic": False, "confidence": 0.95, "category": "clean"}


# ── Module-level singleton ────────────────────────────────────────────────────
toxicity_service = ToxicityService()
