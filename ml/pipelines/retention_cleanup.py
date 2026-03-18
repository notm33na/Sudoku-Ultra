"""
retention_cleanup.py — Airflow DAG for data retention enforcement.

Deletes or archives data that has exceeded the configured retention period.
Runs daily at 03:30 UTC.

Retention policy (configured via Airflow Variables or defaults below):
  RETENTION_GAME_SESSIONS_DAYS      365   raw game_sessions (1 year)
  RETENTION_ANOMALY_REPORTS_DAYS    180   anomaly_reports_daily DuckDB table (6 months)
  RETENTION_WAREHOUSE_FACT_DAYS     730   warehouse fact tables (2 years)
  RETENTION_GDPR_AUDIT_DAYS        1825   gdpr_deletion_log (5 years — legal requirement)
  RETENTION_KAFKA_EVENTS_DAYS        90   JSONL event files on disk (3 months)

Tasks
-----
  cleanup_pg_sessions      — DELETE old game_sessions rows from PostgreSQL
  cleanup_duckdb_warehouse — DELETE old fact rows from DuckDB warehouse
  cleanup_kafka_events     — Delete old JSONL event files from EVENTS_DIR
  report_retention         — Log retention statistics
"""

from __future__ import annotations

import logging
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

logger = logging.getLogger("retention_cleanup")

from airflow import DAG
from airflow.models import Variable
from airflow.operators.python import PythonOperator

# ── Defaults ──────────────────────────────────────────────────────────────────

DEFAULT_ARGS = {
    "owner": "data-team",
    "depends_on_past": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
    "email_on_failure": False,
}

WAREHOUSE_PATH = os.getenv("DUCKDB_WAREHOUSE_PATH", "/app/data/warehouse.duckdb")
EVENTS_DIR = Path(os.getenv("EVENTS_DIR", "/data/events"))


def _retention_days(var_name: str, default: int) -> int:
    try:
        return int(Variable.get(var_name, default_var=str(default)))
    except Exception:
        return default


# ── Tasks ─────────────────────────────────────────────────────────────────────

def cleanup_pg_sessions(**context) -> None:
    """Delete game_sessions rows older than RETENTION_GAME_SESSIONS_DAYS."""
    import psycopg2

    days = _retention_days("RETENTION_GAME_SESSIONS_DAYS", 365)
    cutoff = date.today() - timedelta(days=days)
    db_url = Variable.get("DATABASE_URL")

    pg = psycopg2.connect(db_url)
    try:
        with pg.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM game_sessions WHERE started_at < %s",
                (cutoff,),
            )
            count = cur.fetchone()[0]
            logger.info(f"game_sessions: {count} rows older than {cutoff} to delete")

            if count > 0:
                cur.execute(
                    "DELETE FROM game_sessions WHERE started_at < %s",
                    (cutoff,),
                )
                logger.info(f"Deleted {cur.rowcount} game_sessions rows older than {cutoff}")

        pg.commit()
    finally:
        pg.close()


