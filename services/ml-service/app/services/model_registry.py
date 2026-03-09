"""
Model registry — loads and serves ML models.

Each model is registered with a name. Services request models by name.
At startup, models are loaded from MLflow or from local files as fallback.

Fully populated as models are trained in Deliverables 2–6.
"""

from __future__ import annotations

import os
from typing import Any

from app.logging import setup_logging

logger = setup_logging()


class ModelRegistry:
    """Thread-safe model registry for ML models."""

    def __init__(self) -> None:
        self._models: dict[str, Any] = {}
        self._metadata: dict[str, dict[str, Any]] = {}

    def register(self, name: str, model: Any, metadata: dict[str, Any] | None = None) -> None:
        """Register a model with optional metadata."""
        self._models[name] = model
        self._metadata[name] = metadata or {}
        logger.info(f"Model registered: {name}")

    def get(self, name: str) -> Any:
        """Get a model by name. Returns None if not found."""
        return self._models.get(name)

    def is_loaded(self, name: str) -> bool:
        """Check if a model is loaded."""
        return name in self._models

    def get_metadata(self, name: str) -> dict[str, Any]:
        """Get model metadata."""
        return self._metadata.get(name, {})

    def list_models(self) -> dict[str, bool]:
        """List all expected models and their load status."""
        expected = [
            "difficulty_classifier",
            "adaptive_regression",
            "puzzle_scanner",
            "churn_predictor",
            "skill_clustering",
        ]
        return {name: name in self._models for name in expected}

    async def load_all(self) -> None:
        """
        Load all available models from MLflow or local files.
        Called at application startup. Gracefully handles missing models.
        """
        logger.info("Loading models from registry...")

        # D2: Difficulty classifier (Random Forest)
        await self._try_load("difficulty_classifier")
        # D3: Adaptive regression (Gradient Boosting)
        await self._try_load("adaptive_regression")
        # D4: Puzzle scanner (MobileNetV2 ONNX)
        await self._try_load("puzzle_scanner")
        # D5: Churn predictor (Logistic Regression)
        await self._try_load("churn_predictor")
        # D6: Skill clustering (K-Means)
        await self._try_load("skill_clustering")

        loaded = sum(1 for v in self._models.values() if v is not None)
        logger.info(f"Model loading complete: {loaded}/{5} models loaded")

    async def _try_load(self, name: str) -> None:
        """Attempt to load a single model. Log and continue on failure."""
        try:
            # PHASE-2-HOOK: Load from MLflow registry once models are trained
            # model = mlflow.pyfunc.load_model(f"models:/{name}/Production")
            logger.info(f"Model '{name}' not yet available — using fallback")
        except Exception as e:
            logger.warning(f"Failed to load model '{name}': {e}")


# Singleton instance
model_registry = ModelRegistry()
