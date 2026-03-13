"""
Airflow DAG: analytics_aggregator

Runs hourly. Reads game events from PostgreSQL game_sessions
(with a PHASE-3-HOOK for Kafka consumption) and writes aggregated
metrics to a DuckDB analytics store.

Metrics computed:
  - daily_active_users
  - streak_distribution
  - puzzle_completion_rates (per difficulty)
  - difficulty_popularity

Schedule: 0 * * * *  (top of every hour)

PHASE-3-HOOK: Replace the PostgreSQL source with consumption from
the Kafka topic 'game.session.completed' published by game-service.
"""

from __future__ import annotations

import os
from datetime import date, datetime, timedelta

import duckdb
import psycopg2
from airflow import DAG
from airflow.models import Variable
from airflow.operators.python import PythonOperator

# ─── Config ───────────────────────────────────────────────────────────────────

DEFAULT_ARGS = {
    "owner": "sudoku-ultra",
    "depends_on_past": False,
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
    "email_on_failure": False,
}

# ─── DuckDB Schema Bootstrap ──────────────────────────────────────────────────


def _ensure_schema(duck: duckdb.DuckDBPyConnection) -> None:
    duck.execute("""
        CREATE TABLE IF NOT EXISTS daily_active_users (
            date          DATE PRIMARY KEY,
            user_count    INTEGER,
            new_user_count INTEGER,
            updated_at    TIMESTAMP DEFAULT NOW()
        )
    """)
    duck.execute("""
        CREATE TABLE IF NOT EXISTS streak_distribution (
            date         DATE,
            streak_bucket VARCHAR,
            user_count   INTEGER,
            PRIMARY KEY (date, streak_bucket)
        )
    """)
    duck.execute("""
        CREATE TABLE IF NOT EXISTS puzzle_completion_rates (
            date            DATE,
            difficulty      VARCHAR,
            started_count   INTEGER,
            completed_count INTEGER,
            avg_time_ms     DOUBLE,
            PRIMARY KEY (date, difficulty)
        )
    """)
    duck.execute("""
        CREATE TABLE IF NOT EXISTS difficulty_popularity (
            date        DATE,
            difficulty  VARCHAR,
            play_count  INTEGER,
            PRIMARY KEY (date, difficulty)
        )
    """)


# ─── Tasks ────────────────────────────────────────────────────────────────────


def aggregate_metrics(**context) -> None:
    db_url = Variable.get("DATABASE_URL")
    duckdb_path = Variable.get("DUCKDB_PATH", default_var="/app/data/analytics.duckdb")

    # Ensure directory exists
    os.makedirs(os.path.dirname(duckdb_path), exist_ok=True)

    # PHASE-3-HOOK: Replace this PostgreSQL source with Kafka consumer
    # that reads from 'game.session.completed' and stores in a staging table.
    pg = psycopg2.connect(db_url)
    duck = duckdb.connect(duckdb_path)

    try:
        _ensure_schema(duck)
        today = date.today()

        # ── 1. Daily Active Users ─────────────────────────────────────────────
        with pg.cursor() as cur:
            cur.execute("""
                SELECT
                    COUNT(DISTINCT user_id)                         AS user_count,
                    COUNT(DISTINCT u.id) FILTER (
                        WHERE u.created_at::date = CURRENT_DATE
                    )                                               AS new_user_count
                FROM game_sessions gs
                JOIN users u ON u.id = gs.user_id
                WHERE gs.started_at::date = CURRENT_DATE
            """)
            row = cur.fetchone()
            user_count, new_user_count = row[0] or 0, row[1] or 0

        duck.execute("""
            INSERT OR REPLACE INTO daily_active_users
                (date, user_count, new_user_count, updated_at)
            VALUES (?, ?, ?, NOW())
        """, [today, user_count, new_user_count])

        print(f"[analytics] DAU: {user_count} ({new_user_count} new)")

        # ── 2. Streak Distribution ────────────────────────────────────────────
        with pg.cursor() as cur:
            cur.execute("""
                SELECT
                    CASE
                        WHEN current_streak = 0        THEN '0'
                        WHEN current_streak <= 7       THEN '1-7'
                        WHEN current_streak <= 30      THEN '8-30'
                        WHEN current_streak <= 100     THEN '31-100'
                        ELSE '100+'
                    END AS streak_bucket,
                    COUNT(*) AS user_count
                FROM streaks
                GROUP BY 1
            """)
            streak_rows = cur.fetchall()

        for bucket, count in streak_rows:
            duck.execute("""
                INSERT OR REPLACE INTO streak_distribution (date, streak_bucket, user_count)
                VALUES (?, ?, ?)
            """, [today, bucket, count])

        print(f"[analytics] Streak distribution: {dict(streak_rows)}")

        # ── 3. Puzzle Completion Rates ────────────────────────────────────────
        with pg.cursor() as cur:
            cur.execute("""
                SELECT
                    difficulty,
                    COUNT(*)                                   AS started_count,
                    COUNT(*) FILTER (WHERE status = 'completed') AS completed_count,
                    AVG(time_elapsed_ms) FILTER (
                        WHERE status = 'completed'
                    )                                          AS avg_time_ms
                FROM game_sessions
                WHERE started_at::date = CURRENT_DATE
                GROUP BY difficulty
            """)
            completion_rows = cur.fetchall()

        for diff, started, completed, avg_ms in completion_rows:
            duck.execute("""
                INSERT OR REPLACE INTO puzzle_completion_rates
                    (date, difficulty, started_count, completed_count, avg_time_ms)
                VALUES (?, ?, ?, ?, ?)
            """, [today, diff, started or 0, completed or 0, avg_ms or 0.0])

        # ── 4. Difficulty Popularity ──────────────────────────────────────────
        with pg.cursor() as cur:
            cur.execute("""
                SELECT difficulty, COUNT(*) AS play_count
                FROM game_sessions
                WHERE started_at::date = CURRENT_DATE
                GROUP BY difficulty
                ORDER BY play_count DESC
            """)
            pop_rows = cur.fetchall()

        for diff, count in pop_rows:
            duck.execute("""
                INSERT OR REPLACE INTO difficulty_popularity (date, difficulty, play_count)
                VALUES (?, ?, ?)
            """, [today, diff, count])

        print(f"[analytics] Difficulty popularity: {dict(pop_rows)}")
        duck.commit()
        print(f"[analytics_aggregator] Metrics written to DuckDB at {duckdb_path}")

    finally:
        pg.close()
        duck.close()


# ─── DAG Definition ───────────────────────────────────────────────────────────

with DAG(
    dag_id="analytics_aggregator",
    default_args=DEFAULT_ARGS,
    description="Hourly game analytics aggregation → DuckDB",
    schedule_interval="0 * * * *",
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=["analytics", "duckdb"],
) as dag:

    PythonOperator(
        task_id="aggregate_metrics",
        python_callable=aggregate_metrics,
    )
