"""
MLOps router — model versioning, monitoring, retraining triggers.
"""

from fastapi import APIRouter, BackgroundTasks
from pydantic import BaseModel, Field

from app.services.model_version_registry import model_version_registry
from app.services.monitoring_service import monitoring_service

router = APIRouter(prefix="/api/v1/mlops", tags=["mlops"])


# ─── Model Registry ───────────────────────────────────────────────────────────


@router.get("/models")
async def list_models():
    """List all registered models with versions and stages."""
    return model_version_registry.list_models()


class RegisterModelRequest(BaseModel):
    name: str = Field(..., description="Model name")
    version: str = Field(..., description="Semantic version")
    model_path: str = Field(..., description="Path to model file")
    metrics: dict = Field(default_factory=dict, description="Training metrics")
    stage: str = Field("development", description="Lifecycle stage")
    tags: dict[str, str] = Field(default_factory=dict, description="Tags")


@router.post("/models/register")
async def register_model(req: RegisterModelRequest):
    """Register a new model version."""
    entry = model_version_registry.register_model(
        name=req.name,
        version=req.version,
        model_path=req.model_path,
        metrics=req.metrics,
        stage=req.stage,
        tags=req.tags,
    )
    return {"status": "registered", "entry": entry}


class PromoteRequest(BaseModel):
    name: str
    version: str
    target_stage: str = Field("production", description="Target stage")


@router.post("/models/promote")
async def promote_model(req: PromoteRequest):
    """Promote a model version to a target stage."""
    success = model_version_registry.promote(req.name, req.version, req.target_stage)
    if success:
        return {"status": "promoted", "name": req.name, "version": req.version, "stage": req.target_stage}
    return {"status": "failed", "error": "Model or version not found"}


@router.get("/models/{name}/production")
async def get_production_model(name: str):
    """Get the current production model for a given name."""
    entry = model_version_registry.get_production_model(name)
    if entry:
        return entry
    return {"error": f"No production model found for '{name}'"}


# ─── Monitoring ────────────────────────────────────────────────────────────────


@router.get("/monitoring/metrics")
async def get_monitoring_metrics():
    """Get real-time model monitoring metrics."""
    return monitoring_service.get_metrics()


class DriftCheckRequest(BaseModel):
    reference_distribution: dict[str, float] = Field(
        ..., description="Expected class distribution for drift comparison"
    )


@router.post("/monitoring/drift")
async def check_drift(req: DriftCheckRequest):
    """Check for class distribution drift against a reference."""
    return monitoring_service.detect_drift(req.reference_distribution)


# ─── Retraining ────────────────────────────────────────────────────────────────

# Supported model names and their canonical artifact paths.
_SUPPORTED_MODELS = {
    "difficulty-classifier",
    "adaptive-difficulty",
    "digit-scanner",
    "skill-clustering",
    "churn-predictor",
}


class RetrainRequest(BaseModel):
    model_name: str = Field(..., description=(
        "Which model to retrain. One of: "
        "difficulty-classifier, adaptive-difficulty, digit-scanner, "
        "skill-clustering, churn-predictor"
    ))
    n_samples: int = Field(10000, ge=100, description="Training samples")
    n_trials: int = Field(50, ge=5, description="Optuna trials (ignored for models without HPO)")


@router.post("/retrain")
async def trigger_retraining(req: RetrainRequest, background_tasks: BackgroundTasks):
    """
    Trigger model retraining as a background task.

    Returns immediately with a job ID. Retraining runs asynchronously.
    Supported models: difficulty-classifier, adaptive-difficulty,
    digit-scanner, skill-clustering, churn-predictor.
    """
    if req.model_name not in _SUPPORTED_MODELS:
        return {
            "status": "rejected",
            "error": f"Unknown model '{req.model_name}'. Supported: {sorted(_SUPPORTED_MODELS)}",
        }

    import uuid
    job_id = str(uuid.uuid4())[:8]

    background_tasks.add_task(
        _run_retraining, req.model_name, req.n_samples, req.n_trials, job_id,
    )

    return {
        "status": "accepted",
        "job_id": job_id,
        "model_name": req.model_name,
        "message": f"Retraining started in background (job {job_id})",
    }


async def _run_retraining(
    model_name: str,
    n_samples: int,
    n_trials: int,
    job_id: str,
) -> None:
    """Execute model retraining (runs in background)."""
    from app.logging import setup_logging
    logger = setup_logging()

    try:
        if model_name == "difficulty-classifier":
            from app.ml.train_classifier import train_and_save
            metrics = train_and_save(n_samples=n_samples, n_trials=n_trials)
            model_version_registry.register_model(
                name="difficulty-classifier",
                version=f"auto-{job_id}",
                model_path="ml/models/difficulty_classifier.pkl",
                metrics={"test_accuracy": metrics["test_accuracy"]},
                stage="staging",
                tags={"job_id": job_id, "trigger": "api"},
            )

        elif model_name == "adaptive-difficulty":
            from app.ml.train_regression import train_and_save
            metrics = train_and_save(n_samples=n_samples, n_trials=n_trials)
            model_version_registry.register_model(
                name="adaptive-difficulty",
                version=f"auto-{job_id}",
                model_path="ml/models/adaptive_regression.pkl",
                metrics={"test_rmse": metrics["test_rmse"]},
                stage="staging",
                tags={"job_id": job_id, "trigger": "api"},
            )

        elif model_name == "digit-scanner":
            from app.ml.train_scanner import train_and_save
            # train_scanner uses samples_per_class (per digit class, 10 classes total).
            # Map n_samples → samples_per_class so the caller interface stays consistent.
            samples_per_class = max(100, n_samples // 10)
            metrics = train_and_save(samples_per_class=samples_per_class)
            model_version_registry.register_model(
                name="digit-scanner",
                version=f"auto-{job_id}",
                model_path="ml/models/scanner.pt",
                metrics={"best_val_accuracy": metrics["best_val_accuracy"]},
                stage="staging",
                tags={"job_id": job_id, "trigger": "api"},
            )

        elif model_name == "skill-clustering":
            from app.ml.train_clustering import train_and_save
            # train_clustering has no Optuna HPO; n_trials is intentionally ignored.
            metrics = train_and_save(n_samples=n_samples)
            model_version_registry.register_model(
                name="skill-clustering",
                version=f"auto-{job_id}",
                model_path="ml/models/skill_clustering.pkl",
                metrics={"silhouette_score": metrics["silhouette_score"]},
                stage="staging",
                tags={"job_id": job_id, "trigger": "api"},
            )

        elif model_name == "churn-predictor":
            from app.ml.train_churn import train_and_save
            metrics = train_and_save(n_samples=n_samples, n_trials=n_trials)
            model_version_registry.register_model(
                name="churn-predictor",
                version=f"auto-{job_id}",
                model_path="ml/models/churn_predictor.pkl",
                metrics={
                    "test_auc_roc": metrics["test_auc_roc"],
                    "test_f1": metrics["test_f1"],
                },
                stage="staging",
                tags={"job_id": job_id, "trigger": "api"},
            )

        else:
            # Should never reach here — validated at the endpoint level above.
            raise ValueError(f"Unknown model: {model_name}")

        logger.info(f"[Retrain] Job {job_id} completed successfully for '{model_name}'")

    except Exception as e:
        logger.error(f"[Retrain] Job {job_id} failed for '{model_name}': {e}")
