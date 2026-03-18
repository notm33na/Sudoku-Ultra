"""
backfill_features.py — Compute and store feature vectors for all users.

Reads raw game telemetry from PostgreSQL, computes three feature groups
(churn, skill, anomaly), and writes versioned snapshots to the feature store
with full data lineage records.

Usage
-----
  # Backfill all users (idempotent — existing features get a new version)
  python ml/scripts/backfill_features.py

  # Only users who played since a given date
  python ml/scripts/backfill_features.py --since 2026-01-01

  # Specific user
  python ml/scripts/backfill_features.py --user-id <uuid>

  # Dry-run: compute but do not write
  python ml/scripts/backfill_features.py --dry-run

  # Override database URL
  python ml/scripts/backfill_features.py --db-url postgresql://...

Environment variables
---------------------
  DATABASE_URL  — PostgreSQL connection string (default: dev localhost)
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
log = logging.getLogger("backfill_features")

# Allow running from repo root without installing the package
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "services" / "ml-service"))

DEFAULT_DB_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://sudoku:sudoku_dev_password@localhost:5432/sudoku_ultra",
)
PIPELINE_NAME = "backfill_features"

# ── SQL for each feature group ────────────────────────────────────────────────

# Churn features — same as churn_risk_scorer DAG (10 engagement signals)
CHURN_SQL = """
SELECT
    u.id                                                           AS user_id,
    COALESCE(
        EXTRACT(EPOCH FROM (NOW() - s.last_played_date)) / 86400, 999
    )::float                                                       AS days_since_last_play,
    COALESCE(
        COUNT(gs.id) FILTER (WHERE gs.started_at >= NOW() - INTERVAL '30 days')
        / 4.3, 0
    )::float                                                       AS session_frequency,
    COALESCE(AVG(gs.time_elapsed_ms) / 60000.0, 20)::float        AS avg_session_duration,
    COUNT(gs.id)::float                                            AS total_games_played,
    COALESCE(
        COUNT(gs.id) FILTER (
            WHERE gs.status = 'completed'
              AND gs.started_at >= NOW() - INTERVAL '14 days'
        )::float
        / NULLIF(COUNT(gs.id) FILTER (
            WHERE gs.started_at >= NOW() - INTERVAL '14 days'
        ), 0)
        -
        COUNT(gs.id) FILTER (
            WHERE gs.status = 'completed'
              AND gs.started_at BETWEEN NOW() - INTERVAL '28 days'
                                    AND NOW() - INTERVAL '14 days'
        )::float
        / NULLIF(COUNT(gs.id) FILTER (
            WHERE gs.started_at BETWEEN NOW() - INTERVAL '28 days'
                                    AND NOW() - INTERVAL '14 days'
        ), 0),
        0
    )::float                                                       AS win_rate_trend,
    0.0::float                                                     AS hint_usage_trend,
    COUNT(DISTINCT gs.difficulty)::float                           AS difficulty_variety,
    COALESCE(
        COUNT(gs.id) FILTER (WHERE gs.status = 'completed')::float
        / NULLIF(COUNT(gs.id), 0),
        0.7
    )::float                                                       AS completion_rate,
    0.0::float                                                     AS error_rate_trend,
    COALESCE(s.longest_streak, 0)::float                          AS longest_streak
FROM users u
LEFT JOIN streaks s ON s.user_id = u.id
LEFT JOIN game_sessions gs ON gs.user_id = u.id
{where_clause}
GROUP BY u.id, s.last_played_date, s.longest_streak
"""

# Skill features — 8 solve-behaviour signals for clustering
SKILL_SQL = """
SELECT
    u.id                                                           AS user_id,
    COALESCE(
        AVG(gs.time_elapsed_ms / 1000.0)
        FILTER (WHERE gs.difficulty IN ('super_easy','easy') AND gs.status='completed'),
        120
    )::float                                                       AS avg_solve_time_easy,
    COALESCE(
        AVG(gs.time_elapsed_ms / 1000.0)
        FILTER (WHERE gs.difficulty = 'medium' AND gs.status='completed'),
        300
    )::float                                                       AS avg_solve_time_medium,
    COALESCE(
        AVG(gs.time_elapsed_ms / 1000.0)
        FILTER (WHERE gs.difficulty IN ('hard','super_hard') AND gs.status='completed'),
        600
    )::float                                                       AS avg_solve_time_hard,
    COALESCE(
        COUNT(gs.id) FILTER (WHERE gs.hints_used > 0 AND gs.status='completed')::float
        / NULLIF(COUNT(gs.id) FILTER (WHERE gs.status='completed'), 0),
        0.2
    )::float                                                       AS hint_rate,
    COALESCE(
        AVG(gs.errors_count)::float, 0
    )                                                              AS error_rate,
    COALESCE(
        COUNT(gs.id) FILTER (WHERE gs.status='completed')::float
        / NULLIF(COUNT(gs.id), 0),
        0.7
    )::float                                                       AS completion_rate,
    COUNT(DISTINCT gs.difficulty)::float                           AS difficulty_spread,
    COUNT(gs.id) FILTER (
        WHERE gs.started_at >= NOW() - INTERVAL '30 days'
    )::float                                                       AS games_last_30d
