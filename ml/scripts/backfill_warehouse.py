"""
backfill_warehouse.py — PostgreSQL → DuckDB warehouse backfill.

Reads historical game data from PostgreSQL and loads it into the DuckDB
star-schema warehouse in idempotent batches.

Idempotency: each fact row is identified by its primary key
(session_id / match_id). Rows already present are skipped via INSERT OR IGNORE.
User/puzzle dimension rows are upserted (INSERT OR REPLACE).

Usage
-----
  # Full historical backfill
  python ml/scripts/backfill_warehouse.py

  # Backfill only sessions since a date (incremental)
  python ml/scripts/backfill_warehouse.py --since 2026-01-01

  # Dry-run: print counts without writing
  python ml/scripts/backfill_warehouse.py --dry-run

  # Override paths
  python ml/scripts/backfill_warehouse.py \\
      --db-url postgresql://... \\
      --warehouse data/warehouse.duckdb
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
log = logging.getLogger("backfill_warehouse")

sys.path.insert(0, str(Path(__file__).resolve().parents[0]))

DEFAULT_DB_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://sudoku:sudoku_dev_password@localhost:5432/sudoku_ultra",
)
DEFAULT_WAREHOUSE = os.getenv("DUCKDB_WAREHOUSE_PATH", "data/warehouse.duckdb")
BATCH_SIZE = 500

# ── Helpers ───────────────────────────────────────────────────────────────────


def _date_key(dt) -> int | None:
    """Convert a datetime/date to YYYYMMDD integer."""
    if dt is None:
        return None
    if hasattr(dt, "date"):
        dt = dt.date()
    return int(dt.strftime("%Y%m%d"))


def _now_ts() -> datetime:
    return datetime.now(timezone.utc)


# ── Dimension loaders ─────────────────────────────────────────────────────────


def _upsert_users(pg_conn, duck_conn, since_str: str | None, dry_run: bool) -> int:
    """Load dim_user rows from PostgreSQL users table."""
    from pii_masking import pseudonymise

    where = f"WHERE created_at >= '{since_str}'::date" if since_str else ""
    with pg_conn.cursor() as cur:
        cur.execute(f"""
            SELECT id, created_at
            FROM users
            {where}
            ORDER BY created_at
        """)
        rows = cur.fetchall()

    count = 0
    now = _now_ts()
    for batch_start in range(0, len(rows), BATCH_SIZE):
        batch = rows[batch_start:batch_start + BATCH_SIZE]
        for (user_id, created_at) in batch:
            user_hash = pseudonymise(str(user_id))
            dk = _date_key(created_at)
            if not dry_run:
                duck_conn.execute(
                    """
                    INSERT OR REPLACE INTO dim_user
                        (user_hash, created_date_key, first_seen_at, last_updated_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    [user_hash, dk, created_at, now],
                )
            count += 1

    if not dry_run:
        duck_conn.commit()
    log.info(f"  dim_user: {count} rows {'(dry-run)' if dry_run else 'upserted'}")
    return count


def _upsert_puzzles(pg_conn, duck_conn, since_str: str | None, dry_run: bool) -> int:
    """Load dim_puzzle rows from PostgreSQL puzzles table."""
    from pii_masking import pseudonymise

    where = f"WHERE created_at >= '{since_str}'::date" if since_str else ""
    with pg_conn.cursor() as cur:
        cur.execute(f"""
            SELECT id, difficulty, clue_count, created_at
            FROM puzzles
            {where}
        """)
        rows = cur.fetchall()

    count = 0
    now = _now_ts()
    for (puzzle_id, difficulty, clue_count, created_at) in rows:
        puzzle_hash = pseudonymise(str(puzzle_id))
        if not dry_run:
            duck_conn.execute(
                """
                INSERT OR IGNORE INTO dim_puzzle
                    (puzzle_hash, difficulty_key, clue_count, first_seen_at)
                VALUES (?, ?, ?, ?)
                """,
                [puzzle_hash, difficulty, clue_count, created_at or now],
            )
        count += 1

    if not dry_run and count:
        duck_conn.commit()
    log.info(f"  dim_puzzle: {count} rows {'(dry-run)' if dry_run else 'upserted'}")
    return count


# ── Fact loaders ──────────────────────────────────────────────────────────────


def _load_fact_sessions(
    pg_conn, duck_conn, since_str: str | None, dry_run: bool,
) -> tuple[int, int]:
    """Load fact_game_session rows. Returns (inserted, skipped)."""
    from pii_masking import pseudonymise

    where = f"WHERE gs.started_at >= '{since_str}'::date" if since_str else ""
    with pg_conn.cursor() as cur:
        cur.execute(f"""
            SELECT
                gs.id,
                gs.user_id,
                gs.puzzle_id,
                gs.difficulty,
                gs.started_at,
                gs.completed_at,
                gs.status,
                gs.time_elapsed_ms,
                gs.errors_count,
                gs.hints_used,
                gs.score
            FROM game_sessions gs
            {where}
            ORDER BY gs.started_at
        """)
        rows = cur.fetchall()

    inserted = skipped = 0
    now = _now_ts()

    for batch_start in range(0, len(rows), BATCH_SIZE):
        batch = rows[batch_start:batch_start + BATCH_SIZE]
        for (sid, uid, pid, diff, started_at, completed_at, status,
             elapsed_ms, errors, hints, score) in batch:

            session_hash = pseudonymise(str(sid))
            user_hash    = pseudonymise(str(uid))
            puzzle_hash  = pseudonymise(str(pid)) if pid else None
            dk = _date_key(started_at)
            if dk is None:
                skipped += 1
                continue

            if not dry_run:
                try:
                    duck_conn.execute(
                        """
                        INSERT OR IGNORE INTO fact_game_session (
                            session_id, date_key, user_hash, puzzle_hash,
                            difficulty_key, started_at, completed_at, status,
                            time_elapsed_ms, errors_count, hints_used, score,
                            warehouse_loaded_at
                        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                        """,
                        [session_hash, dk, user_hash, puzzle_hash,
                         diff or "medium", started_at, completed_at,
                         status or "completed", elapsed_ms, errors or 0,
                         hints or 0, score, now],
                    )
                    inserted += 1
                except Exception as exc:
                    log.warning(f"    Skipping session {sid}: {exc}")
                    skipped += 1
            else:
                inserted += 1

        if not dry_run:
            duck_conn.commit()

    log.info(f"  fact_game_session: inserted={inserted} skipped={skipped}"
             f"{'  (dry-run)' if dry_run else ''}")
    return inserted, skipped