def cleanup_duckdb_warehouse(**context) -> None:
    """Delete old fact rows and DuckDB aggregate rows past retention."""
    import duckdb

    fact_days      = _retention_days("RETENTION_WAREHOUSE_FACT_DAYS", 730)
    anomaly_days   = _retention_days("RETENTION_ANOMALY_REPORTS_DAYS", 180)
    fact_cutoff    = date.today() - timedelta(days=fact_days)
    anomaly_cutoff = date.today() - timedelta(days=anomaly_days)

    wh_path = Path(WAREHOUSE_PATH)
    if not wh_path.exists():
        logger.warning(f"Warehouse not found at {wh_path} — skipping.")
        return

    duck = duckdb.connect(str(wh_path))
    try:
        fact_cutoff_key = int(fact_cutoff.strftime("%Y%m%d"))

        # fact_game_session
        duck.execute(
            "DELETE FROM fact_game_session WHERE date_key < ?", [fact_cutoff_key]
        )
        logger.info(f"fact_game_session: deleted rows with date_key < {fact_cutoff_key}")

        # fact_match
        duck.execute(
            "DELETE FROM fact_match WHERE date_key < ?", [fact_cutoff_key]
        )
        logger.info(f"fact_match: deleted rows with date_key < {fact_cutoff_key}")

        # anomaly_reports_daily (if table exists)
        try:
            duck.execute(
                "DELETE FROM anomaly_reports_daily WHERE date < ?", [anomaly_cutoff]
            )
            logger.info(f"anomaly_reports_daily: deleted rows older than {anomaly_cutoff}")
        except Exception:
            pass  # Table may not exist

        # daily_active_users (same cutoff as anomaly)
        try:
            duck.execute(
                "DELETE FROM daily_active_users WHERE date < ?", [anomaly_cutoff]
            )
        except Exception:
            pass

        duck.commit()
    finally:
        duck.close()


def cleanup_kafka_events(**context) -> None:
    """Delete JSONL event files from EVENTS_DIR older than retention period."""
    days = _retention_days("RETENTION_KAFKA_EVENTS_DAYS", 90)
    cutoff = date.today() - timedelta(days=days)
    deleted = 0
    errors = 0

    if not EVENTS_DIR.exists():
        logger.info(f"Events dir {EVENTS_DIR} not found — skipping.")
        return

    for subdir in EVENTS_DIR.iterdir():
        if not subdir.is_dir():
            continue
        for f in subdir.glob("*.jsonl"):
            try:
                # Filename format: YYYY-MM-DD.jsonl
                file_date = date.fromisoformat(f.stem)
                if file_date < cutoff:
                    f.unlink()
                    deleted += 1
            except ValueError:
                pass  # Non-date filename
            except Exception as exc:
                logger.warning(f"Could not delete {f}: {exc}")
                errors += 1

    logger.info(f"Kafka events cleanup: deleted={deleted} errors={errors} (cutoff={cutoff})")


def report_retention(**context) -> None:
    """Log a summary of current retention state."""
    import duckdb

    lines = ["=== Retention Report ==="]
    lines.append(f"Run date: {date.today()}")

    wh_path = Path(WAREHOUSE_PATH)
    if wh_path.exists():
        duck = duckdb.connect(str(wh_path), read_only=True)
        try:
            for table in ("fact_game_session", "fact_match"):
                try:
                    row = duck.execute(
                        f"SELECT COUNT(*), MIN(date_key), MAX(date_key) FROM {table}"
                    ).fetchone()
                    lines.append(
                        f"  {table}: {row[0]} rows, date_key range [{row[1]}, {row[2]}]"
                    )
                except Exception:
                    lines.append(f"  {table}: (not available)")
        finally:
            duck.close()
    else:
        lines.append("  Warehouse not found.")

    for line in lines:
        logger.info(line)


# ── DAG Definition ────────────────────────────────────────────────────────────

with DAG(
    dag_id="retention_cleanup",
    default_args=DEFAULT_ARGS,
    description="Daily data retention enforcement across PostgreSQL and DuckDB",
    schedule_interval="30 3 * * *",   # 03:30 UTC daily
    start_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
    catchup=False,
    tags=["retention", "gdpr", "cleanup"],
) as dag:

    t_pg = PythonOperator(
        task_id="cleanup_pg_sessions",
        python_callable=cleanup_pg_sessions,
    )

    t_duckdb = PythonOperator(
        task_id="cleanup_duckdb_warehouse",
        python_callable=cleanup_duckdb_warehouse,
    )

    t_kafka = PythonOperator(
        task_id="cleanup_kafka_events",
        python_callable=cleanup_kafka_events,
    )

    t_report = PythonOperator(
        task_id="report_retention",
        python_callable=report_retention,
    )

    [t_pg, t_duckdb, t_kafka] >> t_report
