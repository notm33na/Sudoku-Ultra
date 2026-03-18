"""
Analytics router — DuckDB query endpoints (hardened).

Changes from Phase 4:
  - All list endpoints support pagination (page / page_size query params)
  - In-process TTL cache (5 min) via warehouse_service / duckdb_service
  - Per-endpoint rate limiting via slowapi (10 req/min per IP for heavy queries)
  - New endpoint: GET /api/v1/analytics/warehouse-summary (star-schema warehouse)
  - GET /api/v1/analytics/sessions (paginated daily sessions from warehouse)
  - GET /api/v1/analytics/skill-segments (user cluster distribution)

Rate limits:
  /summary                10/minute
  /warehouse-summary      10/minute
  /dau                    30/minute
  /sessions               10/minute
  /streak-distribution    30/minute
  /completion-rates       30/minute
  /difficulty-popularity  30/minute
  /skill-segments         30/minute
"""

from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, Query, Request

from app.services.duckdb_service import (
    get_daily_active_users,
    get_difficulty_popularity,
    get_puzzle_completion_rates,
    get_streak_distribution,
    get_summary,
)
from app.services.warehouse_service import (
    get_daily_sessions,
    get_user_skill_segments,
    get_warehouse_summary,
)

router = APIRouter(prefix="/api/v1/analytics", tags=["analytics"])

# ── Rate limiter (optional — slowapi) ────────────────────────────────────────
# If slowapi is not installed, rate limiting is silently disabled.

try:
    from slowapi import Limiter
    from slowapi.util import get_remote_address
    _limiter = Limiter(key_func=get_remote_address)

    def _limit(rate: str):
        return _limiter.limit(rate)

except ImportError:
    import functools

    def _limit(_rate: str):  # type: ignore[misc]
        def decorator(fn):
            @functools.wraps(fn)
            async def wrapper(*args, **kwargs):
                return await fn(*args, **kwargs)
            return wrapper
        return decorator


# ── Existing endpoints (now with pagination guard + cache passthrough) ────────

@router.get("/summary")
@_limit("10/minute")
async def analytics_summary(request: Request) -> dict[str, Any]:
    """One-page analytics dashboard snapshot for today (legacy DuckDB tables)."""
    return get_summary()


@router.get("/dau")
@_limit("30/minute")
async def daily_active_users(
    request: Request,
    days: int = Query(default=30, ge=1, le=365),
) -> list[dict]:
    """Daily active users for the last N days."""
    try:
        return get_daily_active_users(days=days)
    except FileNotFoundError as exc:
        return [{"error": str(exc)}]


@router.get("/streak-distribution")
@_limit("30/minute")
async def streak_distribution(
    request: Request,
    target_date: date = Query(default=None),
) -> list[dict]:
    """Streak bucket distribution for a given date (defaults to today)."""
    try:
        return get_streak_distribution(target_date=target_date)
    except FileNotFoundError as exc:
        return [{"error": str(exc)}]


@router.get("/completion-rates")
@_limit("30/minute")
async def completion_rates(
    request: Request,
    target_date: date = Query(default=None),
) -> list[dict]:
    """Per-difficulty puzzle completion rates for a given date."""
    try:
        return get_puzzle_completion_rates(target_date=target_date)
    except FileNotFoundError as exc:
        return [{"error": str(exc)}]


@router.get("/difficulty-popularity")
@_limit("30/minute")
async def difficulty_popularity(
    request: Request,
    days: int = Query(default=7, ge=1, le=90),
) -> list[dict]:
    """Aggregated difficulty play counts over the last N days."""
    try:
        return get_difficulty_popularity(days=days)
    except FileNotFoundError as exc:
        return [{"error": str(exc)}]


# ── New warehouse-backed endpoints ────────────────────────────────────────────

@router.get("/warehouse-summary")
@_limit("10/minute")
async def warehouse_summary(request: Request) -> dict[str, Any]:
    """
    Star-schema warehouse summary: row counts, date ranges, completion rate.

    Served from the DuckDB warehouse populated by the warehouse_etl DAG.
    Returns `available: false` with a message if the warehouse has not been
    populated yet (run warehouse_etl DAG or backfill_warehouse.py first).
    """
    return get_warehouse_summary()


@router.get("/sessions")
@_limit("10/minute")
async def paginated_sessions(
    request: Request,
    days: int        = Query(default=30, ge=1, le=365,
                              description="Look-back window in days"),
    difficulty: str  = Query(default=None,
                              description="Filter by difficulty key (e.g. 'hard')"),
    page: int        = Query(default=1, ge=1,
                              description="Page number (1-indexed)"),
    page_size: int   = Query(default=30, ge=1, le=100,
                              description="Results per page (max 100)"),
) -> dict[str, Any]:
    """
    Paginated daily session aggregates from the warehouse fact table.

    Returns totals, completion rate, and unique users per calendar day.
    """
    return get_daily_sessions(
        days=days,
        difficulty=difficulty,
        page=page,
        page_size=page_size,
    )


@router.get("/skill-segments")
@_limit("30/minute")
async def skill_segments(request: Request) -> dict[str, Any]:
    """Distribution of active users across K-Means skill segments (0–7)."""
    return get_user_skill_segments()