def _load_fact_matches(
    pg_conn, duck_conn, since_str: str | None, dry_run: bool,
) -> tuple[int, int]:
    """Load fact_match rows from multiplayer_match table."""
    from pii_masking import pseudonymise

    where = f"WHERE completed_at >= '{since_str}'::date" if since_str else ""

    # Try multiplayer_match table; fall back gracefully if it doesn't exist
    try:
        with pg_conn.cursor() as cur:
            cur.execute(f"""
                SELECT
                    id, room_id, winner_id, loser_id,
                    difficulty, end_reason, duration_ms,
                    winner_elo_before, winner_elo_after,
                    loser_elo_before, loser_elo_after,
                    completed_at
                FROM multiplayer_match
                {where}
                ORDER BY completed_at
            """)
            rows = cur.fetchall()
    except Exception as exc:
        log.warning(f"  multiplayer_match unavailable ({exc}) — skipping fact_match")
        return 0, 0

    inserted = skipped = 0
    now = _now_ts()

    for (mid, room_id, winner_id, loser_id, diff, end_reason, duration_ms,
         w_elo_before, w_elo_after, l_elo_before, l_elo_after,
         completed_at) in rows:

        match_hash  = pseudonymise(str(mid))
        winner_hash = pseudonymise(str(winner_id))
        loser_hash  = pseudonymise(str(loser_id))
        dk = _date_key(completed_at)
        if dk is None:
            skipped += 1
            continue

        elo_delta = (w_elo_after - w_elo_before) if (w_elo_after and w_elo_before) else None

        if not dry_run:
            try:
                duck_conn.execute(
                    """
                    INSERT OR IGNORE INTO fact_match (
                        match_id, date_key, room_id, winner_hash, loser_hash,
                        difficulty_key, end_reason, duration_ms,
                        winner_elo_before, winner_elo_after,
                        loser_elo_before, loser_elo_after,
                        elo_delta, completed_at, warehouse_loaded_at
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    [match_hash, dk, str(room_id), winner_hash, loser_hash,
                     diff or "medium", end_reason, duration_ms,
                     w_elo_before, w_elo_after, l_elo_before, l_elo_after,
                     elo_delta, completed_at, now],
                )
                inserted += 1
            except Exception as exc:
                log.warning(f"    Skipping match {mid}: {exc}")
                skipped += 1
        else:
            inserted += 1

    if not dry_run and inserted:
        duck_conn.commit()

    log.info(f"  fact_match: inserted={inserted} skipped={skipped}"
             f"{'  (dry-run)' if dry_run else ''}")
    return inserted, skipped


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Backfill PostgreSQL data into the DuckDB star-schema warehouse."
    )
    parser.add_argument("--db-url",    default=DEFAULT_DB_URL,
                        help="PostgreSQL connection string")
    parser.add_argument("--warehouse", default=DEFAULT_WAREHOUSE,
                        help="DuckDB warehouse file path")
    parser.add_argument("--since",     default=None,
                        help="ISO date: only data since this date (e.g. 2026-01-01)")
    parser.add_argument("--dry-run",   action="store_true",
                        help="Compute row counts without writing")
    args = parser.parse_args()

    import duckdb
    import psycopg2

    # Ensure schema exists
    from warehouse_schema import bootstrap as ensure_schema
    ensure_schema(args.warehouse)

    log.info(f"Database    : {args.db_url.split('@')[-1]}")
    log.info(f"Warehouse   : {args.warehouse}")
    log.info(f"Since       : {args.since or '(all time)'}")
    log.info(f"Dry-run     : {args.dry_run}")
    log.info("")

    pg   = psycopg2.connect(args.db_url)
    duck = duckdb.connect(args.warehouse)

    try:
        log.info("Loading dimension tables…")
        _upsert_users(pg, duck, args.since, args.dry_run)
        _upsert_puzzles(pg, duck, args.since, args.dry_run)

        log.info("Loading fact tables…")
        sess_ins, sess_skip = _load_fact_sessions(pg, duck, args.since, args.dry_run)
        match_ins, match_skip = _load_fact_matches(pg, duck, args.since, args.dry_run)

    finally:
        pg.close()
        duck.close()

    total_ins  = sess_ins + match_ins
    total_skip = sess_skip + match_skip
    log.info("")
    log.info(f"Done — total inserted: {total_ins}  skipped: {total_skip}")
    return 0 if total_skip == 0 or total_ins > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
