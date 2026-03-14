"""
anomaly.py — Anti-cheat anomaly detection router.

Routes:
  POST /api/v1/anomaly/score   — score a completed game session
"""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator

from app.services.anomaly_service import anomaly_service

router = APIRouter(prefix="/api/v1/anomaly", tags=["anomaly"])

# ── Request / Response models ─────────────────────────────────────────────────


class AnomalyScoreRequest(BaseModel):
    session_id: str = Field(..., description="Game session UUID")
    user_id: str = Field(..., description="User UUID")
    difficulty: str = Field(..., description="Puzzle difficulty")
    time_elapsed_ms: int = Field(..., ge=0, description="Total session time in ms")
    cells_filled: int = Field(..., ge=0, le=81, description="Correctly filled cells")
    errors_count: int = Field(..., ge=0, description="Wrong cell entries")
    hints_used: int = Field(..., ge=0, description="Hints requested")
    cells_to_fill: Optional[int] = Field(
        None, ge=1, le=81, description="Expected empty cells (inferred if omitted)"
    )
    cell_fill_times_ms: Optional[List[int]] = Field(
        None,
        description="Per-cell fill times in ms (optional, improves accuracy)",
        max_length=81,
    )

    @field_validator("difficulty")
    @classmethod
    def validate_difficulty(cls, v: str) -> str:
        valid = {"super_easy", "beginner", "easy", "medium", "hard", "expert", "evil"}
        if v not in valid:
            raise ValueError(f"difficulty must be one of {sorted(valid)}")
        return v

    @field_validator("time_elapsed_ms")
    @classmethod
    def validate_time(cls, v: int) -> int:
        if v < 1_000:
            raise ValueError("time_elapsed_ms must be at least 1 000 ms")
        return v


class AnomalyScoreResponse(BaseModel):
    session_id: str
    user_id: str
    anomaly_score: float = Field(..., description="Normalised score; > 1.0 = anomalous")
    reconstruction_error: float
    threshold: float
    is_anomalous: bool


# ── Endpoint ──────────────────────────────────────────────────────────────────


@router.post("/score", response_model=AnomalyScoreResponse)
def score_session(req: AnomalyScoreRequest) -> AnomalyScoreResponse:
    """
    Score a completed game session for anomalous (cheat-like) behaviour.

    The response `is_anomalous` flag is `true` when the reconstruction error
    from the autoencoder exceeds the training threshold (mean + 2σ).
    """
    result = anomaly_service.score(
        time_elapsed_ms=req.time_elapsed_ms,
        cells_filled=req.cells_filled,
        errors_count=req.errors_count,
        hints_used=req.hints_used,
        difficulty=req.difficulty,
        cells_to_fill=req.cells_to_fill,
        cell_fill_times_ms=req.cell_fill_times_ms,
    )

    return AnomalyScoreResponse(
        session_id=req.session_id,
        user_id=req.user_id,
        **result,
    )
