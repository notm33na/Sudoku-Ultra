"""
warehouse_schema.py — DuckDB star schema for the Sudoku Ultra data warehouse.

Star schema design
------------------
Dimension tables (slowly-changing attributes):
  dim_date        — pre-populated calendar for date lookups
  dim_difficulty  — static difficulty levels with metadata
  dim_user        — hashed/pseudonymised user dimension (PII-safe)
  dim_puzzle      — puzzle metadata (clues, techniques required)

Fact tables (append-only measurement records):
  fact_game_session  — one row per completed or abandoned game session
  fact_match         — one row per completed competitive match

All user-identifying columns are pseudonymised via SHA-256 hash so that
the warehouse can be safely queried by analysts without exposing PII.
Raw user_ids from PostgreSQL are hashed using pii_masking.pseudonymise().

Usage
-----
  # Bootstrap schema (idempotent — safe to re-run)
  python ml/scripts/warehouse_schema.py --db-path data/warehouse.duckdb

  # Verify schema
  python ml/scripts/warehouse_schema.py --verify --db-path data/warehouse.duckdb
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
log = logging.getLogger("warehouse_schema")

# ── DDL ───────────────────────────────────────────────────────────────────────

DDL_STATEMENTS = [
    # ── dim_date ─────────────────────────────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS dim_date (
        date_key        INTEGER PRIMARY KEY,   -- YYYYMMDD integer
        full_date       DATE    NOT NULL,
        year            SMALLINT NOT NULL,
        quarter         SMALLINT NOT NULL,     -- 1-4
        month           SMALLINT NOT NULL,     -- 1-12
        week_of_year    SMALLINT NOT NULL,     -- ISO week
        day_of_month    SMALLINT NOT NULL,     -- 1-31
        day_of_week     SMALLINT NOT NULL,     -- 0=Mon … 6=Sun
        is_weekend      BOOLEAN  NOT NULL,
        month_name      VARCHAR(9) NOT NULL,
        day_name        VARCHAR(9) NOT NULL
    )
    """,
    # ── dim_difficulty ───────────────────────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS dim_difficulty (
        difficulty_key  VARCHAR PRIMARY KEY,   -- 'easy', 'medium', etc.
        display_name    VARCHAR NOT NULL,
        sort_order      SMALLINT NOT NULL,     -- 1=super_easy … 6=super_hard
        min_clues       SMALLINT,
        max_clues       SMALLINT,
        is_active       BOOLEAN DEFAULT TRUE
    )
    """,
    # ── dim_user ─────────────────────────────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS dim_user (
        user_hash       VARCHAR PRIMARY KEY,   -- SHA-256 of raw user_id
        created_date_key INTEGER REFERENCES dim_date(date_key),
        country_code    VARCHAR(2),            -- ISO-3166 alpha-2, may be NULL
        skill_segment   SMALLINT,              -- K-Means cluster label (0-7), may be NULL
        is_active       BOOLEAN DEFAULT TRUE,
        first_seen_at   TIMESTAMP NOT NULL,
        last_updated_at TIMESTAMP NOT NULL
    )
    """,
    # ── dim_puzzle ───────────────────────────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS dim_puzzle (
        puzzle_hash         VARCHAR PRIMARY KEY,  -- SHA-256 of puzzle_id
        difficulty_key      VARCHAR REFERENCES dim_difficulty(difficulty_key),
        clue_count          SMALLINT,
        naked_singles       SMALLINT,
        hidden_singles      SMALLINT,
        pointing_pairs      SMALLINT,
        naked_pairs         SMALLINT,
        branching_factor    FLOAT,
        is_daily            BOOLEAN DEFAULT FALSE,
        is_generated        BOOLEAN DEFAULT FALSE,  -- TRUE = GAN-generated
        first_seen_at       TIMESTAMP NOT NULL
    )
    """,
    # ── fact_game_session ────────────────────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS fact_game_session (
        session_id          VARCHAR PRIMARY KEY,   -- pseudonymised session UUID
        date_key            INTEGER NOT NULL REFERENCES dim_date(date_key),
        user_hash           VARCHAR NOT NULL,      -- FK → dim_user
        puzzle_hash         VARCHAR,               -- FK → dim_puzzle (NULL if unknown)
        difficulty_key      VARCHAR NOT NULL REFERENCES dim_difficulty(difficulty_key),
        started_at          TIMESTAMP NOT NULL,
        completed_at        TIMESTAMP,             -- NULL if abandoned
        status              VARCHAR(12) NOT NULL,  -- 'completed' | 'abandoned' | 'timed_out'
        time_elapsed_ms     INTEGER,
        errors_count        SMALLINT DEFAULT 0,
        hints_used          SMALLINT DEFAULT 0,
        score               INTEGER,
        anomaly_score       FLOAT,                 -- from autoencoder; NULL if not scored
        is_anomalous        BOOLEAN DEFAULT FALSE,
        warehouse_loaded_at TIMESTAMP NOT NULL DEFAULT NOW()
    )
    """,
    # ── fact_match ───────────────────────────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS fact_match (
        match_id            VARCHAR PRIMARY KEY,   -- pseudonymised match UUID
        date_key            INTEGER NOT NULL REFERENCES dim_date(date_key),
        room_id             VARCHAR NOT NULL,
        winner_hash         VARCHAR NOT NULL,      -- FK → dim_user
        loser_hash          VARCHAR NOT NULL,      -- FK → dim_user
        difficulty_key      VARCHAR NOT NULL REFERENCES dim_difficulty(difficulty_key),
        end_reason          VARCHAR(20),           -- 'completion' | 'forfeit' | 'timeout'
        duration_ms         INTEGER,
        winner_elo_before   SMALLINT,
        winner_elo_after    SMALLINT,
        loser_elo_before    SMALLINT,
        loser_elo_after     SMALLINT,
        elo_delta           SMALLINT,
        completed_at        TIMESTAMP NOT NULL,
        warehouse_loaded_at TIMESTAMP NOT NULL DEFAULT NOW()
    )
    """,
]

# Indexes (applied after table creation)
INDEX_STATEMENTS = [
    "CREATE INDEX IF NOT EXISTS idx_fact_session_date    ON fact_game_session(date_key)",
    "CREATE INDEX IF NOT EXISTS idx_fact_session_user    ON fact_game_session(user_hash)",
    "CREATE INDEX IF NOT EXISTS idx_fact_session_diff    ON fact_game_session(difficulty_key)",
    "CREATE INDEX IF NOT EXISTS idx_fact_session_status  ON fact_game_session(status)",
    "CREATE INDEX IF NOT EXISTS idx_fact_match_date      ON fact_match(date_key)",
    "CREATE INDEX IF NOT EXISTS idx_fact_match_winner    ON fact_match(winner_hash)",
    "CREATE INDEX IF NOT EXISTS idx_fact_match_loser     ON fact_match(loser_hash)",
    "CREATE INDEX IF NOT EXISTS idx_dim_user_segment     ON dim_user(skill_segment)",
]

# Static difficulty dimension seed rows
DIFFICULTY_SEED = [
    ("super_easy", "Super Easy", 1, 45, 55),
    ("easy",       "Easy",       2, 36, 44),
    ("medium",     "Medium",     3, 28, 35),
    ("hard",       "Hard",       4, 23, 27),
    ("super_hard", "Super Hard", 5, 20, 22),
    ("extreme",    "Extreme",    6, 17, 19),
]


# ── Functions ─────────────────────────────────────────────────────────────────

def bootstrap(db_path: str) -> None:
    """Create all tables and indexes. Safe to re-run (all statements use IF NOT EXISTS)."""
    import duckdb

    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = duckdb.connect(str(path))

    try:
        log.info(f"Bootstrapping warehouse schema at {path}")
        for ddl in DDL_STATEMENTS:
            conn.execute(ddl)

        for idx in INDEX_STATEMENTS:
            conn.execute(idx)

        log.info("Tables and indexes created.")

        # Seed dim_difficulty if empty
        count = conn.execute("SELECT COUNT(*) FROM dim_difficulty").fetchone()[0]
        if count == 0:
            for row in DIFFICULTY_SEED:
                conn.execute(
                    "INSERT OR IGNORE INTO dim_difficulty "
                    "(difficulty_key, display_name, sort_order, min_clues, max_clues) "
                    "VALUES (?, ?, ?, ?, ?)",
                    list(row),
                )
            log.info(f"Seeded dim_difficulty with {len(DIFFICULTY_SEED)} rows.")
        else:
            log.info(f"dim_difficulty already has {count} rows — seed skipped.")

        # Populate dim_date for ±5 years around today
        _populate_dim_date(conn)

        conn.commit()
        log.info("Schema bootstrap complete.")
    finally:
        conn.close()


def _populate_dim_date(conn) -> None:
    """Populate dim_date for 2024-01-01 to 2030-12-31 (idempotent)."""
    from datetime import date, timedelta

    existing = conn.execute("SELECT COUNT(*) FROM dim_date").fetchone()[0]
    if existing > 0:
        log.info(f"dim_date already has {existing} rows — skipping population.")
        return

    start = date(2024, 1, 1)
    end   = date(2030, 12, 31)
    delta = timedelta(days=1)

    MONTH_NAMES = ["","January","February","March","April","May","June",
                   "July","August","September","October","November","December"]
    DAY_NAMES   = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]

    rows = []
    current = start
    while current <= end:
        iso = current.isocalendar()
        rows.append((
            int(current.strftime("%Y%m%d")),  # date_key
            current,                           # full_date
            current.year,
            (current.month - 1) // 3 + 1,     # quarter
            current.month,
            iso[1],                            # week_of_year
            current.day,
            current.weekday(),                 # day_of_week (0=Mon)
            current.weekday() >= 5,            # is_weekend
            MONTH_NAMES[current.month],
            DAY_NAMES[current.weekday()],
        ))
        current += delta

    conn.executemany(
        "INSERT OR IGNORE INTO dim_date VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        rows,
    )
    log.info(f"Populated dim_date with {len(rows)} rows (2024-01-01 → 2030-12-31).")


def verify(db_path: str) -> bool:
    """Return True if all 6 warehouse tables exist."""
    import duckdb

    expected = {"dim_date", "dim_difficulty", "dim_user", "dim_puzzle",
                "fact_game_session", "fact_match"}
    path = Path(db_path)
    if not path.exists():
        log.error(f"Warehouse file not found: {path}")
        return False

    conn = duckdb.connect(str(path), read_only=True)
    try:
        tables = {row[0] for row in conn.execute("SHOW TABLES").fetchall()}
        missing = expected - tables
        if missing:
            log.error(f"Missing tables: {missing}")
            return False

        for table in expected:
            count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            log.info(f"  {table}: {count} rows")

        log.info("Verification passed — all 6 tables present.")
        return True
    finally:
        conn.close()


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description="Bootstrap or verify the DuckDB warehouse schema.")
    parser.add_argument("--db-path", default="data/warehouse.duckdb",
                        help="Path to DuckDB warehouse file")
    parser.add_argument("--verify", action="store_true",
                        help="Verify schema rather than bootstrapping it")
    args = parser.parse_args()

    if args.verify:
        return 0 if verify(args.db_path) else 1
    else:
        bootstrap(args.db_path)
        return 0


if __name__ == "__main__":
    sys.exit(main())
