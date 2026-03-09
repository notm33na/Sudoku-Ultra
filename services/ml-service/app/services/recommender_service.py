"""
Adaptive difficulty recommendation inference service.

Loads trained Gradient Boosting Regressor and predicts optimal
difficulty for a user based on their gameplay features.
Falls back to last_played_difficulty if model is not loaded.
"""

import pickle
from pathlib import Path
from typing import Any

import numpy as np

from app.ml.user_dataset_generator import FEATURE_NAMES, DIFFICULTY_NAMES
from app.logging import setup_logging

logger = setup_logging()

MODEL_DIR = Path("ml/models")


class AdaptiveDifficultyRecommender:
    """
    Inference wrapper for adaptive difficulty regression.
    Predicts optimal difficulty score (0–5) and maps to class name.
    """

    def __init__(self) -> None:
        self.model = None
        self._loaded = False

    def load(self, model_dir: Path | None = None) -> bool:
        """Load model from disk."""
        model_dir = model_dir or MODEL_DIR
        model_path = model_dir / "adaptive_regression.pkl"

        if not model_path.exists():
            logger.warning(f"Regression model not found at {model_dir} — using fallback")
            return False

        try:
            with open(model_path, "rb") as f:
                self.model = pickle.load(f)
            self._loaded = True
            logger.info("Adaptive difficulty model loaded successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to load regression model: {e}")
            return False

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    def predict(self, features: dict[str, Any]) -> dict[str, Any]:
        """
        Predict optimal difficulty for a user.

        Args:
            features: Dict with user gameplay features.

        Returns:
            {recommended_difficulty, confidence, reasoning}
        """
        if not self._loaded:
            return self._fallback(features)

        # Build feature vector
        X = np.array([[
            features.get("avg_solve_time_easy", 120),
            features.get("avg_solve_time_medium", 300),
            features.get("avg_solve_time_hard", 600),
            features.get("hint_rate", 0.2),
            features.get("error_rate", 0.2),
            features.get("current_streak", 0),
            features.get("session_count", 1),
            self._encode_difficulty(features.get("last_played_difficulty", "easy")),
            features.get("win_rate", 0.5),
        ]])

        # Predict continuous score
        score = float(self.model.predict(X)[0])
        score = max(0.0, min(5.0, score))

        # Map to difficulty class
        class_idx = int(round(score))
        class_idx = max(0, min(5, class_idx))
        difficulty = DIFFICULTY_NAMES[class_idx]

        # Confidence: higher when prediction is closer to a class boundary
        distance_to_nearest = abs(score - round(score))
        confidence = round(1.0 - distance_to_nearest, 3)

        # Generate reasoning
        reasoning = self._generate_reasoning(features, difficulty, score, confidence)

        return {
            "recommended_difficulty": difficulty,
            "confidence": confidence,
            "reasoning": reasoning,
        }

    def _encode_difficulty(self, difficulty: str) -> int:
        """Map difficulty name to integer."""
        mapping = {name: i for i, name in enumerate(DIFFICULTY_NAMES)}
        return mapping.get(difficulty, 2)

    def _generate_reasoning(
        self,
        features: dict[str, Any],
        difficulty: str,
        score: float,
        confidence: float,
    ) -> str:
        """Build human-readable reasoning string."""
        parts = [f"Predicted optimal score: {score:.2f}/5.0 → '{difficulty}'."]

        win_rate = features.get("win_rate", 0.5)
        hint_rate = features.get("hint_rate", 0.2)
        streak = features.get("current_streak", 0)

        if win_rate > 0.8 and hint_rate < 0.1:
            parts.append("High win rate with low hint usage suggests readiness for harder puzzles.")
        elif win_rate < 0.5:
            parts.append("Lower win rate suggests an easier difficulty may improve engagement.")
        if streak > 10:
            parts.append(f"Active streak of {streak} days indicates consistent player.")

        return " ".join(parts)

    def _fallback(self, features: dict[str, Any]) -> dict[str, Any]:
        """Simple fallback when model is not loaded."""
        last = features.get("last_played_difficulty", "easy")
        if isinstance(last, (int, float)):
            idx = max(0, min(5, int(last)))
            last = DIFFICULTY_NAMES[idx]

        return {
            "recommended_difficulty": last,
            "confidence": 0.5,
            "reasoning": (
                f"Model not loaded — returning last played difficulty '{last}'. "
                "Train the model with `python -m app.ml.train_regression` to enable predictions."
            ),
        }


# Singleton
recommender = AdaptiveDifficultyRecommender()
