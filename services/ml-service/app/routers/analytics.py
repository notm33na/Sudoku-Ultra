"""
Analytics router — DuckDB query endpoints.

Exposes read-only analytics computed by the analytics_aggregator
Airflow DAG. All data is sourced from the DuckDB analytics file.
"""

from datetime import date
from typing import Any

from fastapi import APIRouter, Query

from app.services.duckdb_service import (
    get_daily_active_users,
    get_difficulty_popularity,
    get_puzzle_completion_rates,
    get_streak_distribution,
    get_summary,
)

router = APIRouter(prefix="/api/v1/analytics", tags=["analytics"])


@router.get("/summary")
async def analytics_summary() -> dict[str, Any]:
    """One-page analytics dashboard snapshot for today."""
    return get_summary()


@router.get("/dau")
async def daily_active_users(days: int = Query(default=30, ge=1, le=365)) -> list[dict]:
    """Daily active users for the last N days."""
    try:
        return get_daily_active_users(days=days)
    except FileNotFoundError as exc:
        return [{"error": str(exc)}]


@router.get("/streak-distribution")
async def streak_distribution(
    target_date: date = Query(default=None),
) -> list[dict]:
    """Streak bucket distribution for a given date (defaults to today)."""
    try:
        return get_streak_distribution(target_date=target_date)
    except FileNotFoundError as exc:
        return [{"error": str(exc)}]


@router.get("/completion-rates")
async def completion_rates(
    target_date: date = Query(default=None),
) -> list[dict]:
    """Per-difficulty puzzle completion rates for a given date."""
    try:
        return get_puzzle_completion_rates(target_date=target_date)
    except FileNotFoundError as exc:
        return [{"error": str(exc)}]


@router.get("/difficulty-popularity")
async def difficulty_popularity(days: int = Query(default=7, ge=1, le=90)) -> list[dict]:
    """Aggregated difficulty play counts over the last N days."""
    try:
        return get_difficulty_popularity(days=days)
    except FileNotFoundError as exc:
        return [{"error": str(exc)}]
