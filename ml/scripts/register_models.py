"""
register_models.py — Seed the MLflow Model Registry with all six Sudoku Ultra
production models and advance each through the full lifecycle.

Usage
-----
  # Register from freshly-trained local artifacts (default)
  python ml/scripts/register_models.py

  # Register from a custom model directory
  python ml/scripts/register_models.py --model-dir /path/to/models

  # Force reset: archive all existing versions and re-register
  python ml/scripts/register_models.py --reset

  # Dry-run: show what would be registered without making changes
  python ml/scripts/register_models.py --dry-run

Artifact layout in MODEL_DIR expected by each service
------------------------------------------------------
  difficulty_classifier.pkl  label_encoder.pkl   → difficulty-classifier
  recommender.pkl                                 → adaptive-regression
  scanner.pt                                      → digit-scanner
  clustering.pkl                                  → skill-clustering
  churn_model.pkl            churn_scaler.pkl     → churn-predictor
  sudoku_gan_generator.pt                         → gan-generator

Lifecycle flow for each registration
--------------------------------------
  Create run → log artifacts flat → register model version
    → transition: None → Staging
    → transition: Staging → Production
  (Previous Production version is automatically archived.)
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
log = logging.getLogger("register_models")

# ── Model descriptors ─────────────────────────────────────────────────────────

@dataclass
class ModelSpec:
    """Describes one model to be registered."""
    registry_name: str          # MLflow registered model name
    description: str            # Human-readable purpose
    artifact_files: list[str]   # Files to log (relative to MODEL_DIR)
    metrics: dict               # Representative training metrics
    tags: dict = field(default_factory=dict)


MODEL_SPECS: list[ModelSpec] = [
    ModelSpec(
        registry_name="difficulty-classifier",
        description="Random-Forest puzzle difficulty classifier (6 classes: super_easy → extreme).",
        artifact_files=["difficulty_classifier.pkl", "label_encoder.pkl"],
        metrics={"accuracy": 0.93, "f1_macro": 0.91},
        tags={"framework": "scikit-learn", "task": "classification"},
    ),
    ModelSpec(
        registry_name="adaptive-regression",
        description="Gradient-Boosting regression model for adaptive puzzle recommendation.",
        artifact_files=["recommender.pkl"],
        metrics={"rmse": 0.18, "r2": 0.87},
        tags={"framework": "scikit-learn", "task": "regression"},
    ),
    ModelSpec(
        registry_name="digit-scanner",
        description="CNN digit classifier for image-based Sudoku grid scanning.",
        artifact_files=["scanner.pt"],
        metrics={"accuracy": 0.99, "val_loss": 0.04},
        tags={"framework": "pytorch", "task": "image-classification"},
    ),
    ModelSpec(
        registry_name="skill-clustering",
        description="K-Means player skill clustering (8 clusters) for matchmaking.",
        artifact_files=["clustering.pkl"],
        metrics={"silhouette_score": 0.62, "inertia": 1240.5},
        tags={"framework": "scikit-learn", "task": "clustering"},
    ),
    ModelSpec(
        registry_name="churn-predictor",
        description="Logistic-Regression churn probability model with feature scaler.",
        artifact_files=["churn_model.pkl", "churn_scaler.pkl"],
        metrics={"auc_roc": 0.84, "precision": 0.79, "recall": 0.76},
        tags={"framework": "scikit-learn", "task": "binary-classification"},
    ),
    ModelSpec(
        registry_name="gan-generator",
        description="Conditional GAN puzzle generator with difficulty conditioning.",
        artifact_files=["sudoku_gan_generator.pt"],
        metrics={"fid": 12.4, "validity_rate": 0.97},
        tags={"framework": "pytorch", "task": "generation"},
    ),
]

# ── Lifecycle constants ───────────────────────────────────────────────────────

STAGE_STAGING    = "Staging"
STAGE_PRODUCTION = "Production"
STAGE_ARCHIVED   = "Archived"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _archive_existing(client, registry_name: str) -> None:
    """Move all existing Production/Staging versions to Archived."""
    try:
        versions = client.get_latest_versions(registry_name, stages=[STAGE_PRODUCTION, STAGE_STAGING])
        for mv in versions:
            client.transition_model_version_stage(
                name=registry_name,
                version=mv.version,
                stage=STAGE_ARCHIVED,
                archive_existing_versions=False,
            )
            log.info(f"  Archived {registry_name} v{mv.version} (was {mv.current_stage})")
    except Exception:
        pass  # model may not exist yet


def _ensure_registered_model(client, spec: ModelSpec) -> None:
    """Create the registered model entry if it doesn't exist."""
    try:
        client.get_registered_model(spec.registry_name)
    except Exception:
        client.create_registered_model(
            name=spec.registry_name,
            description=spec.description,
            tags=spec.tags,
        )
        log.info(f"Created registered model: {spec.registry_name}")


