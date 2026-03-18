"""
backup_dag.py — Airflow DAG: daily backup of PostgreSQL and MongoDB to MinIO.

Schedule: 02:00 UTC daily (offset from other nightly DAGs to spread load).

Tasks:
    backup_postgres     — pg_dump → gzip → MinIO
    backup_mongodb      — mongodump → tar.gz → MinIO
    verify_backups      — list today's objects in MinIO, assert sizes > 0
    notify_on_failure   — Slack alert via HTTP operator (callback)

Connections required (set in Airflow UI or env):
    AIRFLOW_CONN_POSTGRES_DEFAULT   — PostgreSQL URI
    AIRFLOW_CONN_MONGO_DEFAULT      — MongoDB URI (if used)
    MINIO_ENDPOINT, MINIO_ACCESS_KEY, MINIO_SECRET_KEY  — env vars
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.operators.python import PythonOperator

# ── Constants ──────────────────────────────────────────────────────────────────
MINIO_ENDPOINT    = os.getenv("MINIO_ENDPOINT",    "http://minio:9000")
MINIO_BUCKET      = os.getenv("MINIO_BUCKET",      "sudoku-ultra-backups")
MINIO_ACCESS_KEY  = os.getenv("MINIO_ACCESS_KEY",  "")
MINIO_SECRET_KEY  = os.getenv("MINIO_SECRET_KEY",  "")
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL",  "")
DEPLOY_ENV        = os.getenv("DEPLOY_ENV",         "production")

# ── Failure callback ───────────────────────────────────────────────────────────
def notify_on_failure(context: dict) -> None:  # noqa: ANN001
    """Send Slack alert when any task fails."""
    if not SLACK_WEBHOOK_URL:
        return
    import urllib.request, json  # noqa: E401
    dag_id  = context["dag"].dag_id
    task_id = context["task_instance"].task_id
    msg     = {
        "text": (
            f":red_circle: *Backup DAG failure*\n"
            f"DAG: `{dag_id}` | Task: `{task_id}` | Env: `{DEPLOY_ENV}`\n"
            f"<{context.get('task_instance').log_url}|View logs>"
        )
    }
    req = urllib.request.Request(
        SLACK_WEBHOOK_URL,
        data=json.dumps(msg).encode(),
        headers={"Content-Type": "application/json"},
    )
    urllib.request.urlopen(req, timeout=10)


# ── Shared env for bash operators ─────────────────────────────────────────────
_BACKUP_ENV = {
    "DEPLOY_ENV":        DEPLOY_ENV,
    "MINIO_ENDPOINT":    MINIO_ENDPOINT,
    "MINIO_BUCKET":      MINIO_BUCKET,
    "MINIO_ACCESS_KEY":  MINIO_ACCESS_KEY,
    "MINIO_SECRET_KEY":  MINIO_SECRET_KEY,
    # Postgres
    "PGHOST":            os.getenv("PGHOST",     "postgres"),
    "PGPORT":            os.getenv("PGPORT",     "5432"),
    "PGUSER":            os.getenv("PGUSER",     "sudoku"),
    "PGPASSWORD":        os.getenv("PGPASSWORD", ""),
    "PGDATABASE":        os.getenv("PGDATABASE", "sudoku_ultra"),
    # MongoDB
    "MONGO_URI":         os.getenv("MONGO_URI",  ""),
    "MONGO_DB":          os.getenv("MONGO_DB",   ""),
    "BACKUP_RETENTION_DAYS": "30",
}


# ── Verify task ────────────────────────────────────────────────────────────────
def verify_backups(**kwargs) -> None:  # noqa: ANN003
    """Assert that today's backup objects exist in MinIO and are non-zero."""
    import boto3  # type: ignore[import]
    from botocore.config import Config  # type: ignore[import]

    s3 = boto3.client(
        "s3",
        endpoint_url=MINIO_ENDPOINT,
        aws_access_key_id=MINIO_ACCESS_KEY,
        aws_secret_access_key=MINIO_SECRET_KEY,
        config=Config(signature_version="s3v4"),
        region_name="us-east-1",
    )

    date_prefix = datetime.utcnow().strftime("%Y%m%d")
    prefixes = [
        f"postgres/{DEPLOY_ENV}/{date_prefix}",
        f"mongodb/{DEPLOY_ENV}/{date_prefix}",
    ]

    errors: list[str] = []
    for prefix in prefixes:
        resp = s3.list_objects_v2(Bucket=MINIO_BUCKET, Prefix=prefix)
        objects = resp.get("Contents", [])
        if not objects:
            errors.append(f"No backup found for prefix: {prefix}")
            continue
        for obj in objects:
            if obj["Size"] == 0:
                errors.append(f"Zero-size backup object: {obj['Key']}")

    if errors:
        raise RuntimeError("Backup verification failed:\n" + "\n".join(errors))

    print(f"Backup verification passed for date prefix: {date_prefix}")


# ── DAG definition ─────────────────────────────────────────────────────────────
with DAG(
    dag_id="backup_dag",
    description="Daily backup of PostgreSQL and MongoDB to MinIO",
    schedule_interval="0 2 * * *",
    start_date=datetime(2024, 1, 1),
    catchup=False,
    max_active_runs=1,
    default_args={
        "owner":             "platform",
        "retries":           2,
        "retry_delay":       timedelta(minutes=5),
        "on_failure_callback": notify_on_failure,
        "execution_timeout": timedelta(hours=2),
    },
    tags=["backup", "platform", "infra"],
) as dag:

    backup_postgres = BashOperator(
        task_id="backup_postgres",
        bash_command="/opt/airflow/dags/../../../infra/backup/backup_postgres.sh",
        env=_BACKUP_ENV,
    )

    backup_mongodb = BashOperator(
        task_id="backup_mongodb",
        bash_command=(
            # Skip if Mongo is not configured
            "if [ -z \"$MONGO_URI\" ]; then "
            "  echo 'MongoDB not configured — skipping'; exit 0; "
            "fi; "
            "/opt/airflow/dags/../../../infra/backup/backup_mongodb.sh"
        ),
        env=_BACKUP_ENV,
    )

    verify = PythonOperator(
        task_id="verify_backups",
        python_callable=verify_backups,
    )

    [backup_postgres, backup_mongodb] >> verify
