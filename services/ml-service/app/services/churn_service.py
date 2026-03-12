"""
Churn prediction inference service.

Loads trained Logistic Regression model and predicts churn risk
for a user based on their engagement features. Falls back to
heuristic-based prediction if model is not loaded.
"""

import pickle
from pathlib import Path
from typing import Any

import numpy as np

from app.ml.churn_dataset_generator import FEATURE_NAMES
from app.logging import setup_logging

logger = setup_logging()

MODEL_DIR = Path("ml/models")

RISK_LEVELS = {
    "low": (0.0, 0.25),
    "medium": (0.25, 0.50),
    "high": (0.50, 0.75),
    "critical": (0.75, 1.01),
}


class ChurnPredictor:
    """
    Inference wrapper for churn prediction.
    Predicts churn probability and maps to risk levels.
    """

    def __init__(self) -> None:
        self.model = None
        self.scaler = None
        self._loaded = False

    def load(self, model_dir: Path | None = None) -> bool:
        """Load model and scaler from disk."""
        model_dir = model_dir or MODEL_DIR
        model_path = model_dir / "churn_predictor.pkl"
        scaler_path = model_dir / "churn_scaler.pkl"

        if not model_path.exists():
            logger.warning(f"Churn model not found at {model_dir} — using fallback")
            return False

        try:
            with open(model_path, "rb") as f:
                self.model = pickle.load(f)

            if scaler_path.exists():
                with open(scaler_path, "rb") as f:
                    self.scaler = pickle.load(f)

            self._loaded = True
            logger.info("Churn predictor loaded successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to load churn model: {e}")
            return False

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    def predict(self, features: dict[str, Any]) -> dict[str, Any]:
        """
        Predict churn risk for a user.

        Args:
            features: Dict with engagement features.

        Returns:
            {churn_risk: bool, probability: float, risk_level: str, reasoning: str}
        """
        if not self._loaded:
            return self._fallback(features)

        # Build feature vector in correct order
        X = np.array([[
            features.get("days_since_last_play", 0),
            features.get("session_frequency", 3.0),
            features.get("avg_session_duration", 20.0),
            features.get("total_games_played", 50),
            features.get("win_rate_trend", 0.0),
            features.get("hint_usage_trend", 0.0),
            features.get("difficulty_variety", 3),
            features.get("completion_rate", 0.7),
            features.get("error_rate_trend", 0.0),
            features.get("longest_streak", 5),
        ]])

        # Scale if scaler is available
        if self.scaler is not None:
            X = self.scaler.transform(X)

        # Predict
        probability = float(self.model.predict_proba(X)[0, 1])
        churn_risk = probability >= 0.5
        risk_level = self._get_risk_level(probability)

        # Generate reasoning
        reasoning = self._generate_reasoning(features, probability, risk_level)

        return {
            "churn_risk": churn_risk,
            "probability": round(probability, 4),
            "risk_level": risk_level,
            "reasoning": reasoning,
        }

    def _get_risk_level(self, probability: float) -> str:
        """Map probability to risk level."""
        for level, (low, high) in RISK_LEVELS.items():
            if low <= probability < high:
                return level
        return "critical"

    def _generate_reasoning(
        self,
        features: dict[str, Any],
        probability: float,
        risk_level: str,
    ) -> str:
        """Build human-readable reasoning string."""
        parts = [f"Churn probability: {probability:.1%} → {risk_level} risk."]

        days_since = features.get("days_since_last_play", 0)
        session_freq = features.get("session_frequency", 3.0)
        win_trend = features.get("win_rate_trend", 0.0)
        completion = features.get("completion_rate", 0.7)

        if days_since > 14:
            parts.append(f"Inactive for {days_since} days — significant gap.")
        elif days_since <= 2:
            parts.append("Recently active — positive engagement signal.")

        if session_freq < 1.0:
            parts.append("Very low session frequency may indicate fading interest.")
        elif session_freq >= 5.0:
            parts.append("High session frequency suggests strong engagement.")

        if win_trend < -0.1:
            parts.append("Declining win rate may signal frustration.")

        if completion < 0.5:
            parts.append("Low completion rate indicates possible difficulty mismatch.")

        return " ".join(parts)

    def _fallback(self, features: dict[str, Any]) -> dict[str, Any]:
        """Heuristic fallback when model is not loaded."""
        days_since = features.get("days_since_last_play", 0)
        session_freq = features.get("session_frequency", 3.0)

        # Simple heuristic: high days since + low freq = high churn risk
        risk_score = 0.0
        if days_since > 30:
            risk_score += 0.4
        elif days_since > 14:
            risk_score += 0.25
        elif days_since > 7:
            risk_score += 0.1

        if session_freq < 0.5:
            risk_score += 0.3
        elif session_freq < 1.5:
            risk_score += 0.15

        risk_score = min(risk_score, 0.95)
        risk_level = self._get_risk_level(risk_score)

        return {
            "churn_risk": risk_score >= 0.5,
            "probability": round(risk_score, 4),
            "risk_level": risk_level,
            "reasoning": (
                f"Model not loaded — heuristic estimate: {risk_score:.1%} risk ({risk_level}). "
                "Train the model with `python -m app.ml.train_churn` to enable ML predictions."
            ),
        }


# Singleton
churn_predictor = ChurnPredictor()
