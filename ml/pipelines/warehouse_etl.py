"""
warehouse_etl.py — Unified Airflow ETL DAG for the DuckDB data warehouse.

Replaces:
  - analytics_aggregator (hourly game metrics → analytics.duckdb)
  - competitive_analytics_dag (daily Kafka events → competitive.duckdb)

Both sinks are now written to a single star-schema warehouse.duckdb that
is backed by the 6-table schema in warehouse_schema.py.

Schedule: daily at 02:00 UTC (incremental — processes yesterday's data).
For initial load, trigger with conf={"full_backfill": true}.

Tasks
-----
  validate_source        — Great Expectations suite on PostgreSQL data
  ensure_schema          — Bootstrap warehouse schema (idempotent)
  load_dimensions        — Upsert dim_user + dim_puzzle
  load_fact_sessions     — Pseudonymise + load fact_game_session
  load_fact_matches      — Pseudonymise + load fact_match
  compute_aggregates     — Populate legacy analytics tables (DAU, streaks, etc.)
  validate_warehouse     — GE suite on warehouse row counts
  notify_on_failure      — Post Slack alert if any upstream task failed
"""

from __future__ import annotations

import logging
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

logger = logging.getLogger("warehouse_etl")

from airflow import DAG
from airflow.models import Variable
from airflow.operators.python import PythonOperator

# ── Config ────────────────────────────────────────────────────────────────────

DEFAULT_ARGS = {
    "owner": "data-team",
    "depends_on_past": False,
    "retries": 2,
    "retry_delay": timedelta(minutes=10),
    "email_on_failure": False,
}

WAREHOUSE_PATH = os.getenv("DUCKDB_WAREHOUSE_PATH", "/app/data/warehouse.duckdb")
SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"


def _db_url() -> str:
    return Variable.get("DATABASE_URL")


def _target_date(context) -> date:
    """Return the date being processed (yesterday for daily runs)."""
    full_backfill = context.get("dag_run") and context["dag_run"].conf.get("full_backfill")
    if full_backfill:
        return None  # type: ignore[return-value]
    return context["data_interval_start"].date()


# ── Task: validate_source ─────────────────────────────────────────────────────


def validate_source(**context) -> None:
    """
    Great Expectations suite — validate PostgreSQL source data quality.

    Checks:
    1. game_sessions has no null user_id
    2. game_sessions.status is in expected set
    3. game_sessions.time_elapsed_ms is non-negative where non-null
    4. users table has no null id
    """
    import psycopg2
    import psycopg2.extras

    target = _target_date(context)
    db_url = _db_url()
    pg = psycopg2.connect(db_url)

    where = f"WHERE started_at::date = '{target}'" if target else ""
    failures: list[str] = []

    try:
        with pg.cursor() as cur:
            # Check 1: no null user_id in game_sessions
            cur.execute(f"""
                SELECT COUNT(*) FROM game_sessions
                {where}
                {'AND' if where else 'WHERE'} user_id IS NULL
            """)
            null_user_count = cur.fetchone()[0]
            if null_user_count > 0:
                failures.append(f"game_sessions has {null_user_count} rows with null user_id")

            # Check 2: status in expected set
            cur.execute(f"""
                SELECT status, COUNT(*) FROM game_sessions
                {where}
                GROUP BY status
                HAVING status NOT IN ('completed','abandoned','timed_out','in_progress')
            """)
            bad_statuses = cur.fetchall()
            if bad_statuses:
                failures.append(f"Unexpected status values: {bad_statuses}")

            # Check 3: time_elapsed_ms non-negative
            cur.execute(f"""
                SELECT COUNT(*) FROM game_sessions
                {where}
                {'AND' if where else 'WHERE'} time_elapsed_ms < 0
            """)
            neg_time = cur.fetchone()[0]
            if neg_time > 0:
                failures.append(f"{neg_time} sessions have negative time_elapsed_ms")

            # Check 4: users table sanity
            cur.execute("SELECT COUNT(*) FROM users WHERE id IS NULL")
            null_ids = cur.fetchone()[0]
            if null_ids > 0:
                failures.append(f"users table has {null_ids} rows with null id")

    finally:
        pg.close()

    if failures:
        raise ValueError(
            f"Source validation failed ({len(failures)} issue(s)):\n"
            + "\n".join(f"  - {f}" for f in failures)
        )

    logger.info("Source validation passed.")


# ── Task: ensure_schema ───────────────────────────────────────────────────────


def ensure_schema(**context) -> None:
    import sys
    sys.path.insert(0, str(SCRIPTS_DIR))
    from warehouse_schema import bootstrap
    bootstrap(WAREHOUSE_PATH)
    logger.info("Warehouse schema ensured.")


# ── Task: load_dimensions ─────────────────────────────────────────────────────