FROM users u
LEFT JOIN game_sessions gs ON gs.user_id = u.id
{where_clause}
GROUP BY u.id
"""

# Anomaly features — 10 session-behaviour signals for autoencoder
ANOMALY_SQL = """
SELECT
    u.id                                                           AS user_id,
    COALESCE(
        AVG(gs.time_elapsed_ms / 1000.0)
        / NULLIF(MAX(gs.time_elapsed_ms / 1000.0), 0), 0.5
    )::float                                                       AS time_mean_norm,
    COALESCE(
        STDDEV(gs.time_elapsed_ms / 1000.0)
        / NULLIF(AVG(gs.time_elapsed_ms / 1000.0), 1), 0.2
    )::float                                                       AS time_std_norm,
    COALESCE(
        MIN(gs.time_elapsed_ms / 1000.0)
        / NULLIF(AVG(gs.time_elapsed_ms / 1000.0), 1), 0.1
    )::float                                                       AS time_min_norm,
    COALESCE(
        PERCENTILE_CONT(0.1) WITHIN GROUP (ORDER BY gs.time_elapsed_ms / 1000.0)
        / NULLIF(AVG(gs.time_elapsed_ms / 1000.0), 1), 0.1
    )::float                                                       AS time_p10_norm,
    COALESCE(
        AVG(gs.errors_count)::float
        / NULLIF(AVG(gs.time_elapsed_ms / 60000.0), 0), 0
    )::float                                                       AS error_rate,
    COALESCE(
        AVG(gs.hints_used)::float
        / NULLIF(COUNT(gs.id), 0), 0
    )::float                                                       AS hint_rate,
    COALESCE(
        COUNT(gs.id) FILTER (WHERE gs.status='completed')::float
        / NULLIF(COUNT(gs.id), 0), 0.7
    )::float                                                       AS fill_rate_norm,
    COALESCE(
        AVG(gs.time_elapsed_ms / 1000.0) / 1800.0, 0.5
    )::float                                                       AS duration_ratio,
    COALESCE(
        COUNT(gs.id) FILTER (WHERE gs.status='completed')::float
        / NULLIF(COUNT(gs.id), 0), 0.7
    )::float                                                       AS completion_ratio,
    COALESCE(
        1.0 - STDDEV(gs.time_elapsed_ms / 1000.0)
              / NULLIF(AVG(gs.time_elapsed_ms / 1000.0), 1), 0.5
    )::float                                                       AS consistency_score
