"""
anomaly_service.py — Anti-cheat anomaly scoring service.

Inference chain (with automatic fallback):
  1. ONNX runtime  — fastest; loaded from ml/models/anomaly_autoencoder.onnx
  2. PyTorch       — fallback if ONNX runtime unavailable
  3. Heuristic     — rule-based fallback, no model required

Thread-safe lazy loading via threading.Lock.
"""

from __future__ import annotations

import json
import logging
import pathlib
import threading
from typing import Optional

import numpy as np

from app.ml.feature_extractor import extract_features

logger = logging.getLogger(__name__)

# ── Paths ──────────────────────────────────────────────────────────────────────

_BASE = pathlib.Path(__file__).resolve().parents[3] / "ml" / "models"
_ONNX_PATH = _BASE / "anomaly_autoencoder.onnx"
_PT_PATH = _BASE / "anomaly_autoencoder.pt"
_META_PATH = _BASE / "anomaly_meta.json"

# Default threshold used when no trained model is available.
_DEFAULT_THRESHOLD = 0.05

# Heuristic thresholds (used when no model is loaded).
_HEURISTIC_FAST_FILL_RATE = 0.8   # normalised fill_rate_norm (feature 6)
_HEURISTIC_MAX_ERROR_RATE = 0.02  # near-zero error rate for a "completed" session
_HEURISTIC_MIN_TIMING_NORM = 0.01 # extremely fast fill times (feature 0)


class AnomalyService:
    """Thread-safe lazy-loading anomaly scoring service."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._ort_session = None   # onnxruntime.InferenceSession | None
        self._torch_model = None   # SparseAutoencoder | None
        self._threshold: float = _DEFAULT_THRESHOLD
        self._mean_train_error: float = 0.0
        self._loaded = False

    # ── Public API ────────────────────────────────────────────────────────────

    def score(
        self,
        *,
        time_elapsed_ms: int,
        cells_filled: int,
        errors_count: int,
        hints_used: int,
        difficulty: str,
        cells_to_fill: Optional[int] = None,
        cell_fill_times_ms: Optional[list[int]] = None,
    ) -> dict:
        """
        Compute the anomaly score for a completed game session.

        Returns
        -------
        {
          "anomaly_score":       float,  # reconstruction_error / threshold
          "reconstruction_error": float,
          "threshold":           float,
          "is_anomalous":        bool,
        }
        """
        self._ensure_loaded()

        features = extract_features(
            time_elapsed_ms=time_elapsed_ms,
            cells_filled=cells_filled,
            errors_count=errors_count,
            hints_used=hints_used,
            difficulty=difficulty,
            cells_to_fill=cells_to_fill,
            cell_fill_times_ms=cell_fill_times_ms,
        )

        if self._ort_session is not None:
            error = self._score_onnx(features)
        elif self._torch_model is not None:
            error = self._score_torch(features)
        else:
            return self._heuristic_score(features)

        anomaly_score = error / max(1e-9, self._threshold)
        return {
            "anomaly_score": round(float(anomaly_score), 6),
            "reconstruction_error": round(float(error), 6),
            "threshold": round(self._threshold, 6),
            "is_anomalous": bool(error > self._threshold),
        }

    # ── Lazy loading ──────────────────────────────────────────────────────────

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        with self._lock:
            if self._loaded:
                return
            self._load_meta()
            self._load_onnx()
            if self._ort_session is None:
                self._load_torch()
            self._loaded = True

    def _load_meta(self) -> None:
        if _META_PATH.exists():
            try:
                meta = json.loads(_META_PATH.read_text())
                self._threshold = float(meta.get("threshold", _DEFAULT_THRESHOLD))
                self._mean_train_error = float(meta.get("mean_train_error", 0.0))
                logger.info(
                    "anomaly_service: loaded meta (threshold=%.6f)", self._threshold
                )
            except Exception as exc:
                logger.warning("anomaly_service: could not load meta: %s", exc)

    def _load_onnx(self) -> None:
        if not _ONNX_PATH.exists():
            return
        try:
            import onnxruntime as ort

            self._ort_session = ort.InferenceSession(str(_ONNX_PATH))
            logger.info("anomaly_service: ONNX model loaded from %s", _ONNX_PATH)
        except Exception as exc:
            logger.warning("anomaly_service: ONNX load failed: %s", exc)

    def _load_torch(self) -> None:
        if not _PT_PATH.exists():
            return
        try:
            import torch
            from app.ml.train_autoencoder import SparseAutoencoder

            model = SparseAutoencoder()
            model.load_state_dict(torch.load(str(_PT_PATH), map_location="cpu"))
            model.eval()
            self._torch_model = model
            logger.info("anomaly_service: PyTorch model loaded from %s", _PT_PATH)
        except Exception as exc:
            logger.warning("anomaly_service: PyTorch load failed: %s", exc)

    # ── Inference ──────────────────────────────────────────────────────────────

    def _score_onnx(self, features: np.ndarray) -> float:
        inp = features.reshape(1, -1)
        outputs = self._ort_session.run(None, {"features": inp})
        recon = outputs[0].reshape(-1)
        return float(np.mean((features - recon) ** 2))

    def _score_torch(self, features: np.ndarray) -> float:
        import torch

        x = torch.from_numpy(features).unsqueeze(0)
        with torch.no_grad():
            recon, _ = self._torch_model(x)
        recon_np = recon.squeeze(0).numpy()
        return float(np.mean((features - recon_np) ** 2))

    def _heuristic_score(self, features: np.ndarray) -> dict:
        """
        Rule-based fallback when no model is loaded.

        Flags sessions with:
        - Superhuman fill speed (f6 > 0.8 AND f0 < 0.02)
        - Near-zero errors on a hard puzzle
        - Robotic timing consistency (f9 < 0.05)
        """
        f0 = float(features[0])   # time_mean_norm
        f4 = float(features[4])   # error_rate
        f6 = float(features[6])   # fill_rate_norm
        f9 = float(features[9])   # consistency_score

        suspicion = 0.0
        if f6 > _HEURISTIC_FAST_FILL_RATE and f0 < 0.02:
            suspicion += 0.6
        if f4 < _HEURISTIC_MAX_ERROR_RATE and f6 > 0.5:
            suspicion += 0.3
        if f9 < 0.05:
            suspicion += 0.2

        is_anomalous = suspicion >= 0.6
        # Represent as a pseudo reconstruction_error for a consistent API.
        pseudo_error = suspicion * _DEFAULT_THRESHOLD * 2
        return {
            "anomaly_score": round(suspicion, 6),
            "reconstruction_error": round(pseudo_error, 6),
            "threshold": _DEFAULT_THRESHOLD,
            "is_anomalous": is_anomalous,
        }


# Module-level singleton.
anomaly_service = AnomalyService()