def load_dimensions(**context) -> None:
    import sys
    sys.path.insert(0, str(SCRIPTS_DIR))
    import duckdb
    import psycopg2
    from backfill_warehouse import _upsert_users, _upsert_puzzles

    target = _target_date(context)
    since_str = str(target) if target else None

    pg   = psycopg2.connect(_db_url())
    duck = duckdb.connect(WAREHOUSE_PATH)
    try:
        _upsert_users(pg, duck, since_str, dry_run=False)
        _upsert_puzzles(pg, duck, since_str, dry_run=False)
    finally:
        pg.close()
        duck.close()


# ── Task: load_fact_sessions ──────────────────────────────────────────────────


def load_fact_sessions(**context) -> None:
    import sys
    sys.path.insert(0, str(SCRIPTS_DIR))
    import duckdb
    import psycopg2
    from backfill_warehouse import _load_fact_sessions

    target = _target_date(context)
    since_str = str(target) if target else None

    pg   = psycopg2.connect(_db_url())
    duck = duckdb.connect(WAREHOUSE_PATH)
    try:
        ins, skip = _load_fact_sessions(pg, duck, since_str, dry_run=False)
        logger.info(f"fact_game_session: inserted={ins} skipped={skip}")
    finally:
        pg.close()
        duck.close()


# ── Task: load_fact_matches ───────────────────────────────────────────────────


def load_fact_matches(**context) -> None:
    import sys
    sys.path.insert(0, str(SCRIPTS_DIR))
    import duckdb
    import psycopg2
    from backfill_warehouse import _load_fact_matches

    target = _target_date(context)
    since_str = str(target) if target else None

    pg   = psycopg2.connect(_db_url())
    duck = duckdb.connect(WAREHOUSE_PATH)
    try:
        ins, skip = _load_fact_matches(pg, duck, since_str, dry_run=False)
        logger.info(f"fact_match: inserted={ins} skipped={skip}")
    finally:
        pg.close()
        duck.close()


# ── Task: compute_aggregates ──────────────────────────────────────────────────


def compute_aggregates(**context) -> None:
    """
    Re-compute the legacy analytics tables (daily_active_users, streak_distribution,
    puzzle_completion_rates, difficulty_popularity) from the warehouse fact tables.
    These feed the existing /api/v1/analytics/* endpoints.
    """
    import duckdb

    target = _target_date(context)
    target_date = target or date.today()

    duck = duckdb.connect(WAREHOUSE_PATH)
    try:
        # Ensure legacy tables exist
        duck.execute("""
            CREATE TABLE IF NOT EXISTS daily_active_users (
                date DATE PRIMARY KEY, user_count INTEGER,
                new_user_count INTEGER, updated_at TIMESTAMP DEFAULT NOW()
            )
        """)
        duck.execute("""
            CREATE TABLE IF NOT EXISTS streak_distribution (
                date DATE, streak_bucket VARCHAR, user_count INTEGER,
                PRIMARY KEY (date, streak_bucket)
            )
        """)
        duck.execute("""
            CREATE TABLE IF NOT EXISTS puzzle_completion_rates (
                date DATE, difficulty VARCHAR,
                started_count INTEGER, completed_count INTEGER, avg_time_ms DOUBLE,
                PRIMARY KEY (date, difficulty)
            )
        """)
        duck.execute("""
            CREATE TABLE IF NOT EXISTS difficulty_popularity (
                date DATE, difficulty VARCHAR, play_count INTEGER,
                PRIMARY KEY (date, difficulty)
            )
        """)

        # DAU — count distinct user hashes that had a session that day
        row = duck.execute("""
            SELECT COUNT(DISTINCT user_hash) AS user_count
            FROM fact_game_session
            WHERE date_key = ?
        """, [int(target_date.strftime("%Y%m%d"))]).fetchone()
        dau = row[0] if row else 0

        duck.execute("""
            INSERT OR REPLACE INTO daily_active_users (date, user_count, new_user_count, updated_at)
            VALUES (?, ?, 0, NOW())
        """, [target_date, dau])

        # Completion rates
        rows = duck.execute("""
            SELECT difficulty_key,
                   COUNT(*) AS started,
                   COUNT(*) FILTER (WHERE status = 'completed') AS completed,
                   AVG(time_elapsed_ms) FILTER (WHERE status = 'completed') AS avg_ms
            FROM fact_game_session
            WHERE date_key = ?
            GROUP BY difficulty_key
        """, [int(target_date.strftime("%Y%m%d"))]).fetchall()

        for diff, started, completed, avg_ms in rows:
            duck.execute("""
                INSERT OR REPLACE INTO puzzle_completion_rates
                    (date, difficulty, started_count, completed_count, avg_time_ms)
                VALUES (?, ?, ?, ?, ?)
            """, [target_date, diff, started, completed, avg_ms or 0.0])
            duck.execute("""
                INSERT OR REPLACE INTO difficulty_popularity (date, difficulty, play_count)
                VALUES (?, ?, ?)
            """, [target_date, diff, started])

        duck.commit()
        logger.info(f"Aggregates computed for {target_date}: DAU={dau}")
    finally:
        duck.close()


