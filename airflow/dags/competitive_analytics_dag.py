"""
competitive_analytics_dag.py — Airflow DAG for competitive analytics.

Runs daily at 01:00 UTC. Reads JSONL event files produced by the Kafka
consumer (app.ml.kafka_consumer) and writes aggregated analytics into
competitive.duckdb for serving by the ml-service /api/v1/competitive/* endpoints.

Tasks:
  1. ensure_schema          — Create DuckDB tables if they don't exist.
  2. load_match_events      — Load yesterday's JSONL match events into a staging table.
  3. load_session_events    — Load yesterday's JSONL session events (with anomaly scores).
  4. compute_elo_trends     — Aggregate per-user Elo changes by day → elo_trends.
  5. snapshot_leaderboard   — Write daily top-N snapshot → leaderboard_snapshots.
  6. compute_match_stats    — Aggregate match metrics by day → match_stats_daily.
  7. compute_anomaly_report — Aggregate anomaly flags by day → anomaly_reports_daily.
  8. cleanup_staging        — Drop yesterday's staging tables.

Environment variables (Airflow Variables / env):
  COMPETITIVE_DUCKDB_PATH   path to competitive.duckdb  (default: /data/competitive.duckdb)
  EVENTS_DIR                path to JSONL event dir      (default: /data/events)
  LEADERBOARD_SNAPSHOT_SIZE top-N to snapshot           (default: 100)
"""

from __future__ import annotations

import json
import logging
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("competitive_analytics")

# ── Config ────────────────────────────────────────────────────────────────────

DUCKDB_PATH = os.getenv("COMPETITIVE_DUCKDB_PATH", "/data/competitive.duckdb")
EVENTS_DIR = Path(os.getenv("EVENTS_DIR", "/data/events"))
SNAPSHOT_SIZE = int(os.getenv("LEADERBOARD_SNAPSHOT_SIZE", "100"))

# ── Airflow DAG definition ────────────────────────────────────────────────────

from airflow import DAG  # noqa: E402
from airflow.operators.python import PythonOperator  # noqa: E402

default_args = {
    "owner": "ml-team",
    "depends_on_past": False,
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
    "email_on_failure": False,
}

dag = DAG(
    dag_id="competitive_analytics",
    description="Aggregate Kafka competitive events into DuckDB analytics tables",
    schedule_interval="0 1 * * *",  # 01:00 UTC daily
    start_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
    catchup=False,
    default_args=default_args,
    tags=["competitive", "analytics", "multiplayer"],
)

# ── Helpers ───────────────────────────────────────────────────────────────────