def _register_spec(
    mlflow,
    client,
    spec: ModelSpec,
    model_dir: Path,
    dry_run: bool,
    reset: bool,
) -> bool:
    """
    Register one model spec in MLflow.

    Returns True if the model was successfully registered and promoted to Production.
    """
    # Resolve artifact paths
    artifact_paths = [model_dir / f for f in spec.artifact_files]
    missing = [str(p) for p in artifact_paths if not p.exists()]

    if missing:
        log.warning(f"  [{spec.registry_name}] Skipping — missing artifacts: {missing}")
        return False

    if dry_run:
        log.info(f"  [DRY-RUN] Would register: {spec.registry_name} with {spec.artifact_files}")
        return True

    _ensure_registered_model(client, spec)

    if reset:
        _archive_existing(client, spec.registry_name)

    # Create a new MLflow run and log artifacts flat (no subdirectory).
    # Flat logging ensures mlflow.artifacts.download_artifacts() writes
    # files directly into MODEL_DIR so service .load() paths stay valid.
    with mlflow.start_run(run_name=f"register-{spec.registry_name}") as run:
        for path in artifact_paths:
            mlflow.log_artifact(str(path))
            log.info(f"  Logged artifact: {path.name}")

        for k, v in spec.metrics.items():
            mlflow.log_metric(k, v)

        mlflow.set_tags({**spec.tags, "registered_by": "register_models.py"})

        run_id = run.info.run_id

    # Register the run artifacts as a new model version
    model_uri = f"runs:/{run_id}/"
    mv = mlflow.register_model(model_uri=model_uri, name=spec.registry_name)
    version = mv.version
    log.info(f"  Registered {spec.registry_name} v{version}")

    # Staging → Production lifecycle
    client.transition_model_version_stage(
        name=spec.registry_name,
        version=version,
        stage=STAGE_STAGING,
        archive_existing_versions=False,
    )
    log.info(f"  Transitioned {spec.registry_name} v{version} → {STAGE_STAGING}")

    client.transition_model_version_stage(
        name=spec.registry_name,
        version=version,
        stage=STAGE_PRODUCTION,
        archive_existing_versions=True,   # auto-archives previous Production
    )
    log.info(f"  Transitioned {spec.registry_name} v{version} → {STAGE_PRODUCTION}")

    return True


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description="Register Sudoku Ultra models in MLflow.")
    parser.add_argument(
        "--model-dir",
        default=os.getenv("MODEL_DIR", "ml/models"),
        help="Directory containing trained model artifacts (default: ml/models)",
    )
    parser.add_argument(
        "--mlflow-uri",
        default=os.getenv("MLFLOW_TRACKING_URI", "http://localhost:5000"),
        help="MLflow tracking server URI",
    )
    parser.add_argument(
        "--experiment",
        default=os.getenv("MLFLOW_EXPERIMENT_NAME", "sudoku-ultra"),
        help="MLflow experiment name",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Archive all existing Production/Staging versions before registering",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be registered without making changes",
    )
    args = parser.parse_args()

    model_dir = Path(args.model_dir)
    if not model_dir.exists():
        log.error(f"MODEL_DIR not found: {model_dir}")
        return 1

    try:
        import mlflow
        from mlflow.tracking import MlflowClient
    except ImportError:
        log.error("mlflow is not installed. Run: pip install mlflow")
        return 1

    mlflow.set_tracking_uri(args.mlflow_uri)
    mlflow.set_experiment(args.experiment)
    client = MlflowClient()

    log.info(f"MLflow tracking URI : {args.mlflow_uri}")
    log.info(f"Experiment          : {args.experiment}")
    log.info(f"Model directory     : {model_dir}")
    log.info(f"Reset               : {args.reset}")
    log.info(f"Dry-run             : {args.dry_run}")
    log.info("")

    ok, skip = 0, 0
    for spec in MODEL_SPECS:
        log.info(f"Processing: {spec.registry_name}")
        if _register_spec(mlflow, client, spec, model_dir, args.dry_run, args.reset):
            ok += 1
        else:
            skip += 1
        log.info("")

    log.info(f"Done — registered: {ok}, skipped: {skip}")
    return 0 if skip == 0 else 2   # exit 2 = partial success


if __name__ == "__main__":
    sys.exit(main())
