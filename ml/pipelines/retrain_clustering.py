"""
Airflow DAG: retrain_clustering

Weekly retraining of the skill-clustering model (K-Means, 8 clusters).
Triggers ml-service /retrain, waits for the MLflow run to finish,
evaluates silhouette score threshold, then registers and promotes.

Schedule : 0 2 * * 0   (Sunday 02:00 UTC — same schedule as skill_clustering DAG
                         but retrain_clustering replaces the model, while
                         skill_clustering.py re-scores users with the current model)
SLA       : silhouette_score ≥ 0.50
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta

import requests
from airflow import DAG
from airflow.models import Variable
from airflow.operators.python import PythonOperator

# ─── Config ───────────────────────────────────────────────────────────────────

MODEL_NAME       = "skill-clustering"
MLFLOW_NAME      = "skill-clustering"
SILHOUETTE_MIN   = 0.50
N_SAMPLES        = 10000
N_TRIALS         = 1     # K-Means has no HPO
POLL_INTERVAL    = 30
POLL_TIMEOUT     = 1800  # 30 min

DEFAULT_ARGS = {
    "owner": "sudoku-ultra",
    "depends_on_past": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=20),
    "email_on_failure": False,
}

# ─── Tasks ────────────────────────────────────────────────────────────────────


def trigger_retrain(**context) -> None:
    ml_url = Variable.get("ML_SERVICE_URL", default_var="http://ml-service:3003")
    resp = requests.post(
        f"{ml_url}/api/v1/mlops/retrain",
        json={"model_name": MODEL_NAME, "n_samples": N_SAMPLES, "n_trials": N_TRIALS},
        timeout=30,
    )
    resp.raise_for_status()
    context["ti"].xcom_push(key="job_id", value=resp.json()["job_id"])


def poll_mlflow(**context) -> None:
    import mlflow

    job_id   = context["ti"].xcom_pull(task_ids="trigger_retrain", key="job_id")
    uri      = Variable.get("MLFLOW_TRACKING_URI", default_var="http://mlflow:5000")
    exp_name = Variable.get("MLFLOW_EXPERIMENT",   default_var="sudoku-ultra")
    mlflow.set_tracking_uri(uri)
    exp = mlflow.tracking.MlflowClient().get_experiment_by_name(exp_name)
    if exp is None:
        raise ValueError(f"MLflow experiment '{exp_name}' not found")

    deadline = time.time() + POLL_TIMEOUT
    while time.time() < deadline:
        runs = mlflow.search_runs(
            experiment_ids=[exp.experiment_id],
            filter_string=f"tags.job_id = '{job_id}' AND attributes.status = 'FINISHED'",
            max_results=1,
        )
        if not runs.empty:
            context["ti"].xcom_push(key="run_id", value=runs.iloc[0]["run_id"])
            return
        print(f"[poll_mlflow] waiting for job {job_id} …")
        time.sleep(POLL_INTERVAL)
    raise TimeoutError(f"Retrain job {job_id} timed out after {POLL_TIMEOUT}s")


def evaluate_metrics(**context) -> None:
    import mlflow

    run_id = context["ti"].xcom_pull(task_ids="poll_mlflow", key="run_id")
    uri    = Variable.get("MLFLOW_TRACKING_URI", default_var="http://mlflow:5000")
    mlflow.set_tracking_uri(uri)
    m = mlflow.tracking.MlflowClient().get_run(run_id).data.metrics

    sil = m.get("silhouette_score", 0.0)
    print(f"[evaluate_metrics] silhouette_score={sil:.4f}")
    if sil < SILHOUETTE_MIN:
        raise ValueError(f"silhouette_score {sil:.4f} < threshold {SILHOUETTE_MIN}")
    print("[evaluate_metrics] PASSED")


def register_and_promote(**context) -> None:
    import mlflow
    from mlflow.tracking import MlflowClient

    run_id = context["ti"].xcom_pull(task_ids="poll_mlflow", key="run_id")
    uri    = Variable.get("MLFLOW_TRACKING_URI", default_var="http://mlflow:5000")
    mlflow.set_tracking_uri(uri)
    client = MlflowClient()

    mv = mlflow.register_model(f"runs:/{run_id}/", MLFLOW_NAME)
    client.transition_model_version_stage(MLFLOW_NAME, mv.version, "Staging",   archive_existing_versions=False)
    client.transition_model_version_stage(MLFLOW_NAME, mv.version, "Production",archive_existing_versions=True)
    print(f"[register_and_promote] {MLFLOW_NAME} v{mv.version} → Production")


# ─── DAG Definition ───────────────────────────────────────────────────────────

with DAG(
    dag_id="retrain_clustering",
    default_args=DEFAULT_ARGS,
    description="Weekly skill-clustering retraining with MLflow promotion",
    schedule_interval="0 2 * * 0",
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=["retrain", "ml", "clustering"],
) as dag:

    t1 = PythonOperator(task_id="trigger_retrain",     python_callable=trigger_retrain)
    t2 = PythonOperator(task_id="poll_mlflow",         python_callable=poll_mlflow)
    t3 = PythonOperator(task_id="evaluate_metrics",    python_callable=evaluate_metrics)
    t4 = PythonOperator(task_id="register_and_promote",python_callable=register_and_promote)

    t1 >> t2 >> t3 >> t4