FROM users u
LEFT JOIN game_sessions gs ON gs.user_id = u.id
{where_clause}
GROUP BY u.id
"""

FEATURE_GROUPS: dict[str, tuple[str, list[str]]] = {
    "churn": (
        CHURN_SQL,
        ["days_since_last_play","session_frequency","avg_session_duration",
         "total_games_played","win_rate_trend","hint_usage_trend",
         "difficulty_variety","completion_rate","error_rate_trend","longest_streak"],
    ),
    "skill": (
        SKILL_SQL,
        ["avg_solve_time_easy","avg_solve_time_medium","avg_solve_time_hard",
         "hint_rate","error_rate","completion_rate","difficulty_spread","games_last_30d"],
    ),
    "anomaly": (
        ANOMALY_SQL,
        ["time_mean_norm","time_std_norm","time_min_norm","time_p10_norm",
         "error_rate","hint_rate","fill_rate_norm","duration_ratio",
         "completion_ratio","consistency_score"],
    ),
}

# ── Helpers ────────────────────────────────────────────────────────────────────

def _write_features(
    conn,
    user_id: str,
    feature_group: str,
    features: dict,
    since_str: str | None,
    row_count: int,
    dry_run: bool,
) -> None:
    """Write one feature record + lineage to the feature_store."""
    if dry_run:
        log.debug(f"  [DRY-RUN] {feature_group} for {user_id[:8]}… = {list(features.keys())}")
        return

    with conn.cursor() as cur:
        # Get next version
        cur.execute(
            """
            SELECT COALESCE(MAX(feature_version), 0) + 1
            FROM feature_store
            WHERE entity_id = %s AND entity_type = 'user' AND feature_group = %s
            """,
            (user_id, feature_group),
        )
        next_ver = cur.fetchone()[0]

        # Demote previous current
        cur.execute(
            """
            UPDATE feature_store SET is_current = false
            WHERE entity_id = %s AND entity_type = 'user'
              AND feature_group = %s AND is_current = true
            """,
            (user_id, feature_group),
        )

        # Insert new snapshot
        feature_id = str(uuid.uuid4())
        cur.execute(
            """
            INSERT INTO feature_store (
                id, entity_id, entity_type, feature_group,
                feature_version, features, is_current,
                pipeline_name, pipeline_run_id, computed_at
            ) VALUES (%s,%s,'user',%s,%s,%s,true,%s,NULL,NOW())
            """,
            (feature_id, user_id, feature_group, next_ver,
             json.dumps(features), PIPELINE_NAME),
        )

        # Lineage record
        source_filter: dict = {"user_id": user_id}
        if since_str:
            source_filter["since"] = since_str
        cur.execute(
            """
            INSERT INTO feature_lineage
                (id, feature_id, source_table, source_filter, row_count, computed_at)
            VALUES (%s,%s,%s,%s,%s,NOW())
            """,
            (str(uuid.uuid4()), feature_id, "game_sessions",
             json.dumps(source_filter), row_count),
        )


def _run_group(
    conn,
    feature_group: str,
    sql_template: str,
    columns: list[str],
    where_clause: str,
    since_str: str | None,
    dry_run: bool,
) -> tuple[int, int]:
    """Run one feature group query and write results. Returns (written, skipped)."""
    import psycopg2.extras

    sql = sql_template.format(where_clause=where_clause)
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql)
        rows = cur.fetchall()

    log.info(f"  {feature_group}: {len(rows)} users")
    written = skipped = 0

    for row in rows:
        user_id = row["user_id"]
        features = {col: float(row[col]) for col in columns if col in row}

        # Count how many sessions contributed (use total_games_played for churn,
        # otherwise infer from non-null session aggregate fields)
        row_count = int(row.get("total_games_played", 0) or row.get("games_last_30d", 0) or 0)

        try:
            _write_features(conn, user_id, feature_group, features,
                            since_str, row_count, dry_run)
            written += 1
        except Exception as exc:
            log.warning(f"    Failed for {user_id}: {exc}")
            skipped += 1

    if not dry_run:
        conn.commit()

    return written, skipped


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Backfill ML feature store from historical game data."
    )
    parser.add_argument("--db-url",  default=DEFAULT_DB_URL, help="PostgreSQL connection string")
    parser.add_argument("--since",   default=None,           help="ISO date: only users active since (e.g. 2026-01-01)")
    parser.add_argument("--user-id", default=None,           help="Backfill a single user UUID")
    parser.add_argument("--groups",  default=None,           help="Comma-separated feature groups to run (default: all)")
    parser.add_argument("--dry-run", action="store_true",    help="Compute but do not persist")
    args = parser.parse_args()

    import psycopg2

    selected_groups = (
        [g.strip() for g in args.groups.split(",")]
        if args.groups
        else list(FEATURE_GROUPS.keys())
    )
    invalid = set(selected_groups) - set(FEATURE_GROUPS.keys())
    if invalid:
        log.error(f"Unknown feature groups: {invalid}")
        return 1

    # Build WHERE clause
    conditions: list[str] = []
    if args.user_id:
        conditions.append(f"u.id = '{args.user_id}'")
    if args.since:
        conditions.append(f"gs.started_at >= '{args.since}'::date")
    where_clause = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    log.info(f"Database    : {args.db_url.split('@')[-1]}")  # hide credentials
    log.info(f"Feature groups: {selected_groups}")
    log.info(f"Filter      : {where_clause or '(all users)'}")
    log.info(f"Dry-run     : {args.dry_run}")
    log.info("")

    conn = psycopg2.connect(args.db_url)
    total_written = total_skipped = 0

    try:
        for group in selected_groups:
            sql_template, columns = FEATURE_GROUPS[group]
            log.info(f"Processing feature group: {group}")
            written, skipped = _run_group(
                conn, group, sql_template, columns,
                where_clause, args.since, args.dry_run,
            )
            total_written += written
            total_skipped += skipped
            log.info(f"  → written={written}  skipped={skipped}")
            log.info("")
    finally:
        conn.close()

    log.info(f"Done — total written: {total_written}, total skipped: {total_skipped}")
    return 0 if total_skipped == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
