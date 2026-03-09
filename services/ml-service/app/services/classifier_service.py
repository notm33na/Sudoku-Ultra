"""
Difficulty classifier inference service.

Loads the trained Random Forest model and provides predictions
with SHAP explanations. Includes rule-based fallback if model
is not available.
"""

import pickle
from pathlib import Path
from typing import Any

import numpy as np

from app.ml.dataset_generator import FEATURE_NAMES
from app.logging import setup_logging

logger = setup_logging()

MODEL_DIR = Path("ml/models")

DIFFICULTY_CLASSES = ["super_easy", "easy", "medium", "hard", "super_hard", "extreme"]


class DifficultyClassifier:
    """
    Inference wrapper for the difficulty classifier.
    Loads model + label encoder at init time. Falls back to
    rule-based classification if model files are missing.
    """

    def __init__(self) -> None:
        self.model = None
        self.label_encoder = None
        self.shap_explainer = None
        self._loaded = False

    def load(self, model_dir: Path | None = None) -> bool:
        """Load model and encoder from disk. Returns True on success."""
        model_dir = model_dir or MODEL_DIR
        model_path = model_dir / "difficulty_classifier.pkl"
        encoder_path = model_dir / "label_encoder.pkl"

        if not model_path.exists() or not encoder_path.exists():
            logger.warning(
                f"Classifier model not found at {model_dir} — using rule-based fallback"
            )
            return False

        try:
            with open(model_path, "rb") as f:
                self.model = pickle.load(f)
            with open(encoder_path, "rb") as f:
                self.label_encoder = pickle.load(f)
            self._loaded = True
            logger.info("Difficulty classifier loaded successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to load classifier: {e}")
            return False

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    def predict(self, features: dict[str, float]) -> dict[str, Any]:
        """
        Predict difficulty from puzzle features.

        Args:
            features: Dict with keys matching FEATURE_NAMES.

        Returns:
            {difficulty, confidence, shap_values, explanation}
        """
        if not self._loaded:
            return self._rule_based_fallback(features)

        # Build feature vector in correct order
        X = np.array([[features.get(f, 0.0) for f in FEATURE_NAMES]])

        # Predict with probabilities
        proba = self.model.predict_proba(X)[0]
        pred_idx = np.argmax(proba)
        difficulty = self.label_encoder.inverse_transform([pred_idx])[0]
        confidence = float(proba[pred_idx])

        # SHAP explanation
        shap_values = self._compute_shap(X, pred_idx)

        # Generate explanation
        top_features = sorted(shap_values.items(), key=lambda x: abs(x[1]), reverse=True)[:3]
        top_str = ", ".join(f"{k} ({v:+.3f})" for k, v in top_features)
        explanation = (
            f"Classified as '{difficulty}' with {confidence:.1%} confidence. "
            f"Top factors: {top_str}."
        )

        return {
            "difficulty": difficulty,
            "confidence": confidence,
            "shap_values": shap_values,
            "explanation": explanation,
        }

    def _compute_shap(self, X: np.ndarray, pred_class_idx: int) -> dict[str, float]:
        """Compute SHAP values for the prediction."""
        try:
            if self.shap_explainer is None:
                import shap
                self.shap_explainer = shap.TreeExplainer(self.model)

            shap_result = self.shap_explainer.shap_values(X)

            # shap_result is a list of arrays, one per class
            if isinstance(shap_result, list):
                class_shap = shap_result[pred_class_idx][0]
            else:
                class_shap = shap_result[0]

            return {name: round(float(val), 4) for name, val in zip(FEATURE_NAMES, class_shap)}

        except Exception as e:
            logger.warning(f"SHAP computation failed: {e}")
            # Fallback to feature importance
            importances = self.model.feature_importances_
            return {name: round(float(val), 4) for name, val in zip(FEATURE_NAMES, importances)}

    def _rule_based_fallback(self, features: dict[str, float]) -> dict[str, Any]:
        """Rule-based classification when ML model is unavailable."""
        clue_count = features.get("clue_count", 30)

        if clue_count >= 45:
            difficulty = "super_easy"
        elif clue_count >= 36:
            difficulty = "easy"
        elif clue_count >= 30:
            difficulty = "medium"
        elif clue_count >= 26:
            difficulty = "hard"
        elif clue_count >= 22:
            difficulty = "super_hard"
        else:
            difficulty = "extreme"

        # Uniform placeholder SHAP
        shap_values = {f: round(1.0 / len(FEATURE_NAMES), 4) for f in FEATURE_NAMES}

        return {
            "difficulty": difficulty,
            "confidence": 0.5,
            "shap_values": shap_values,
            "explanation": (
                f"Rule-based fallback (model not loaded): "
                f"{int(clue_count)} clues → '{difficulty}'."
            ),
        }


# Singleton
classifier = DifficultyClassifier()
