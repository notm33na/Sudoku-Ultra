"""
Model registry — loads and serves ML models at startup.

Each individual ML service (classifier, scanner, etc.) manages its own model
object. This registry calls their .load() methods at startup and tracks load
status for health reporting via list_models().

MLflow integration
------------------
At startup, _try_load() attempts to pull the latest Production artifact from
the MLflow Model Registry into MODEL_DIR, then delegates to the service's
existing .load() method. If MLflow is unreachable the service falls back to
whatever artifact is already on disk. Both paths converge on .load(), so no
service internals need to change.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.config import settings
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
            "skill_clustering",
            "churn_predictor",
            "gan_generator",
        ]
        return {name: name in self._models for name in expected}

    # ── MLflow helpers ────────────────────────────────────────────────────

    def _download_from_mlflow(self, mlflow_model_name: str) -> bool:
        """
        Pull Production artifacts from the MLflow registry into MODEL_DIR.

        Artifacts are logged flat (no sub-directory) by register_models.py so
        that existing service .load() paths remain valid after download.

        Returns True if the download succeeded, False on any error.
        """
        try:
            import mlflow  # lazy import — only needed at startup

            mlflow.set_tracking_uri(settings.MLFLOW_TRACKING_URI)
            model_uri = f"models:/{mlflow_model_name}/Production"
            dst = str(Path(settings.MODEL_DIR))
            mlflow.artifacts.download_artifacts(artifact_uri=model_uri, dst_path=dst)
            logger.info(f"MLflow: downloaded '{mlflow_model_name}' → {dst}")
            return True
        except Exception as exc:
            logger.warning(
                f"MLflow unavailable for '{mlflow_model_name}': {exc} "
                "— falling back to local artifact"
            )
            return False

    async def _try_load(
        self,
        registry_name: str,
        mlflow_model_name: str,
        service: Any,
    ) -> None:
        """
        Load a model with MLflow-first, local-fallback strategy.

        1. Attempt to download the Production artifact from MLflow into MODEL_DIR.
           If MLflow is unreachable the step is skipped silently.
        2. Call service.load() which reads from MODEL_DIR.
           If an artifact was freshly downloaded, the service picks it up here.
           If not, it uses whatever is already on disk (or its heuristic fallback).
        3. Register the service in this registry with source metadata.
        """
        mlflow_ok = self._download_from_mlflow(mlflow_model_name)
        source = "mlflow" if mlflow_ok else "local"

        try:
            if service.load():
                self.register(
                    registry_name,
                    service,
                    {"source": source, "mlflow_name": mlflow_model_name},
                )
            else:
                logger.warning(
                    f"Model '{registry_name}' artifact not found — "
                    "service will use heuristic fallback"
                )
        except Exception as exc:
            logger.warning(f"Failed to load model '{registry_name}': {exc}")

    # ── Startup ───────────────────────────────────────────────────────────

    async def load_all(self) -> None:
        """
        Load all six models at application startup.

        For each model: try MLflow Production artifact → fall back to local
        disk → fall back to service heuristic. The service is always registered
        so callers can query is_loaded() to decide whether to use ML or rules.
        """
        logger.info("Loading models from registry...")

        # Lazy imports avoid circular dependencies at module level.
        from app.services.classifier_service import classifier
        from app.services.recommender_service import recommender
        from app.services.scanner_service import scanner_service
        from app.services.churn_service import churn_predictor
        from app.services.clustering_service import skill_clustering_service
        from app.services.gan_service import gan_service

        _services: list[tuple[str, str, Any]] = [
            ("difficulty_classifier", settings.MLFLOW_MODEL_CLASSIFIER,  classifier),
            ("adaptive_regression",   settings.MLFLOW_MODEL_REGRESSION,  recommender),
            ("puzzle_scanner",        settings.MLFLOW_MODEL_SCANNER,      scanner_service),
            ("skill_clustering",      settings.MLFLOW_MODEL_CLUSTERING,   skill_clustering_service),
            ("churn_predictor",       settings.MLFLOW_MODEL_CHURN,        churn_predictor),
            ("gan_generator",         settings.MLFLOW_MODEL_GAN,          gan_service),
        ]

        for registry_name, mlflow_name, service in _services:
            await self._try_load(registry_name, mlflow_name, service)

        loaded = len(self._models)
        logger.info(f"Model loading complete: {loaded}/6 models loaded")


# Singleton instance
model_registry = ModelRegistry()
