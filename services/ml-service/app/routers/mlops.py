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
    "adaptive-regression",
    "digit-scanner",
    "skill-clustering",
    "churn-predictor",
    "gan-generator",
}


class RetrainRequest(BaseModel):
    model_name: str = Field(..., description=(
        "Which model to retrain. One of: "
        "difficulty-classifier, adaptive-regression, digit-scanner, "
        "skill-clustering, churn-predictor, gan-generator"
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
    """
    Execute model retraining (runs in background).

    Each branch trains the model, logs the run to MLflow with the job_id tag
    so that Airflow DAGs can find it via search_runs(tags.job_id=...), and
    also writes to the JSON-based model_version_registry for backward compat.
    """
    from app.logging import setup_logging
    from app.config import settings
    logger = setup_logging()

    try:
        import mlflow
        mlflow.set_tracking_uri(settings.MLFLOW_TRACKING_URI)
        mlflow.set_experiment(settings.MLFLOW_EXPERIMENT_NAME)

        with mlflow.start_run(
            run_name=f"retrain-{model_name}-{job_id}",
            tags={"job_id": job_id, "model_name": model_name, "trigger": "api"},
        ) as run:
            run_id = run.info.run_id
            mlflow.log_param("n_samples", n_samples)
            mlflow.log_param("n_trials", n_trials)

            if model_name == "difficulty-classifier":
                from app.ml.train_classifier import train_and_save
                metrics = train_and_save(n_samples=n_samples, n_trials=n_trials)
                mlflow.log_metrics({"test_accuracy": metrics["test_accuracy"],
                                    "test_f1_macro": metrics.get("test_f1_macro", 0.0)})
                mlflow.log_artifact("ml/models/difficulty_classifier.pkl")
                mlflow.log_artifact("ml/models/label_encoder.pkl")
                model_version_registry.register_model(
                    name="difficulty-classifier", version=f"auto-{job_id}",
                    model_path="ml/models/difficulty_classifier.pkl",
                    metrics={"test_accuracy": metrics["test_accuracy"]},
                    stage="staging", tags={"job_id": job_id},
                )

            elif model_name == "adaptive-regression":
                from app.ml.train_regression import train_and_save
                metrics = train_and_save(n_samples=n_samples, n_trials=n_trials)
                mlflow.log_metrics({"test_rmse": metrics["test_rmse"],
                                    "test_r2": metrics.get("test_r2", 0.0)})
                mlflow.log_artifact("ml/models/recommender.pkl")
                model_version_registry.register_model(
                    name="adaptive-regression", version=f"auto-{job_id}",
                    model_path="ml/models/recommender.pkl",
                    metrics={"test_rmse": metrics["test_rmse"]},
                    stage="staging", tags={"job_id": job_id},
                )

            elif model_name == "digit-scanner":
                from app.ml.train_scanner import train_and_save
                samples_per_class = max(100, n_samples // 10)
                metrics = train_and_save(samples_per_class=samples_per_class)
                mlflow.log_metrics({"best_val_accuracy": metrics["best_val_accuracy"]})
                mlflow.log_artifact("ml/models/scanner.pt")
                model_version_registry.register_model(
                    name="digit-scanner", version=f"auto-{job_id}",
                    model_path="ml/models/scanner.pt",
                    metrics={"best_val_accuracy": metrics["best_val_accuracy"]},
                    stage="staging", tags={"job_id": job_id},
                )

            elif model_name == "skill-clustering":
                from app.ml.train_clustering import train_and_save
                metrics = train_and_save(n_samples=n_samples)
                mlflow.log_metrics({"silhouette_score": metrics["silhouette_score"]})
                mlflow.log_artifact("ml/models/clustering.pkl")
                model_version_registry.register_model(
                    name="skill-clustering", version=f"auto-{job_id}",
                    model_path="ml/models/clustering.pkl",
                    metrics={"silhouette_score": metrics["silhouette_score"]},
                    stage="staging", tags={"job_id": job_id},
                )

            elif model_name == "churn-predictor":
                from app.ml.train_churn import train_and_save
                metrics = train_and_save(n_samples=n_samples, n_trials=n_trials)
                mlflow.log_metrics({"test_auc_roc": metrics["test_auc_roc"],
                                    "test_f1": metrics["test_f1"]})
                mlflow.log_artifact("ml/models/churn_model.pkl")
                mlflow.log_artifact("ml/models/churn_scaler.pkl")
                model_version_registry.register_model(
                    name="churn-predictor", version=f"auto-{job_id}",
                    model_path="ml/models/churn_model.pkl",
                    metrics={"test_auc_roc": metrics["test_auc_roc"]},
                    stage="staging", tags={"job_id": job_id},
                )

            elif model_name == "gan-generator":
                from app.ml.train_gan import train_and_save
                metrics = train_and_save(epochs=50)
                mlflow.log_metrics({"best_g_loss": metrics["best_g_loss"]})
                mlflow.log_artifact("ml/models/sudoku_gan_generator.pt")
                model_version_registry.register_model(
                    name="gan-generator", version=f"auto-{job_id}",
                    model_path="ml/models/sudoku_gan_generator.pt",
                    metrics={"best_g_loss": metrics["best_g_loss"]},
                    stage="staging", tags={"job_id": job_id},
                )

            else:
                raise ValueError(f"Unknown model: {model_name}")

            mlflow.set_tag("status", "success")

        logger.info(f"[Retrain] Job {job_id} completed for '{model_name}' (run_id={run_id})")

    except Exception as e:
        logger.error(f"[Retrain] Job {job_id} failed for '{model_name}': {e}")
        try:
            mlflow.set_tag("status", "failed")
            mlflow.set_tag("error", str(e)[:200])
        except Exception:
            pass
