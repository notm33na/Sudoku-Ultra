"""
competitive_duckdb_service.py — Competitive analytics DuckDB queries.

Reads aggregation tables written by the competitive_analytics Airflow DAG.
The ml-service opens the DB in read-only mode; the DAG owns write access.

Tables (written by Airflow DAG):
  elo_trends              — per-user Elo change summarised by day
  leaderboard_snapshots   — daily top-N player snapshots
  match_stats_daily       — aggregate match metrics by day
  anomaly_reports_daily   — daily anomaly flag summary
"""

from __future__ import annotations

import os
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import duckdb

from app.logging import setup_logging

logger = setup_logging()

COMPETITIVE_DUCKDB_PATH = os.getenv(
    "COMPETITIVE_DUCKDB_PATH", "data/competitive.duckdb"
)


def _connect() -> duckdb.DuckDBPyConnection:
    """Open a read-only connection to competitive.duckdb."""
    path = Path(COMPETITIVE_DUCKDB_PATH)
    if not path.exists():
        raise FileNotFoundError(
            f"Competitive analytics DB not found at {path}. "
            "Run the competitive_analytics Airflow DAG at least once first."
        )
    return duckdb.connect(str(path), read_only=True)


# ─── Elo Trends ───────────────────────────────────────────────────────────────


def get_elo_trend(user_id: str, days: int = 30) -> list[dict[str, Any]]:
    """Return per-day Elo summary for a single player over the last N days."""
    since = date.today() - timedelta(days=days)
    conn = _connect()
    try:
        rows = conn.execute(
            """
            SELECT date, matches_played, wins, losses,
                   elo_start, elo_end, elo_delta
            FROM elo_trends
            WHERE user_id = ? AND date >= ?
            ORDER BY date ASC
            """,
            [user_id, since],
        ).fetchall()
        return [
            {
                "date": str(r[0]),
                "matches_played": r[1],
                "wins": r[2],
                "losses": r[3],
                "elo_start": r[4],
                "elo_end": r[5],
                "elo_delta": r[6],
            }
            for r in rows
        ]
    finally:
        conn.close()


# ─── Leaderboard Snapshot ─────────────────────────────────────────────────────


def get_leaderboard_snapshot(
    snapshot_date: date | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Return the leaderboard snapshot for a given date (defaults to latest)."""
    conn = _connect()
    try:
        if snapshot_date is None:
            row = conn.execute(
                "SELECT MAX(snapshot_date) FROM leaderboard_snapshots"
            ).fetchone()
            snapshot_date = row[0] if row and row[0] else date.today()

        rows = conn.execute(
            """
            SELECT rank, user_id, elo_rating, wins, losses
            FROM leaderboard_snapshots
            WHERE snapshot_date = ?
            ORDER BY rank ASC
            LIMIT ?
            """,
            [snapshot_date, limit],
        ).fetchall()
        return [
            {
                "snapshot_date": str(snapshot_date),
                "rank": r[0],
                "user_id": r[1],
                "elo_rating": r[2],
                "wins": r[3],
                "losses": r[4],
                "win_rate": round(r[3] / (r[3] + r[4]), 4) if (r[3] + r[4]) > 0 else 0.0,
            }
            for r in rows
        ]
    finally:
        conn.close()


# ─── Match Stats ──────────────────────────────────────────────────────────────


def get_match_stats(days: int = 7) -> list[dict[str, Any]]:
    """Return daily aggregate match metrics for the last N days."""
    since = date.today() - timedelta(days=days)
    conn = _connect()
    try:
        rows = conn.execute(
            """
            SELECT date, total_matches, avg_duration_ms,
                   avg_elo_delta, difficulty_breakdown, end_reason_breakdown
            FROM match_stats_daily
            WHERE date >= ?
            ORDER BY date DESC
            """,
            [since],
        ).fetchall()
        return [
            {
                "date": str(r[0]),
                "total_matches": r[1],
                "avg_duration_ms": round(r[2] or 0, 2),
                "avg_elo_delta": round(r[3] or 0, 2),
                "difficulty_breakdown": r[4],
                "end_reason_breakdown": r[5],
            }
            for r in rows
        ]
    finally:
        conn.close()


# ─── Anomaly Report ───────────────────────────────────────────────────────────


def get_anomaly_report(days: int = 7) -> list[dict[str, Any]]:
    """Return daily anomaly flag summary for the last N days."""
    since = date.today() - timedelta(days=days)
    conn = _connect()
    try:
        rows = conn.execute(
            """
            SELECT date, total_sessions, flagged_count,
                   flag_rate, avg_anomaly_score
            FROM anomaly_reports_daily
            WHERE date >= ?
            ORDER BY date DESC
            """,
            [since],
        ).fetchall()
        return [
            {
                "date": str(r[0]),
                "total_sessions": r[1],
                "flagged_count": r[2],
                "flag_rate": round(r[3] or 0, 6),
                "avg_anomaly_score": round(r[4] or 0, 6),
            }
            for r in rows
        ]
    finally:
        conn.close()


# ─── Summary ──────────────────────────────────────────────────────────────────


def get_competitive_summary() -> dict[str, Any]:
    """Return a one-page competitive analytics snapshot."""
    try:
        top10 = get_leaderboard_snapshot(limit=10)
        match_stats = get_match_stats(days=7)
        anomaly = get_anomaly_report(days=7)
        available = True
    except FileNotFoundError:
        return {
            "available": False,
            "message": "Competitive analytics DB not yet populated. "
                       "Run the competitive_analytics Airflow DAG.",
        }
    except Exception as exc:
        logger.error("Competitive summary query failed: %s", exc)
        return {"available": False, "message": str(exc)}

    recent_matches = sum(s["total_matches"] for s in match_stats)
    recent_flagged = sum(a["flagged_count"] for a in anomaly)

    return {
        "available": True,
        "date": str(date.today()),
        "top10": top10,
        "recent_matches_7d": recent_matches,
        "recent_anomalies_7d": recent_flagged,
        "match_stats_7d": match_stats,
        "anomaly_report_7d": anomaly,
    }
