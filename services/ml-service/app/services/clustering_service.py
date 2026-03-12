"""
Player skill clustering inference service.

Loads the trained K-Means model and assigns users to skill tiers:
Beginner, Casual, Intermediate, Advanced, Expert.
"""

import json
import pickle
from pathlib import Path
from typing import Any

import numpy as np

from app.ml.skill_dataset_generator import FEATURE_NAMES, CLUSTER_LABELS
from app.logging import setup_logging

logger = setup_logging()

MODEL_DIR = Path("ml/models")


class SkillClusteringService:
    """Inference wrapper for player skill clustering."""

    def __init__(self) -> None:
        self.model = None
        self.scaler = None
        self.label_map: dict[int, str] = {}
        self._loaded = False

    def load(self, model_dir: Path | None = None) -> bool:
        """Load KMeans model, scaler, and label map."""
        model_dir = model_dir or MODEL_DIR
        model_path = model_dir / "skill_clustering.pkl"
        scaler_path = model_dir / "skill_scaler.pkl"
        label_map_path = model_dir / "cluster_label_map.json"

        if not model_path.exists():
            logger.warning(f"Clustering model not found at {model_dir} — using fallback")
            return False

        try:
            with open(model_path, "rb") as f:
                self.model = pickle.load(f)
            if scaler_path.exists():
                with open(scaler_path, "rb") as f:
                    self.scaler = pickle.load(f)
            if label_map_path.exists():
                with open(label_map_path) as f:
                    raw = json.load(f)
                    self.label_map = {int(k): v for k, v in raw.items()}

            self._loaded = True
            logger.info("Skill clustering model loaded successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to load clustering model: {e}")
            return False

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    def predict(self, features: dict[str, Any]) -> dict[str, Any]:
        """
        Assign a user to a skill cluster.

        Returns:
            {cluster: str, cluster_id: int, confidence: float, reasoning: str}
        """
        if not self._loaded:
            return self._fallback(features)

        X = np.array([[features.get(f, 0.0) for f in FEATURE_NAMES]])

        if self.scaler is not None:
            X = self.scaler.transform(X)

        cluster_id = int(self.model.predict(X)[0])
        cluster_label = self.label_map.get(cluster_id, f"Cluster {cluster_id}")

        # Confidence: inverse of distance to nearest centroid (normalized)
        distances = self.model.transform(X)[0]
        min_dist = distances[cluster_id]
        mean_dist = float(np.mean(distances))
        confidence = round(max(0.0, min(1.0, 1.0 - (min_dist / mean_dist))), 3)

        reasoning = self._generate_reasoning(features, cluster_label, confidence)

        return {
            "cluster": cluster_label,
            "cluster_id": cluster_id,
            "confidence": confidence,
            "reasoning": reasoning,
        }

    def _generate_reasoning(self, features: dict, label: str, confidence: float) -> str:
        parts = [f"Assigned to '{label}' cluster (confidence: {confidence:.1%})."]

        hint_rate = features.get("hint_rate", 0.5)
        error_rate = features.get("error_rate", 0.3)
        days_active = features.get("days_active_last_30", 0)

        if hint_rate < 0.05:
            parts.append("Minimal hint usage indicates strong problem-solving ability.")
        elif hint_rate > 0.3:
            parts.append("Higher hint usage suggests room for improvement.")

        if days_active > 20:
            parts.append(f"Active {days_active}/30 days — highly engaged.")
        elif days_active < 5:
            parts.append(f"Only active {days_active}/30 days — low engagement.")

        return " ".join(parts)

    def _fallback(self, features: dict) -> dict[str, Any]:
        """Heuristic fallback when model is not loaded."""
        hint_rate = features.get("hint_rate", 0.5)
        error_rate = features.get("error_rate", 0.3)
        solve_time_easy = features.get("avg_solve_time_easy", 120)

        if solve_time_easy < 40 and hint_rate < 0.05:
            label = "Expert"
        elif solve_time_easy < 80 and hint_rate < 0.10:
            label = "Advanced"
        elif solve_time_easy < 120 and hint_rate < 0.20:
            label = "Intermediate"
        elif solve_time_easy < 200:
            label = "Casual"
        else:
            label = "Beginner"

        return {
            "cluster": label,
            "cluster_id": CLUSTER_LABELS.index(label),
            "confidence": 0.5,
            "reasoning": f"Model not loaded — heuristic: '{label}' based on solve time and hint usage.",
        }


# Singleton
skill_clustering_service = SkillClusteringService()
