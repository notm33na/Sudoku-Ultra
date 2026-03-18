"""
Feature store — versioned, lineage-tracked feature persistence.

Design
------
Features are stored in the ``feature_store`` PostgreSQL table.  Each row is
an immutable snapshot of a feature vector for one (entity, feature_group)
pair at a point in time.  Versions are monotonically increasing integers; the
latest version for each entity+group is flagged ``is_current = true``.

When a new version is written, the previous current row is set to
``is_current = false`` in the same transaction.  This gives a full audit trail
while keeping current-feature queries fast (single-row index lookup).

Data lineage is recorded in ``feature_lineage``: each feature write can attach
one or more lineage rows describing the source tables and filters used to
compute the features.

Feature groups
--------------
  churn      10 engagement features used by the churn predictor
  skill      8 solve-behaviour features used by skill clustering
  anomaly    10 session-behaviour features used by the anomaly autoencoder
  difficulty Feature vector used by the difficulty classifier

Usage
-----
    from app.services.feature_store import feature_store

    # Write
    fid = feature_store.write(
        entity_id="user-uuid",
        entity_type="user",
        feature_group="churn",
        features={"days_since_last_play": 3.0, ...},
        pipeline_name="churn_risk_scorer",
        pipeline_run_id=None,          # optional MLflow / Airflow run id
        lineage=[{
            "source_table": "game_sessions",
            "source_filter": {"user_id": "user-uuid", "since": "2026-01-01"},
            "row_count": 42,
        }],
    )

    # Read current
    rec = feature_store.read_current("user-uuid", "user", "churn")
    if rec:
        features = rec["features"]

    # Read specific version
    rec = feature_store.read_version("user-uuid", "user", "churn", version=3)

    # Inspect lineage
    lineage = feature_store.get_lineage(fid)
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

import psycopg2
import psycopg2.extras

from app.config import settings
from app.logging import setup_logging

logger = setup_logging()

# ── Feature group definitions ──────────────────────────────────────────────────

FEATURE_GROUPS = {
    "churn": [
        "days_since_last_play", "session_frequency", "avg_session_duration",
        "total_games_played", "win_rate_trend", "hint_usage_trend",
        "difficulty_variety", "completion_rate", "error_rate_trend",
        "longest_streak",
    ],
    "skill": [
        "avg_solve_time_easy", "avg_solve_time_medium", "avg_solve_time_hard",
        "hint_rate", "error_rate", "completion_rate",
        "difficulty_spread", "games_last_30d",
    ],
    "anomaly": [
        "time_mean_norm", "time_std_norm", "time_min_norm", "time_p10_norm",
        "error_rate", "hint_rate", "fill_rate_norm",
        "duration_ratio", "completion_ratio", "consistency_score",
    ],
    "difficulty": [
        "clue_count", "naked_singles", "hidden_singles", "pointing_pairs",
        "box_reductions", "naked_pairs", "naked_triples", "x_wings",
        "swordfish", "branching_factor",
    ],
}


# ── Service class ──────────────────────────────────────────────────────────────

class FeatureStore:
    """
    Versioned, lineage-tracked feature storage backed by PostgreSQL.

    All methods are synchronous (psycopg2) to keep the interface simple and
    consistent with other ml-service Postgres usages.
    """

    def _conn(self) -> psycopg2.extensions.connection:
        return psycopg2.connect(settings.DATABASE_URL)

    # ── Write ──────────────────────────────────────────────────────────────

    def write(
        self,
        entity_id:    str,
        entity_type:  str,
        feature_group: str,
        features:     dict[str, Any],
        pipeline_name: str,
        pipeline_run_id: str | None = None,
        lineage: list[dict[str, Any]] | None = None,
    ) -> str:
        """
        Persist a new feature snapshot and return its ``id``.

        The previous current version (if any) is marked ``is_current=false``
        in the same transaction.  The new record is always ``is_current=true``.

        ``lineage`` is a list of dicts with keys:
          source_table  (str)  — table name, e.g. "game_sessions"
          source_filter (dict) — query predicate used to fetch raw data
          row_count     (int)  — number of rows consumed (optional)
        """
        conn = self._conn()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                # Get the next version number
                cur.execute(
                    """
                    SELECT COALESCE(MAX(feature_version), 0) + 1 AS next_ver
                    FROM feature_store
                    WHERE entity_id = %s
                      AND entity_type = %s
                      AND feature_group = %s
                    """,
                    (entity_id, entity_type, feature_group),
                )
                next_ver = cur.fetchone()["next_ver"]

                # Demote the previous current row
                cur.execute(
                    """
                    UPDATE feature_store
                       SET is_current = false
                     WHERE entity_id    = %s
                       AND entity_type  = %s
                       AND feature_group = %s
                       AND is_current   = true
                    """,
                    (entity_id, entity_type, feature_group),
                )

                # Insert new snapshot
                feature_id = str(uuid.uuid4())
                cur.execute(
                    """
                    INSERT INTO feature_store (
                        id, entity_id, entity_type, feature_group,
                        feature_version, features, is_current,
                        pipeline_name, pipeline_run_id, computed_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, true, %s, %s, %s)
                    """,
                    (
                        feature_id, entity_id, entity_type, feature_group,
                        next_ver, json.dumps(features), pipeline_name,
                        pipeline_run_id,
                        datetime.now(timezone.utc),
                    ),
                )

                # Write lineage records
                for entry in (lineage or []):
                    cur.execute(
                        """
                        INSERT INTO feature_lineage (
                            id, feature_id, source_table, source_filter,
                            row_count, computed_at
                        ) VALUES (%s, %s, %s, %s, %s, %s)
                        """,
                        (
                            str(uuid.uuid4()),
                            feature_id,
                            entry["source_table"],
                            json.dumps(entry.get("source_filter", {})),
                            entry.get("row_count"),
                            datetime.now(timezone.utc),
                        ),
                    )

            conn.commit()
            logger.debug(
                f"[FeatureStore] wrote {feature_group} v{next_ver} "
                f"for {entity_type}:{entity_id}"
            )
            return feature_id

        except Exception as exc:
            conn.rollback()
            logger.error(f"[FeatureStore] write failed: {exc}")
            raise
        finally:
            conn.close()

    # ── Read ───────────────────────────────────────────────────────────────

    def read_current(
        self,
        entity_id:    str,
        entity_type:  str,
        feature_group: str,
    ) -> dict[str, Any] | None:
        """Return the current (latest) feature record, or None."""
        conn = self._conn()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT * FROM feature_store
                    WHERE entity_id    = %s
                      AND entity_type  = %s
                      AND feature_group = %s
                      AND is_current   = true
                    LIMIT 1
                    """,
                    (entity_id, entity_type, feature_group),
                )
                row = cur.fetchone()
        finally:
            conn.close()

        if row is None:
            return None
        return self._deserialise(dict(row))

    def read_version(
        self,
        entity_id:    str,
        entity_type:  str,
        feature_group: str,
        version:       int,
    ) -> dict[str, Any] | None:
        """Return a specific version of a feature record, or None."""
        conn = self._conn()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT * FROM feature_store
                    WHERE entity_id      = %s
                      AND entity_type    = %s
                      AND feature_group  = %s
                      AND feature_version = %s
                    LIMIT 1
                    """,
                    (entity_id, entity_type, feature_group, version),
                )
                row = cur.fetchone()
        finally:
            conn.close()

        return self._deserialise(dict(row)) if row else None

    def list_versions(
        self,
        entity_id:    str,
        entity_type:  str,
        feature_group: str,
    ) -> list[dict[str, Any]]:
        """Return all versions for an entity+group, newest first."""
        conn = self._conn()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT id, feature_version, is_current,
                           pipeline_name, pipeline_run_id, computed_at
                    FROM feature_store
                    WHERE entity_id    = %s
                      AND entity_type  = %s
                      AND feature_group = %s
                    ORDER BY feature_version DESC
                    """,
                    (entity_id, entity_type, feature_group),
                )
                return [dict(r) for r in cur.fetchall()]
        finally:
            conn.close()

    def batch_read_current(
        self,
        entity_ids:    list[str],
        entity_type:   str,
        feature_group: str,
    ) -> dict[str, dict[str, Any]]:
        """
        Return current features for a list of entity IDs.

        Returns a dict keyed by entity_id.  Missing entities are absent.
        """
        if not entity_ids:
            return {}
        conn = self._conn()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT * FROM feature_store
                    WHERE entity_id   = ANY(%s)
                      AND entity_type  = %s
                      AND feature_group = %s
                      AND is_current   = true
                    """,
                    (entity_ids, entity_type, feature_group),
                )
                rows = cur.fetchall()
        finally:
            conn.close()

        return {row["entity_id"]: self._deserialise(dict(row)) for row in rows}

    # ── Lineage ────────────────────────────────────────────────────────────

    def get_lineage(self, feature_id: str) -> list[dict[str, Any]]:
        """Return all lineage records for a feature snapshot."""
        conn = self._conn()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    "SELECT * FROM feature_lineage WHERE feature_id = %s ORDER BY computed_at",
                    (feature_id,),
                )
                return [dict(r) for r in cur.fetchall()]
        finally:
            conn.close()

    # ── Stats ──────────────────────────────────────────────────────────────

    def stats(self) -> dict[str, Any]:
        """Return row counts per feature group for the health endpoint."""
        conn = self._conn()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT feature_group,
                           COUNT(*) FILTER (WHERE is_current)     AS current_count,
                           COUNT(*)                               AS total_versions,
                           MAX(computed_at)                       AS last_written
                    FROM feature_store
                    GROUP BY feature_group
                    ORDER BY feature_group
                    """
                )
                return {
                    row["feature_group"]: {
                        "current_count":   row["current_count"],
                        "total_versions":  row["total_versions"],
                        "last_written":    row["last_written"].isoformat() if row["last_written"] else None,
                    }
                    for row in cur.fetchall()
                }
        finally:
            conn.close()

    # ── Internal ───────────────────────────────────────────────────────────

    @staticmethod
    def _deserialise(row: dict[str, Any]) -> dict[str, Any]:
        """Ensure ``features`` is a dict (psycopg2 may return it as str)."""
        if isinstance(row.get("features"), str):
            row["features"] = json.loads(row["features"])
        if isinstance(row.get("source_filter"), str):
            row["source_filter"] = json.loads(row["source_filter"])
        return row


# Singleton
feature_store = FeatureStore()
