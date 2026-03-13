"""
Model registry — loads and serves ML models at startup.

Each individual ML service (classifier, scanner, etc.) manages its own model
object. This registry calls their .load() methods at startup and tracks load
status for health reporting via list_models().
"""

from __future__ import annotations

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
        Load all available models from local artifact files.
        Called at application startup. Missing artifacts are logged as warnings;
        the service degrades gracefully and routers use heuristic fallbacks.
        """
        logger.info("Loading models from registry...")

        # Import singletons here to avoid circular imports at module level.
        from app.services.classifier_service import classifier
        from app.services.recommender_service import recommender
        from app.services.scanner_service import scanner_service
        from app.services.churn_service import churn_predictor
        from app.services.clustering_service import skill_clustering_service

        _services: list[tuple[str, Any]] = [
            ("difficulty_classifier", classifier),
            ("adaptive_regression",  recommender),
            ("puzzle_scanner",       scanner_service),
            ("churn_predictor",      churn_predictor),
            ("skill_clustering",     skill_clustering_service),
        ]

        for name, service in _services:
            try:
                if service.load():
                    self.register(name, service)
                else:
                    logger.warning(
                        f"Model '{name}' artifact not found — service will use heuristic fallback"
                    )
            except Exception as e:
                logger.warning(f"Failed to load model '{name}': {e}")

        loaded = len(self._models)
        logger.info(f"Model loading complete: {loaded}/5 models loaded")


# Singleton instance
model_registry = ModelRegistry()