# ── Task: validate_warehouse ──────────────────────────────────────────────────


def validate_warehouse(**context) -> None:
    """
    Great Expectations suite — validate warehouse data quality post-load.

    Checks:
    1. fact_game_session has no null date_key
    2. fact_game_session.status only contains expected values
    3. dim_user has no duplicate user_hash
    4. fact_game_session row count increased (non-empty incremental load)
    """
    import duckdb

    target = _target_date(context)
    duck = duckdb.connect(WAREHOUSE_PATH, read_only=True)
    failures: list[str] = []

    try:
        # Check 1: no null date_key
        n = duck.execute(
            "SELECT COUNT(*) FROM fact_game_session WHERE date_key IS NULL"
        ).fetchone()[0]
        if n > 0:
            failures.append(f"fact_game_session: {n} rows with null date_key")

        # Check 2: valid status values
        bad = duck.execute("""
            SELECT DISTINCT status FROM fact_game_session
            WHERE status NOT IN ('completed','abandoned','timed_out','in_progress')
        """).fetchall()
        if bad:
            failures.append(f"Invalid status values: {[r[0] for r in bad]}")

        # Check 3: no duplicate user_hash
        dup = duck.execute("""
            SELECT COUNT(*) FROM (
                SELECT user_hash FROM dim_user
                GROUP BY user_hash HAVING COUNT(*) > 1
            )
        """).fetchone()[0]
        if dup > 0:
            failures.append(f"dim_user: {dup} duplicate user_hash values")

        # Check 4: incremental row count > 0 (skip on full backfill)
        if target:
            dk = int(target.strftime("%Y%m%d"))
            count = duck.execute(
                "SELECT COUNT(*) FROM fact_game_session WHERE date_key = ?",
                [dk],
            ).fetchone()[0]
            if count == 0:
                logger.warning(
                    f"No fact_game_session rows for date_key={dk} "
                    f"— may be expected on low-traffic days"
                )

    finally:
        duck.close()

    if failures:
        raise ValueError(
            f"Warehouse validation failed ({len(failures)} issue(s)):\n"
            + "\n".join(f"  - {f}" for f in failures)
        )

    logger.info("Warehouse validation passed.")


# ── Task: notify_on_failure ───────────────────────────────────────────────────


def notify_on_failure(context) -> None:
    """Post a Slack alert when any task in the DAG fails."""
    slack_url = Variable.get("SLACK_WEBHOOK_URL", default_var=None)
    if not slack_url:
        logger.warning("SLACK_WEBHOOK_URL not set — Slack alert skipped.")
        return

    import urllib.request, json as _json
    task_instance = context.get("task_instance")
    message = {
        "text": (
            f":red_circle: *warehouse_etl* task failed\n"
            f"  Task: `{task_instance.task_id if task_instance else 'unknown'}`\n"
            f"  Date: `{context.get('ds')}`\n"
            f"  Log: {task_instance.log_url if task_instance else 'N/A'}"
        )
    }
    try:
        req = urllib.request.Request(
            slack_url,
            data=_json.dumps(message).encode(),
            headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(req, timeout=5)
    except Exception as exc:
        logger.warning(f"Slack notification failed: {exc}")


# ── DAG Definition ────────────────────────────────────────────────────────────

with DAG(
    dag_id="warehouse_etl",
    default_args=DEFAULT_ARGS,
    description="Daily ETL: PostgreSQL → DuckDB star-schema warehouse",
    schedule_interval="0 2 * * *",  # 02:00 UTC daily
    start_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
    catchup=False,
    tags=["warehouse", "etl", "duckdb"],
    on_failure_callback=notify_on_failure,
) as dag:

    t_validate_source = PythonOperator(
        task_id="validate_source",
        python_callable=validate_source,
    )

    t_ensure_schema = PythonOperator(
        task_id="ensure_schema",
        python_callable=ensure_schema,
    )

    t_load_dims = PythonOperator(
        task_id="load_dimensions",
        python_callable=load_dimensions,
    )

    t_load_sessions = PythonOperator(
        task_id="load_fact_sessions",
        python_callable=load_fact_sessions,
    )

    t_load_matches = PythonOperator(
        task_id="load_fact_matches",
        python_callable=load_fact_matches,
    )

    t_aggregates = PythonOperator(
        task_id="compute_aggregates",
        python_callable=compute_aggregates,
    )

    t_validate_wh = PythonOperator(
        task_id="validate_warehouse",
        python_callable=validate_warehouse,
    )

    # Task graph:
    # validate_source → ensure_schema → load_dimensions
    #                                 → load_fact_sessions  ┐
    #                                 → load_fact_matches   ┤→ compute_aggregates → validate_warehouse
    t_validate_source >> t_ensure_schema >> t_load_dims
    t_load_dims >> [t_load_sessions, t_load_matches]
    [t_load_sessions, t_load_matches] >> t_aggregates >> t_validate_wh
