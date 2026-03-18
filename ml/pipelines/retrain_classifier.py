"""
Airflow DAG: retrain_classifier

Weekly retraining of the difficulty-classifier (Random Forest).
Triggers ml-service /retrain, waits for the MLflow run to finish,
evaluates accuracy threshold, then registers and promotes to Production.

Schedule : 0 3 * * 1   (Monday 03:00 UTC)
SLA       : accuracy ≥ 0.88, f1_macro ≥ 0.85
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta

import requests
from airflow import DAG
from airflow.models import Variable
from airflow.operators.python import PythonOperator

# ─── Config ───────────────────────────────────────────────────────────────────

MODEL_NAME      = "difficulty-classifier"
MLFLOW_NAME     = "difficulty-classifier"
ACCURACY_MIN    = 0.88
F1_MACRO_MIN    = 0.85
N_SAMPLES       = 15000
N_TRIALS        = 50
POLL_INTERVAL   = 30   # seconds between MLflow polls
POLL_TIMEOUT    = 2700  # 45 minutes

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
    data = resp.json()
    job_id = data["job_id"]
    print(f"[trigger_retrain] job_id={job_id}")
    context["ti"].xcom_push(key="job_id", value=job_id)


def poll_mlflow(**context) -> None:
    import mlflow

    job_id   = context["ti"].xcom_pull(task_ids="trigger_retrain", key="job_id")
    uri      = Variable.get("MLFLOW_TRACKING_URI", default_var="http://mlflow:5000")
    exp_name = Variable.get("MLFLOW_EXPERIMENT",   default_var="sudoku-ultra")

    mlflow.set_tracking_uri(uri)
    client   = mlflow.tracking.MlflowClient()
    exp      = client.get_experiment_by_name(exp_name)
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
            run_id = runs.iloc[0]["run_id"]
            print(f"[poll_mlflow] run completed: run_id={run_id}")
            context["ti"].xcom_push(key="run_id", value=run_id)
            return
        print(f"[poll_mlflow] waiting for job {job_id} …")
        time.sleep(POLL_INTERVAL)

    raise TimeoutError(f"Retrain job {job_id} did not finish within {POLL_TIMEOUT}s")


def evaluate_metrics(**context) -> None:
    import mlflow

    run_id = context["ti"].xcom_pull(task_ids="poll_mlflow", key="run_id")
    uri    = Variable.get("MLFLOW_TRACKING_URI", default_var="http://mlflow:5000")
    mlflow.set_tracking_uri(uri)
    client = mlflow.tracking.MlflowClient()

    run    = client.get_run(run_id)
    m      = run.data.metrics
    acc    = m.get("test_accuracy", 0.0)
    f1     = m.get("test_f1_macro", 0.0)

    print(f"[evaluate_metrics] accuracy={acc:.4f}  f1_macro={f1:.4f}")
    if acc < ACCURACY_MIN:
        raise ValueError(f"accuracy {acc:.4f} < threshold {ACCURACY_MIN}")
    if f1 < F1_MACRO_MIN:
        raise ValueError(f"f1_macro {f1:.4f} < threshold {F1_MACRO_MIN}")
    print("[evaluate_metrics] PASSED")


def register_and_promote(**context) -> None:
    import mlflow
    from mlflow.tracking import MlflowClient

    run_id = context["ti"].xcom_pull(task_ids="poll_mlflow", key="run_id")
    uri    = Variable.get("MLFLOW_TRACKING_URI", default_var="http://mlflow:5000")
    mlflow.set_tracking_uri(uri)
    client = MlflowClient()

    mv = mlflow.register_model(f"runs:/{run_id}/", MLFLOW_NAME)
    ver = mv.version
    client.transition_model_version_stage(MLFLOW_NAME, ver, "Staging",  archive_existing_versions=False)
    client.transition_model_version_stage(MLFLOW_NAME, ver, "Production", archive_existing_versions=True)
    print(f"[register_and_promote] {MLFLOW_NAME} v{ver} → Production")


# ─── DAG Definition ───────────────────────────────────────────────────────────

with DAG(
    dag_id="retrain_classifier",
    default_args=DEFAULT_ARGS,
    description="Weekly difficulty-classifier retraining with MLflow promotion",
    schedule_interval="0 3 * * 1",
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=["retrain", "ml", "classifier"],
) as dag:

    t1 = PythonOperator(task_id="trigger_retrain",     python_callable=trigger_retrain)
    t2 = PythonOperator(task_id="poll_mlflow",         python_callable=poll_mlflow)
    t3 = PythonOperator(task_id="evaluate_metrics",    python_callable=evaluate_metrics)
    t4 = PythonOperator(task_id="register_and_promote",python_callable=register_and_promote)

    t1 >> t2 >> t3 >> t4
