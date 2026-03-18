"""
gdpr_deletion.py — GDPR right-to-erasure implementation.

Deletes or anonymises all data associated with a user across:
  1. PostgreSQL  — personal data tables (users, game_sessions, etc.)
  2. DuckDB warehouse — pseudonymised rows keyed by user_hash

Deletion strategy
-----------------
PostgreSQL rows are hard-deleted (ON DELETE CASCADE handles child rows).
Warehouse rows keyed by user_hash are also hard-deleted since the hash
itself is a pseudonymous identifier that must be removed on erasure.

A deletion audit record is written to the `gdpr_deletion_log` table
(created on first use) so that future data sync jobs can skip this user.

Usage
-----
  # Delete a single user
  python ml/scripts/gdpr_deletion.py --user-id <uuid>

  # Dry-run: show what would be deleted
  python ml/scripts/gdpr_deletion.py --user-id <uuid> --dry-run

  # Process a CSV of user IDs
  python ml/scripts/gdpr_deletion.py --user-id-file erasure_requests.csv
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
log = logging.getLogger("gdpr_deletion")

sys.path.insert(0, str(Path(__file__).resolve().parent))

DEFAULT_DB_URL       = os.getenv("DATABASE_URL",
    "postgresql://sudoku:sudoku_dev_password@localhost:5432/sudoku_ultra")
DEFAULT_WAREHOUSE    = os.getenv("DUCKDB_WAREHOUSE_PATH", "data/warehouse.duckdb")

# Tables to hard-delete from PostgreSQL (in safe order; cascades handle children)
PG_DELETE_PLAN = [
    # (table, user_id_column)
    ("feature_store",       "entity_id"),
    ("ab_test_result",      "user_id"),
    ("game_sessions",       "user_id"),
    ("streaks",             "user_id"),
    ("daily_puzzle_attempts","user_id"),
    ("user_lessons",        "user_id"),
    ("friendships",         "user_id"),
    ("friendships",         "friend_id"),
    ("player_ratings",      "user_id"),
    ("multiplayer_match",   "winner_id"),
    ("multiplayer_match",   "loser_id"),
    ("activity_feeds",      "user_id"),
    ("notifications",       "user_id"),
    ("users",               "id"),         # must be last
]


# ── Core ──────────────────────────────────────────────────────────────────────

def delete_user(
    user_id: str,
    pg_conn,
    duck_conn,
    dry_run: bool = False,
) -> dict:
    """
    Erase all data for ``user_id``. Returns a summary dict.
    """
    from pii_masking import pseudonymise

    user_hash = pseudonymise(user_id)
    now = datetime.now(timezone.utc)
    summary: dict[str, int] = {}

    # 1. PostgreSQL deletions
    for (table, col) in PG_DELETE_PLAN:
        try:
            if dry_run:
                with pg_conn.cursor() as cur:
                    cur.execute(f"SELECT COUNT(*) FROM {table} WHERE {col} = %s", (user_id,))
                    count = cur.fetchone()[0]
            else:
                with pg_conn.cursor() as cur:
                    cur.execute(f"DELETE FROM {table} WHERE {col} = %s", (user_id,))
                    count = cur.rowcount
            summary[f"pg:{table}:{col}"] = count
        except Exception as exc:
            log.warning(f"  {table}.{col}: {exc} (table may not exist)")

    if not dry_run:
        pg_conn.commit()

    # 2. DuckDB warehouse deletions
    warehouse_tables = [
        ("fact_game_session", "user_hash"),
        ("fact_match",        "winner_hash"),
        ("fact_match",        "loser_hash"),
        ("dim_user",          "user_hash"),
    ]
    for (table, col) in warehouse_tables:
        try:
            if dry_run:
                count = duck_conn.execute(
                    f"SELECT COUNT(*) FROM {table} WHERE {col} = ?", [user_hash]
                ).fetchone()[0]
            else:
                duck_conn.execute(
                    f"DELETE FROM {table} WHERE {col} = ?", [user_hash]
                )
                count = -1  # DuckDB doesn't return rowcount on DELETE
            summary[f"duckdb:{table}:{col}"] = count
        except Exception as exc:
            log.warning(f"  DuckDB {table}.{col}: {exc}")

    if not dry_run:
        duck_conn.commit()

    # 3. Write deletion audit log (PostgreSQL)
    if not dry_run:
        _write_audit(pg_conn, user_id, now)

    return summary


def _write_audit(pg_conn, user_id: str, deleted_at: datetime) -> None:
    """Ensure gdpr_deletion_log table exists and record the deletion."""
    try:
        with pg_conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS gdpr_deletion_log (
                    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    user_id     VARCHAR NOT NULL,
                    requested_at TIMESTAMP NOT NULL,
                    completed_at TIMESTAMP NOT NULL DEFAULT NOW()
                )
            """)
            cur.execute(
                "INSERT INTO gdpr_deletion_log (user_id, requested_at) VALUES (%s, %s)",
                (user_id, deleted_at),
            )
        pg_conn.commit()
    except Exception as exc:
        log.warning(f"Could not write GDPR audit log: {exc}")


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        description="GDPR right-to-erasure: delete all data for a user."
    )
    parser.add_argument("--user-id",      default=None, help="Single user UUID to delete")
    parser.add_argument("--user-id-file", default=None,
                        help="CSV/text file with one user UUID per line")
    parser.add_argument("--db-url",    default=DEFAULT_DB_URL)
    parser.add_argument("--warehouse", default=DEFAULT_WAREHOUSE)
    parser.add_argument("--dry-run",   action="store_true",
                        help="Show counts without deleting")
    args = parser.parse_args()

    if not args.user_id and not args.user_id_file:
        parser.error("Provide --user-id or --user-id-file")

    user_ids: list[str] = []
    if args.user_id:
        user_ids.append(args.user_id)
    if args.user_id_file:
        path = Path(args.user_id_file)
        if not path.exists():
            log.error(f"File not found: {path}")
            return 1
        user_ids.extend(
            line.strip() for line in path.read_text().splitlines()
            if line.strip() and not line.startswith("#")
        )

    import duckdb
    import psycopg2

    pg   = psycopg2.connect(args.db_url)
    duck = duckdb.connect(args.warehouse) if Path(args.warehouse).exists() else None

    errors = 0
    for uid in user_ids:
        log.info(f"{'[DRY-RUN] ' if args.dry_run else ''}Deleting user {uid}…")
        try:
            summary = delete_user(uid, pg, duck, dry_run=args.dry_run)
            for key, count in summary.items():
                if count != 0:
                    log.info(f"  {key}: {count if count >= 0 else 'deleted'}")
        except Exception as exc:
            log.error(f"  FAILED for {uid}: {exc}")
            errors += 1

    pg.close()
    if duck:
        duck.close()

    return 0 if errors == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
