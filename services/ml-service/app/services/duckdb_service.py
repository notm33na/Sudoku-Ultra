"""
DuckDB analytics service.

Provides read access to the DuckDB analytics store populated by the
analytics_aggregator Airflow DAG. The ml-service opens the DB in
read-only mode to avoid conflicts with the Airflow writer.

Tables:
  daily_active_users       — DAU by date
  streak_distribution      — streak bucket counts by date
  puzzle_completion_rates  — per-difficulty completion stats by date
  difficulty_popularity    — play counts per difficulty by date
"""

import os
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import duckdb

from app.logging import setup_logging

logger = setup_logging()

DUCKDB_PATH = os.getenv("DUCKDB_PATH", "data/analytics.duckdb")


def _connect() -> duckdb.DuckDBPyConnection:
    """Open a read-only connection to the analytics DuckDB file."""
    path = Path(DUCKDB_PATH)
    if not path.exists():
        raise FileNotFoundError(
            f"DuckDB analytics file not found at {path}. "
            "Run the analytics_aggregator DAG at least once first."
        )
    return duckdb.connect(str(path), read_only=True)


# ─── Queries ──────────────────────────────────────────────────────────────────


def get_daily_active_users(days: int = 30) -> list[dict[str, Any]]:
    """Return DAU for the last N days."""
    since = date.today() - timedelta(days=days)
    conn = _connect()
    try:
        rows = conn.execute(
            """SELECT date, user_count, new_user_count, updated_at
               FROM daily_active_users
               WHERE date >= ?
               ORDER BY date DESC""",
            [since],
        ).fetchall()
        return [
            {
                "date": str(r[0]),
                "user_count": r[1],
                "new_user_count": r[2],
                "updated_at": str(r[3]),
            }
            for r in rows
        ]
    finally:
        conn.close()


def get_streak_distribution(target_date: date | None = None) -> list[dict[str, Any]]:
    """Return streak bucket distribution for a given date (defaults to today)."""
    target_date = target_date or date.today()
    conn = _connect()
    try:
        rows = conn.execute(
            """SELECT streak_bucket, user_count
               FROM streak_distribution
               WHERE date = ?
               ORDER BY streak_bucket""",
            [target_date],
        ).fetchall()
        return [{"streak_bucket": r[0], "user_count": r[1]} for r in rows]
    finally:
        conn.close()


def get_puzzle_completion_rates(
    target_date: date | None = None,
) -> list[dict[str, Any]]:
    """Return completion rates per difficulty for a given date."""
    target_date = target_date or date.today()
    conn = _connect()
    try:
        rows = conn.execute(
            """SELECT difficulty, started_count, completed_count, avg_time_ms
               FROM puzzle_completion_rates
               WHERE date = ?
               ORDER BY difficulty""",
            [target_date],
        ).fetchall()
        return [
            {
                "difficulty": r[0],
                "started_count": r[1],
                "completed_count": r[2],
                "avg_time_ms": round(r[3] or 0, 2),
                "completion_rate": round(r[2] / r[1], 4) if r[1] > 0 else 0.0,
            }
            for r in rows
        ]
    finally:
        conn.close()


def get_difficulty_popularity(days: int = 7) -> list[dict[str, Any]]:
    """Return aggregated difficulty play counts over the last N days."""
    since = date.today() - timedelta(days=days)
    conn = _connect()
    try:
        rows = conn.execute(
            """SELECT difficulty, SUM(play_count) AS total_plays
               FROM difficulty_popularity
               WHERE date >= ?
               GROUP BY difficulty
               ORDER BY total_plays DESC""",
            [since],
        ).fetchall()
        return [{"difficulty": r[0], "total_plays": int(r[1])} for r in rows]
    finally:
        conn.close()


def get_summary() -> dict[str, Any]:
    """Return a one-page analytics summary for the dashboard."""
    today = date.today()
    try:
        dau = get_daily_active_users(days=1)
        streak_dist = get_streak_distribution(today)
        completion = get_puzzle_completion_rates(today)
        popularity = get_difficulty_popularity(days=7)
        available = True
    except FileNotFoundError:
        return {
            "available": False,
            "message": "Analytics store not yet populated. Run analytics_aggregator DAG.",
        }
    except Exception as exc:
        logger.error(f"DuckDB summary query failed: {exc}")
        return {"available": False, "message": str(exc)}

    return {
        "available": True,
        "date": str(today),
        "daily_active_users": dau[0] if dau else None,
        "streak_distribution": streak_dist,
        "completion_rates": completion,
        "difficulty_popularity": popularity,
    }