def _connect_rw():
    """Open a read-write DuckDB connection."""
    import duckdb

    path = Path(DUCKDB_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(str(path))


def _load_jsonl(subdir: str, target_date: date) -> list[dict[str, Any]]:
    """Read all events from a date-partitioned JSONL file. Returns [] if absent."""
    path = EVENTS_DIR / subdir / f"{target_date}.jsonl"
    if not path.exists():
        logger.warning("No event file found at %s", path)
        return []
    events: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    logger.warning("Skipping invalid JSON line in %s", path)
    logger.info("Loaded %d events from %s", len(events), path)
    return events


# ── Task functions ────────────────────────────────────────────────────────────


def ensure_schema(**ctx: Any) -> None:
    conn = _connect_rw()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS competitive_matches (
            match_id        VARCHAR PRIMARY KEY,
            room_id         VARCHAR NOT NULL,
            winner_id       VARCHAR NOT NULL,
            loser_id        VARCHAR NOT NULL,
            winner_elo_before INTEGER,
            winner_elo_after  INTEGER,
            loser_elo_before  INTEGER,
            loser_elo_after   INTEGER,
            elo_delta       INTEGER,
            difficulty      VARCHAR,
            end_reason      VARCHAR,
            duration_ms     INTEGER,
            completed_at    TIMESTAMP,
            consumed_at     TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS enriched_sessions (
            session_id          VARCHAR PRIMARY KEY,
            user_id             VARCHAR NOT NULL,
            puzzle_id           VARCHAR,
            difficulty          VARCHAR,
            time_elapsed_ms     INTEGER,
            score               INTEGER,
            hints_used          INTEGER,
            errors_count        INTEGER,
            completed_at        TIMESTAMP,
            anomaly_score       DOUBLE,
            reconstruction_error DOUBLE,
            is_anomalous        BOOLEAN,
            enriched_at         TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS elo_trends (
            date            DATE,
            user_id         VARCHAR,
            matches_played  INTEGER,
            wins            INTEGER,
            losses          INTEGER,
            elo_start       INTEGER,
            elo_end         INTEGER,
            elo_delta       INTEGER,
            PRIMARY KEY (date, user_id)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS leaderboard_snapshots (
            snapshot_date   DATE,
            rank            INTEGER,
            user_id         VARCHAR,
            elo_rating      INTEGER,
            wins            INTEGER,
            losses          INTEGER,
            PRIMARY KEY (snapshot_date, rank)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS match_stats_daily (
            date                    DATE PRIMARY KEY,
            total_matches           INTEGER,
            avg_duration_ms         DOUBLE,
            avg_elo_delta           DOUBLE,
            difficulty_breakdown    VARCHAR,
            end_reason_breakdown    VARCHAR
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS anomaly_reports_daily (
            date                DATE PRIMARY KEY,
            total_sessions      INTEGER,
            flagged_count       INTEGER,
            flag_rate           DOUBLE,
            avg_anomaly_score   DOUBLE
        )
    """)
    conn.close()
    logger.info("Schema ensured.")


def load_match_events(**ctx: Any) -> None:
    target_date: date = ctx["data_interval_start"].date()
    events = _load_jsonl("matches", target_date)
    if not events:
        return

    conn = _connect_rw()
    inserted = 0
    for ev in events:
        try:
            conn.execute(
                """
                INSERT OR IGNORE INTO competitive_matches
                    (match_id, room_id, winner_id, loser_id,
                     winner_elo_before, winner_elo_after,
                     loser_elo_before, loser_elo_after,
                     elo_delta, difficulty, end_reason,
                     duration_ms, completed_at, consumed_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                [
                    ev.get("match_id"),
                    ev.get("room_id"),
                    ev.get("winner_id"),
                    ev.get("loser_id"),
                    ev.get("winner_elo_before"),
                    ev.get("winner_elo_after"),
                    ev.get("loser_elo_before"),
                    ev.get("loser_elo_after"),
                    ev.get("elo_delta"),
                    ev.get("difficulty"),
                    ev.get("end_reason"),
                    ev.get("duration_ms"),
                    ev.get("completed_at"),
                    ev.get("consumed_at"),
                ],
            )
            inserted += 1
        except Exception as exc:
            logger.warning("Skipping match event %s: %s", ev.get("match_id"), exc)
    conn.close()
    logger.info("Inserted %d/%d match events.", inserted, len(events))


def load_session_events(**ctx: Any) -> None:
    target_date: date = ctx["data_interval_start"].date()
    events = _load_jsonl("sessions", target_date)
    if not events:
        return

    conn = _connect_rw()
    inserted = 0
    for ev in events:
        try:
            conn.execute(
                """
                INSERT OR IGNORE INTO enriched_sessions
                    (session_id, user_id, puzzle_id, difficulty,
                     time_elapsed_ms, score, hints_used, errors_count,
                     completed_at, anomaly_score, reconstruction_error,
                     is_anomalous, enriched_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                [
                    ev.get("session_id"),
                    ev.get("user_id"),
                    ev.get("puzzle_id"),
                    ev.get("difficulty"),
                    ev.get("time_elapsed_ms"),
                    ev.get("score"),
                    ev.get("hints_used"),
                    ev.get("errors_count"),
                    ev.get("completed_at"),
                    ev.get("anomaly_score"),
                    ev.get("reconstruction_error"),
                    ev.get("is_anomalous"),
                    ev.get("enriched_at"),
                ],
            )
            inserted += 1
        except Exception as exc:
            logger.warning("Skipping session event %s: %s", ev.get("session_id"), exc)
    conn.close()
    logger.info("Inserted %d/%d session events.", inserted, len(events))


def compute_elo_trends(**ctx: Any) -> None:
    target_date: date = ctx["data_interval_start"].date()
    conn = _connect_rw()

    # Delete existing rows for this date to allow re-run idempotency.
    conn.execute("DELETE FROM elo_trends WHERE date = ?", [target_date])

    conn.execute(
        """
        INSERT INTO elo_trends
            (date, user_id, matches_played, wins, losses,
             elo_start, elo_end, elo_delta)
        SELECT
            CAST(completed_at AS DATE)                             AS date,
            user_id,
            COUNT(*)                                               AS matches_played,
            SUM(is_win)                                            AS wins,
            SUM(1 - is_win)                                        AS losses,
            FIRST(elo_before ORDER BY completed_at ASC)           AS elo_start,
            LAST(elo_after  ORDER BY completed_at ASC)            AS elo_end,
            LAST(elo_after  ORDER BY completed_at ASC)
              - FIRST(elo_before ORDER BY completed_at ASC)       AS elo_delta
        FROM (
            SELECT completed_at,
                   winner_id   AS user_id,
                   winner_elo_before AS elo_before,
                   winner_elo_after  AS elo_after,
                   1 AS is_win
            FROM competitive_matches
            WHERE CAST(completed_at AS DATE) = ?
            UNION ALL
            SELECT completed_at,
                   loser_id    AS user_id,
                   loser_elo_before AS elo_before,
                   loser_elo_after  AS elo_after,
                   0 AS is_win
            FROM competitive_matches
            WHERE CAST(completed_at AS DATE) = ?
        ) t
        GROUP BY CAST(completed_at AS DATE), user_id
        """,
        [target_date, target_date],
    )
    conn.close()
    logger.info("Elo trends computed for %s.", target_date)


def snapshot_leaderboard(**ctx: Any) -> None:
    target_date: date = ctx["data_interval_start"].date()
    conn = _connect_rw()

    conn.execute("DELETE FROM leaderboard_snapshots WHERE snapshot_date = ?", [target_date])

    conn.execute(
        """
        INSERT INTO leaderboard_snapshots
            (snapshot_date, rank, user_id, elo_rating, wins, losses)
        SELECT
            ? AS snapshot_date,
            ROW_NUMBER() OVER (ORDER BY elo_end DESC) AS rank,
            user_id,
            elo_end  AS elo_rating,
            SUM(wins)   AS wins,
            SUM(losses) AS losses
        FROM elo_trends
        WHERE date <= ?
        GROUP BY user_id, elo_end
        ORDER BY elo_end DESC
        LIMIT ?
        """,
        [target_date, target_date, SNAPSHOT_SIZE],
    )
    conn.close()
    logger.info("Leaderboard snapshot written for %s (top %d).", target_date, SNAPSHOT_SIZE)


def compute_match_stats(**ctx: Any) -> None:
    target_date: date = ctx["data_interval_start"].date()
    conn = _connect_rw()

    conn.execute("DELETE FROM match_stats_daily WHERE date = ?", [target_date])

    row = conn.execute(
        """
        SELECT
            COUNT(*)                                        AS total_matches,
            AVG(duration_ms)                               AS avg_duration_ms,
            AVG(elo_delta)                                 AS avg_elo_delta
        FROM competitive_matches
        WHERE CAST(completed_at AS DATE) = ?
        """,
        [target_date],
    ).fetchone()

    if not row or row[0] == 0:
        conn.close()
        logger.info("No matches on %s, skipping match_stats_daily.", target_date)
        return

    # Difficulty breakdown as JSON string.
    diff_rows = conn.execute(
        """
        SELECT difficulty, COUNT(*) AS cnt
        FROM competitive_matches
        WHERE CAST(completed_at AS DATE) = ?
        GROUP BY difficulty
        """,
        [target_date],
    ).fetchall()
    difficulty_breakdown = json.dumps({r[0]: r[1] for r in diff_rows})

    reason_rows = conn.execute(
        """
        SELECT end_reason, COUNT(*) AS cnt
        FROM competitive_matches
        WHERE CAST(completed_at AS DATE) = ?
        GROUP BY end_reason
        """,
        [target_date],
    ).fetchall()
    end_reason_breakdown = json.dumps({r[0]: r[1] for r in reason_rows})

    conn.execute(
        """
        INSERT INTO match_stats_daily
            (date, total_matches, avg_duration_ms, avg_elo_delta,
             difficulty_breakdown, end_reason_breakdown)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        [
            target_date,
            row[0],
            row[1],
            row[2],
            difficulty_breakdown,
            end_reason_breakdown,
        ],
    )
    conn.close()
    logger.info(
        "Match stats for %s: %d matches, avg_delta=%.2f.",
        target_date,
        row[0],
        row[2] or 0,
    )


def compute_anomaly_report(**ctx: Any) -> None:
    target_date: date = ctx["data_interval_start"].date()
    conn = _connect_rw()

    conn.execute("DELETE FROM anomaly_reports_daily WHERE date = ?", [target_date])

    row = conn.execute(
        """
        SELECT
            COUNT(*)                                        AS total_sessions,
            SUM(CASE WHEN is_anomalous THEN 1 ELSE 0 END)  AS flagged_count,
            AVG(CASE WHEN anomaly_score IS NOT NULL
                     THEN anomaly_score ELSE 0 END)        AS avg_anomaly_score
        FROM enriched_sessions
        WHERE CAST(completed_at AS DATE) = ?
        """,
        [target_date],
    ).fetchone()

    if not row or row[0] == 0:
        conn.close()
        logger.info("No sessions on %s, skipping anomaly_reports_daily.", target_date)
        return

    total = row[0]
    flagged = row[1] or 0
    flag_rate = flagged / total if total > 0 else 0.0

    conn.execute(
        """
        INSERT INTO anomaly_reports_daily
            (date, total_sessions, flagged_count, flag_rate, avg_anomaly_score)
        VALUES (?, ?, ?, ?, ?)
        """,
        [target_date, total, flagged, flag_rate, row[2] or 0.0],
    )
    conn.close()
    logger.info(
        "Anomaly report for %s: %d sessions, %d flagged (%.2f%%).",
        target_date,
        total,
        flagged,
        flag_rate * 100,
    )


# ── Task graph ────────────────────────────────────────────────────────────────

t_schema = PythonOperator(
    task_id="ensure_schema",
    python_callable=ensure_schema,
    dag=dag,
)

t_load_matches = PythonOperator(
    task_id="load_match_events",
    python_callable=load_match_events,
    dag=dag,
)

t_load_sessions = PythonOperator(
    task_id="load_session_events",
    python_callable=load_session_events,
    dag=dag,
)

t_elo_trends = PythonOperator(
    task_id="compute_elo_trends",
    python_callable=compute_elo_trends,
    dag=dag,
)

t_snapshot = PythonOperator(
    task_id="snapshot_leaderboard",
    python_callable=snapshot_leaderboard,
    dag=dag,
)

t_match_stats = PythonOperator(
    task_id="compute_match_stats",
    python_callable=compute_match_stats,
    dag=dag,
)

t_anomaly = PythonOperator(
    task_id="compute_anomaly_report",
    python_callable=compute_anomaly_report,
    dag=dag,
)

# Schema first, then parallel loads, then aggregations.
t_schema >> [t_load_matches, t_load_sessions]
t_load_matches >> [t_elo_trends, t_match_stats]
t_load_sessions >> t_anomaly
t_elo_trends >> t_snapshot
