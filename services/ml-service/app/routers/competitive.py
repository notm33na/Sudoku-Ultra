"""
competitive.py — Competitive analytics router.

Exposes read-only competitive analytics computed by the competitive_analytics
Airflow DAG. Data is sourced from competitive.duckdb.

Routes:
  GET /api/v1/competitive/summary
  GET /api/v1/competitive/leaderboard
  GET /api/v1/competitive/elo-trend/{user_id}
  GET /api/v1/competitive/match-stats
  GET /api/v1/competitive/anomaly-report
"""

from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.services.competitive_duckdb_service import (
    get_anomaly_report,
    get_competitive_summary,
    get_elo_trend,
    get_leaderboard_snapshot,
    get_match_stats,
)

router = APIRouter(prefix="/api/v1/competitive", tags=["competitive"])


@router.get("/summary")
async def competitive_summary() -> dict[str, Any]:
    """One-page competitive analytics snapshot (leaderboard, match stats, anomalies)."""
    return get_competitive_summary()


@router.get("/leaderboard")
async def leaderboard_snapshot(
    snapshot_date: date = Query(default=None, description="Date to query; defaults to latest"),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[dict[str, Any]]:
    """Daily leaderboard snapshot from DuckDB (set by Airflow DAG)."""
    try:
        return get_leaderboard_snapshot(snapshot_date=snapshot_date, limit=limit)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@router.get("/elo-trend/{user_id}")
async def elo_trend(
    user_id: str,
    days: int = Query(default=30, ge=1, le=365),
) -> list[dict[str, Any]]:
    """Per-day Elo history for a player over the last N days."""
    try:
        return get_elo_trend(user_id=user_id, days=days)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@router.get("/match-stats")
async def match_stats(
    days: int = Query(default=7, ge=1, le=90),
) -> list[dict[str, Any]]:
    """Daily aggregate match metrics (total matches, avg Elo delta, difficulty breakdown)."""
    try:
        return get_match_stats(days=days)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@router.get("/anomaly-report")
async def anomaly_report(
    days: int = Query(default=7, ge=1, le=90),
) -> list[dict[str, Any]]:
    """Daily anomaly flag summary (flagged sessions, flag rate, avg score)."""
    try:
        return get_anomaly_report(days=days)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
