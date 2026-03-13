"""
Model version registry — tracks model versions, lineage, and metadata.

Provides a JSON-based manifest for model lifecycle management
across training, staging, and production environments.
"""

import json
import hashlib
from pathlib import Path
from datetime import datetime, timezone
from typing import Any


MODEL_DIR = Path("ml/models")
MANIFEST_PATH = MODEL_DIR / "model_manifest.json"


class ModelVersionRegistry:
    """
    Tracks model versions, metadata, and lifecycle stage.

    Stages: development → staging → production → archived
    """

    def __init__(self, manifest_path: Path | None = None) -> None:
        self.manifest_path = manifest_path or MANIFEST_PATH
        self.manifest: dict[str, Any] = {"models": {}, "metadata": {}}
        self._load()

    def _load(self) -> None:
        """Load manifest from disk."""
        if self.manifest_path.exists():
            with open(self.manifest_path) as f:
                self.manifest = json.load(f)

    def _save(self) -> None:
        """Persist manifest to disk."""
        self.manifest_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.manifest_path, "w") as f:
            json.dump(self.manifest, f, indent=2, default=str)

    def register_model(
        self,
        name: str,
        version: str,
        model_path: str,
        metrics: dict[str, Any],
        stage: str = "development",
        tags: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """
        Register a new model version.

        Args:
            name: Model name (e.g. 'difficulty-classifier')
            version: Semantic version (e.g. '1.0.0')
            model_path: Path to the model file
            metrics: Training/eval metrics
            stage: Lifecycle stage
            tags: Optional metadata tags

        Returns:
            The registered model entry.
        """
        # Compute file hash for integrity
        file_hash = self._compute_hash(model_path) if Path(model_path).exists() else None

        entry = {
            "name": name,
            "version": version,
            "model_path": model_path,
            "file_hash": file_hash,
            "metrics": metrics,
            "stage": stage,
            "tags": tags or {},
            "registered_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

        if name not in self.manifest["models"]:
            self.manifest["models"][name] = {"versions": {}, "latest": None, "production": None}

        self.manifest["models"][name]["versions"][version] = entry
        self.manifest["models"][name]["latest"] = version

        # Auto-promote only when this is the very first version
        if len(self.manifest["models"][name]["versions"]) == 1:
            self.manifest["models"][name]["production"] = version
            entry["stage"] = "production"

        self._save()
        return entry

    def promote(self, name: str, version: str, target_stage: str) -> bool:
        """Promote a model version to a target stage."""
        if name not in self.manifest["models"]:
            return False
        if version not in self.manifest["models"][name]["versions"]:
            return False

        entry = self.manifest["models"][name]["versions"][version]
        entry["stage"] = target_stage
        entry["updated_at"] = datetime.now(timezone.utc).isoformat()

        if target_stage == "production":
            # Demote previous production version
            old_prod = self.manifest["models"][name].get("production")
            if old_prod and old_prod != version:
                old_entry = self.manifest["models"][name]["versions"].get(old_prod)
                if old_entry:
                    old_entry["stage"] = "archived"
            self.manifest["models"][name]["production"] = version

        self._save()
        return True

    def get_production_model(self, name: str) -> dict[str, Any] | None:
        """Get the current production model entry."""
        if name not in self.manifest["models"]:
            return None
        prod_version = self.manifest["models"][name].get("production")
        if not prod_version:
            return None
        return self.manifest["models"][name]["versions"].get(prod_version)

    def list_models(self) -> dict[str, Any]:
        """List all registered models with their latest and production versions."""
        result = {}
        for name, data in self.manifest["models"].items():
            result[name] = {
                "latest": data.get("latest"),
                "production": data.get("production"),
                "versions": list(data["versions"].keys()),
            }
        return result

    def _compute_hash(self, filepath: str) -> str:
        """Compute SHA256 hash of a model file."""
        sha256 = hashlib.sha256()
        with open(filepath, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        return sha256.hexdigest()


# Singleton
model_version_registry = ModelVersionRegistry()
