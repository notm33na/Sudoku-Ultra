"""
A/B Testing router — manage ML model experiments and record results.

Endpoints
---------
POST   /api/v1/ab-tests/experiments              — create or update an experiment
GET    /api/v1/ab-tests/experiments              — list all experiments
GET    /api/v1/ab-tests/assign                   — get variant assignment for a user
POST   /api/v1/ab-tests/results                  — record a metric observation
GET    /api/v1/ab-tests/experiments/{name}/summary — aggregate results by variant
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

import psycopg2
import psycopg2.extras
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.config import settings
from app.services.ab_router import ab_router

router = APIRouter(prefix="/api/v1/ab-tests", tags=["ab-testing"])


# ── Pydantic models ────────────────────────────────────────────────────────────

class ExperimentRequest(BaseModel):
    experiment_name:   str   = Field(...,  description="Unique experiment identifier")
    model_name:        str   = Field(...,  description="MLflow registered model name")
    control_variant:   str   = Field("Production", description="MLflow stage for control")
    treatment_variant: str   = Field("Staging",    description="MLflow stage for treatment")
    traffic_split:     float = Field(0.5,  ge=0.0, le=1.0,
                                     description="Fraction of users routed to treatment")
    status:            str   = Field("active",
                                     description="active | paused | completed")
    description:       str   = Field("", description="Human-readable purpose")
    end_date:          datetime | None = Field(None, description="Optional expiry (UTC)")


class RecordResultRequest(BaseModel):
    experiment_name: str   = Field(..., description="Experiment this result belongs to")
    user_id:         str   = Field(..., description="User UUID")
    variant:         str   = Field(..., description="control | treatment")
    metric_name:     str   = Field(..., description="e.g. accuracy, solve_time_ms")
    metric_value:    float = Field(..., description="Observed metric value")


# ── Helpers ────────────────────────────────────────────────────────────────────

def _db() -> psycopg2.extensions.connection:
    return psycopg2.connect(settings.DATABASE_URL)


# ── Endpoint 1: create / update experiment ────────────────────────────────────

@router.post("/experiments", status_code=201)
async def create_experiment(req: ExperimentRequest) -> dict[str, Any]:
    """
    Create a new A/B experiment or update an existing one (upsert by name).

    Invalidates the in-memory cache so the next assignment call picks up
    the new config immediately.
    """
    conn = _db()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                INSERT INTO ab_test_config (
                    id, experiment_name, model_name,
                    control_variant, treatment_variant,
                    traffic_split, status, description,
                    start_date, end_date,
                    created_at, updated_at
                ) VALUES (
                    %s, %s, %s, %s, %s,
                    %s, %s, %s,
                    NOW(), %s,
                    NOW(), NOW()
                )
                ON CONFLICT (experiment_name) DO UPDATE SET
                    model_name        = EXCLUDED.model_name,
                    control_variant   = EXCLUDED.control_variant,
                    treatment_variant = EXCLUDED.treatment_variant,
                    traffic_split     = EXCLUDED.traffic_split,
                    status            = EXCLUDED.status,
                    description       = EXCLUDED.description,
                    end_date          = EXCLUDED.end_date,
                    updated_at        = NOW()
                RETURNING *
                """,
                (
                    str(uuid.uuid4()),
                    req.experiment_name, req.model_name,
                    req.control_variant, req.treatment_variant,
                    req.traffic_split, req.status, req.description,
                    req.end_date,
                ),
            )
            row = cur.fetchone()
        conn.commit()
    except Exception as exc:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(exc))
    finally:
        conn.close()

    ab_router.invalidate_cache()
    return {"status": "ok", "experiment": dict(row)}


# ── Endpoint 2: list experiments ───────────────────────────────────────────────

@router.get("/experiments")
async def list_experiments() -> list[dict[str, Any]]:
    """Return all experiments (reads from cache; refreshes if stale)."""
    return ab_router.list_experiments()


# ── Endpoint 3: get variant assignment ────────────────────────────────────────

@router.get("/assign")
async def assign_variant(
    experiment_name: str = Query(..., description="Experiment identifier"),
    user_id:         str = Query(..., description="User UUID for deterministic assignment"),
) -> dict[str, Any]:
    """
    Return the variant assigned to a user for the given experiment.

    Assignment is deterministic — the same (user_id, experiment_name) pair
    always returns the same variant.  The response includes the MLflow model
    URI for the assigned variant so callers can load the right model version.

    Returns ``variant: "control"`` if the experiment is not found, paused,
    or has passed its end_date.
    """
    config = ab_router.get_experiment(experiment_name)
    if config is None:
        raise HTTPException(
            status_code=404,
            detail=f"Experiment '{experiment_name}' not found",
        )

    variant, model_uri = ab_router.assign(user_id, experiment_name)
    return {
        "experiment_name": experiment_name,
        "user_id":         user_id,
        "variant":         variant,
        "model_uri":       model_uri,
        "model_name":      config["model_name"],
    }


# ── Endpoint 4: record result ─────────────────────────────────────────────────

@router.post("/results", status_code=201)
async def record_result(req: RecordResultRequest) -> dict[str, Any]:
    """
    Record a metric observation for a user's experiment exposure.

    Callers should record results after the ML prediction is consumed
    (e.g. after the user completes a puzzle that used the assigned model).
    Results are aggregated by the ``/experiments/{name}/summary`` endpoint.
    """
    if req.variant not in ("control", "treatment"):
        raise HTTPException(
            status_code=422,
            detail="variant must be 'control' or 'treatment'",
        )

    conn = _db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO ab_test_result
                    (id, experiment_name, user_id, variant, metric_name, metric_value, recorded_at)
                VALUES (%s, %s, %s, %s, %s, %s, NOW())
                """,
                (
                    str(uuid.uuid4()),
                    req.experiment_name, req.user_id,
                    req.variant, req.metric_name, req.metric_value,
                ),
            )
        conn.commit()
    except psycopg2.errors.ForeignKeyViolation:
        conn.rollback()
        raise HTTPException(
            status_code=404,
            detail=f"Experiment '{req.experiment_name}' not found",
        )
    except Exception as exc:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(exc))
    finally:
        conn.close()

    return {"status": "recorded", "experiment_name": req.experiment_name, "variant": req.variant}


# ── Endpoint 5: experiment summary ────────────────────────────────────────────

@router.get("/experiments/{experiment_name}/summary")
async def experiment_summary(experiment_name: str) -> dict[str, Any]:
    """
    Aggregate results for an experiment, grouped by variant and metric.

    Returns mean, min, max, and sample count per (variant, metric_name).
    """
    conn = _db()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # Verify experiment exists
            cur.execute(
                "SELECT * FROM ab_test_config WHERE experiment_name = %s",
                (experiment_name,),
            )
            config = cur.fetchone()
            if config is None:
                raise HTTPException(
                    status_code=404,
                    detail=f"Experiment '{experiment_name}' not found",
                )

            cur.execute(
                """
                SELECT
                    variant,
                    metric_name,
                    COUNT(*)          AS n,
                    AVG(metric_value) AS mean,
                    MIN(metric_value) AS min,
                    MAX(metric_value) AS max,
                    STDDEV(metric_value) AS stddev
                FROM ab_test_result
                WHERE experiment_name = %s
                GROUP BY variant, metric_name
                ORDER BY variant, metric_name
                """,
                (experiment_name,),
            )
            rows = [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()

    return {
        "experiment_name": experiment_name,
        "status":          config["status"],
        "traffic_split":   config["traffic_split"],
        "results":         rows,
    }
