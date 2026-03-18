"""
Airflow DAG: retrain_gan

Monthly retraining of the GAN generator (Sudoku WGAN-GP).
GAN quality is measured by best generator loss — lower is better.
Triggers ml-service /retrain, waits for the MLflow run, evaluates
g_loss threshold, then registers and promotes to Production.

Schedule : 0 3 * * 0   (Sunday 03:00 UTC, first of every month via
                         catchup=False and monthly schedule)
SLA       : best_g_loss ≤ 0.5  (WGAN-GP generator loss in Wasserstein distance units)
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta

import requests
from airflow import DAG
from airflow.models import Variable
from airflow.operators.python import PythonOperator

# ─── Config ───────────────────────────────────────────────────────────────────

MODEL_NAME    = "gan-generator"
MLFLOW_NAME   = "gan-generator"
G_LOSS_MAX    = 0.5    # lower is better; reject if above this
N_SAMPLES     = 1      # unused for GAN (trains on generated data); kept for API compat
N_TRIALS      = 1      # unused for GAN
POLL_INTERVAL = 60     # check every minute — GAN training takes longer
POLL_TIMEOUT  = 7200   # 2 hours

DEFAULT_ARGS = {
    "owner": "sudoku-ultra",
    "depends_on_past": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=30),
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
    if data.get("status") != "accepted":
        raise ValueError(f"Retrain rejected: {data}")
    context["ti"].xcom_push(key="job_id", value=data["job_id"])
    print(f"[trigger_retrain] job_id={data['job_id']}")


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
            run_id = runs.iloc[0]["run_id"]
            print(f"[poll_mlflow] run completed: run_id={run_id}")
            context["ti"].xcom_push(key="run_id", value=run_id)
            return
        elapsed = int(time.time() - (deadline - POLL_TIMEOUT))
        print(f"[poll_mlflow] waiting for GAN job {job_id} … ({elapsed}s elapsed)")
        time.sleep(POLL_INTERVAL)
    raise TimeoutError(f"GAN retrain job {job_id} timed out after {POLL_TIMEOUT}s")


def evaluate_metrics(**context) -> None:
    import mlflow

    run_id = context["ti"].xcom_pull(task_ids="poll_mlflow", key="run_id")
    uri    = Variable.get("MLFLOW_TRACKING_URI", default_var="http://mlflow:5000")
    mlflow.set_tracking_uri(uri)
    m = mlflow.tracking.MlflowClient().get_run(run_id).data.metrics

    g_loss = m.get("best_g_loss", 999.0)
    print(f"[evaluate_metrics] best_g_loss={g_loss:.4f}")
    if g_loss > G_LOSS_MAX:
        raise ValueError(
            f"best_g_loss {g_loss:.4f} > threshold {G_LOSS_MAX} — "
            "GAN did not converge sufficiently"
        )
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
    dag_id="retrain_gan",
    default_args=DEFAULT_ARGS,
    description="Monthly GAN generator retraining with MLflow promotion",
    schedule_interval="0 3 1 * *",   # 1st of every month, 03:00 UTC
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=["retrain", "ml", "gan", "generation"],
) as dag:

    t1 = PythonOperator(task_id="trigger_retrain",     python_callable=trigger_retrain)
    t2 = PythonOperator(task_id="poll_mlflow",         python_callable=poll_mlflow)
    t3 = PythonOperator(task_id="evaluate_metrics",    python_callable=evaluate_metrics)
    t4 = PythonOperator(task_id="register_and_promote",python_callable=register_and_promote)

    t1 >> t2 >> t3 >> t4
