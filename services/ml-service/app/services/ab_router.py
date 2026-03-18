"""
A/B test router — deterministic variant assignment for ML model experiments.

How it works
------------
1. Experiment configs are read from the ``ab_test_config`` PostgreSQL table
   and cached in memory for ``CACHE_TTL_SECS`` seconds.
2. Variant assignment is deterministic: MD5(user_id + experiment_name) % 100.
   Users with a bucket value below ``traffic_split * 100`` are in "treatment";
   all others are in "control".  The same user always gets the same variant for
   the same experiment.
3. The router returns the assigned variant name *and* the MLflow model URI
   (``models:/<model_name>/<variant_stage>``) so callers can load the right
   model version without extra lookups.

Usage
-----
    from app.services.ab_router import ab_router

    variant, model_uri = ab_router.assign("user-uuid", "classifier-v2-test")
    # variant  → "control" | "treatment"
    # model_uri → "models:/difficulty-classifier/Production"
"""

from __future__ import annotations

import hashlib
import time
from typing import Any

from app.config import settings
from app.logging import setup_logging

logger = setup_logging()

CACHE_TTL_SECS = 300   # refresh experiment configs every 5 minutes


class ABRouter:
    """
    Thread-safe A/B router with in-memory config cache.

    The cache is intentionally simple (single dict + timestamp) to avoid
    adding a Redis dependency for a read-heavy, rarely-mutated config table.
    """

    def __init__(self) -> None:
        self._cache: dict[str, dict[str, Any]] = {}
        self._cache_loaded_at: float = 0.0

    # ── Public API ────────────────────────────────────────────────────────

    def assign(self, user_id: str, experiment_name: str) -> tuple[str, str]:
        """
        Return (variant, model_uri) for the given user and experiment.

        Variant is ``"control"`` if:
          - the experiment does not exist,
          - its status is not ``"active"``,
          - the experiment end_date has passed, or
          - the user's hash bucket falls outside the treatment range.

        model_uri follows the MLflow Models URI scheme:
          ``models:/<model_name>/<variant_stage>``
        """
        config = self._get_config(experiment_name)

        if config is None:
            logger.debug(f"[ABRouter] experiment '{experiment_name}' not found → control")
            return "control", ""

        if config["status"] != "active":
            return "control", self._uri(config, "control")

        if config.get("end_date") and time.time() > config["end_date"]:
            return "control", self._uri(config, "control")

        bucket = self._hash_bucket(user_id, experiment_name)
        threshold = int(config["traffic_split"] * 100)
        variant = "treatment" if bucket < threshold else "control"

        return variant, self._uri(config, variant)

    def get_experiment(self, experiment_name: str) -> dict[str, Any] | None:
        """Return the cached config dict for an experiment, or None."""
        return self._get_config(experiment_name)

    def list_experiments(self) -> list[dict[str, Any]]:
        """Return all cached experiment configs."""
        self._maybe_refresh()
        return list(self._cache.values())

    def invalidate_cache(self) -> None:
        """Force the next call to reload configs from the database."""
        self._cache_loaded_at = 0.0

    # ── Internals ─────────────────────────────────────────────────────────

    @staticmethod
    def _hash_bucket(user_id: str, experiment_name: str) -> int:
        """
        Deterministic bucket in [0, 100) for the (user, experiment) pair.

        Uses the lower 32 bits of MD5 to avoid modulo bias across the
        full 128-bit hash space.
        """
        raw = f"{user_id}:{experiment_name}".encode()
        digest = hashlib.md5(raw).hexdigest()
        return int(digest[:8], 16) % 100

    @staticmethod
    def _uri(config: dict[str, Any], variant: str) -> str:
        stage = (
            config["treatment_variant"] if variant == "treatment"
            else config["control_variant"]
        )
        return f"models:/{config['model_name']}/{stage}"

    def _get_config(self, experiment_name: str) -> dict[str, Any] | None:
        self._maybe_refresh()
        return self._cache.get(experiment_name)

    def _maybe_refresh(self) -> None:
        if time.time() - self._cache_loaded_at < CACHE_TTL_SECS:
            return
        try:
            self._cache = self._load_from_db()
            self._cache_loaded_at = time.time()
            logger.debug(f"[ABRouter] cache refreshed — {len(self._cache)} experiments")
        except Exception as exc:
            logger.warning(f"[ABRouter] failed to refresh config cache: {exc}")

    def _load_from_db(self) -> dict[str, dict[str, Any]]:
        """Load all experiments from the ab_test_config table."""
        import psycopg2
        import psycopg2.extras

        conn = psycopg2.connect(settings.DATABASE_URL)
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT
                        experiment_name,
                        model_name,
                        control_variant,
                        treatment_variant,
                        traffic_split,
                        status,
                        description,
                        EXTRACT(EPOCH FROM start_date) AS start_epoch,
                        EXTRACT(EPOCH FROM end_date)   AS end_date
                    FROM ab_test_config
                    ORDER BY created_at
                    """
                )
                rows = cur.fetchall()
        finally:
            conn.close()

        return {
            row["experiment_name"]: {
                "experiment_name":   row["experiment_name"],
                "model_name":        row["model_name"],
                "control_variant":   row["control_variant"],
                "treatment_variant": row["treatment_variant"],
                "traffic_split":     float(row["traffic_split"]),
                "status":            row["status"],
                "description":       row["description"],
                "start_epoch":       row["start_epoch"],
                "end_date":          float(row["end_date"]) if row["end_date"] else None,
            }
            for row in rows
        }


# Singleton
ab_router = ABRouter()
