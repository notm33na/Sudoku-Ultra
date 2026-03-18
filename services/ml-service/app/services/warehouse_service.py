"""
warehouse_service.py — Read-only queries against the DuckDB star-schema warehouse.

Provides paginated, cached queries for the hardened analytics API.
All queries run in read-only mode; the ETL DAG is the sole writer.

Caching: a simple in-process TTL cache (5 minutes) avoids hammering
DuckDB on every request. Cache is keyed by (query_name, params).
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Any

logger = logging.getLogger("warehouse_service")

WAREHOUSE_PATH = os.getenv("DUCKDB_WAREHOUSE_PATH", "data/warehouse.duckdb")
CACHE_TTL_S    = int(os.getenv("ANALYTICS_CACHE_TTL_S", "300"))  # 5 minutes
PAGE_SIZE_MAX  = 100
PAGE_SIZE_DEFAULT = 30

# ── Simple TTL cache ─────────────────────────────────────────────────────────

_cache: dict[str, tuple[float, Any]] = {}


def _cache_get(key: str) -> Any | None:
    entry = _cache.get(key)
    if entry and (time.monotonic() - entry[0]) < CACHE_TTL_S:
        return entry[1]
    return None


def _cache_set(key: str, value: Any) -> None:
    _cache[key] = (time.monotonic(), value)


def _key(*parts) -> str:
    return hashlib.md5(json.dumps(parts, default=str).encode()).hexdigest()


# ── Connection ───────────────────────────────────────────────────────────────

def _connect():
    import duckdb

    path = Path(WAREHOUSE_PATH)
    if not path.exists():
        raise FileNotFoundError(
            f"Warehouse not found at {path}. Run warehouse_etl DAG or backfill_warehouse.py."
        )
    return duckdb.connect(str(path), read_only=True)


# ── Queries ──────────────────────────────────────────────────────────────────

def get_warehouse_summary() -> dict[str, Any]:
    """
    One-page warehouse summary: row counts, date ranges, top difficulty.
    Cached for CACHE_TTL_S seconds.
    """
    cache_key = _key("warehouse_summary")
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    try:
        conn = _connect()
    except FileNotFoundError as exc:
        return {"available": False, "message": str(exc)}

    try:
        result: dict[str, Any] = {"available": True}

        # Table row counts
        counts = {}
        for table in ("dim_user", "dim_puzzle", "fact_game_session", "fact_match"):
            try:
                n = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                counts[table] = n
            except Exception:
                counts[table] = None
        result["row_counts"] = counts

        # Date range of fact_game_session
        try:
            row = conn.execute(
                "SELECT MIN(date_key), MAX(date_key) FROM fact_game_session"
            ).fetchone()
            result["session_date_range"] = {
                "min_date_key": row[0],
                "max_date_key": row[1],
            }
        except Exception:
            result["session_date_range"] = None

        # Top difficulty last 30 days
        try:
            cutoff = int((date.today() - timedelta(days=30)).strftime("%Y%m%d"))
            rows = conn.execute("""
                SELECT difficulty_key, COUNT(*) AS sessions
                FROM fact_game_session
                WHERE date_key >= ?
                GROUP BY difficulty_key
                ORDER BY sessions DESC
                LIMIT 3
            """, [cutoff]).fetchall()
            result["top_difficulties_30d"] = [
                {"difficulty": r[0], "sessions": r[1]} for r in rows
            ]
        except Exception:
            result["top_difficulties_30d"] = []

        # Completion rate last 7 days
        try:
            cutoff7 = int((date.today() - timedelta(days=7)).strftime("%Y%m%d"))
            row = conn.execute("""
                SELECT
                    COUNT(*) AS total,
                    COUNT(*) FILTER (WHERE status = 'completed') AS completed
                FROM fact_game_session
                WHERE date_key >= ?
            """, [cutoff7]).fetchone()
            total = row[0] or 0
            result["completion_rate_7d"] = round(row[1] / total, 4) if total > 0 else None
        except Exception:
            result["completion_rate_7d"] = None

    finally:
        conn.close()

    _cache_set(cache_key, result)
    return result


def get_daily_sessions(
    days: int = 30,
    difficulty: str | None = None,
    page: int = 1,
    page_size: int = PAGE_SIZE_DEFAULT,
) -> dict[str, Any]:
    """
    Paginated daily session counts (from warehouse fact table).
    """
    page_size = min(page_size, PAGE_SIZE_MAX)
    offset = (page - 1) * page_size
    cache_key = _key("daily_sessions", days, difficulty, page, page_size)
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    try:
        conn = _connect()
    except FileNotFoundError as exc:
        return {"error": str(exc), "items": [], "total": 0, "page": page, "page_size": page_size}

    try:
        cutoff = int((date.today() - timedelta(days=days)).strftime("%Y%m%d"))

        diff_filter = "AND difficulty_key = ?" if difficulty else ""
        params_count = [cutoff] + ([difficulty] if difficulty else [])
        params_data  = [cutoff] + ([difficulty] if difficulty else []) + [page_size, offset]

        total_row = conn.execute(
            f"SELECT COUNT(DISTINCT date_key) FROM fact_game_session "
            f"WHERE date_key >= ? {diff_filter}",
            params_count,
        ).fetchone()
        total = total_row[0] if total_row else 0

        rows = conn.execute(
            f"""
            SELECT date_key,
                   COUNT(*) AS total_sessions,
                   COUNT(*) FILTER (WHERE status = 'completed') AS completed,
                   COUNT(DISTINCT user_hash) AS unique_users,
                   AVG(time_elapsed_ms) AS avg_time_ms
            FROM fact_game_session
            WHERE date_key >= ? {diff_filter}
            GROUP BY date_key
            ORDER BY date_key DESC
            LIMIT ? OFFSET ?
            """,
            params_data,
        ).fetchall()

        items = [
            {
                "date_key": r[0],
                "total_sessions": r[1],
                "completed": r[2],
                "unique_users": r[3],
                "avg_time_ms": round(r[4] or 0, 1),
                "completion_rate": round(r[2] / r[1], 4) if r[1] > 0 else 0.0,
            }
            for r in rows
        ]

        result = {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "pages": (total + page_size - 1) // page_size if page_size > 0 else 0,
        }
    finally:
        conn.close()

    _cache_set(cache_key, result)
    return result


def get_user_skill_segments() -> dict[str, Any]:
    """Distribution of users across skill segments (from dim_user)."""
    cache_key = _key("skill_segments")
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    try:
        conn = _connect()
    except FileNotFoundError as exc:
        return {"error": str(exc)}

    try:
        rows = conn.execute("""
            SELECT skill_segment, COUNT(*) AS user_count
            FROM dim_user
            WHERE is_active = true
            GROUP BY skill_segment
            ORDER BY skill_segment NULLS LAST
        """).fetchall()
        result = {
            "segments": [
                {"segment": r[0], "user_count": r[1]} for r in rows
            ]
        }
    finally:
        conn.close()

    _cache_set(cache_key, result)
    return result


def invalidate_cache() -> None:
    """Clear the in-process query cache (call after ETL run)."""
    _cache.clear()
    logger.debug("Warehouse query cache cleared.")
