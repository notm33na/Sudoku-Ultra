"""
XAI router — cell-level difficulty explanation.

POST /api/v1/xai/cell-importance
  Returns per-cell importance scores derived from SHAP values of the
  difficulty classifier, plus the top cells driving the rating.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field, field_validator

router = APIRouter(prefix="/api/v1/xai", tags=["xai"])


# ── Request / Response models ─────────────────────────────────────────────────

class XAIRequest(BaseModel):
    board: list[int] = Field(..., description="81-cell board state (0 = empty)")
    puzzle: list[int] = Field(..., description="Original puzzle (0 = empty clue cells)")

    @field_validator("board", "puzzle")
    @classmethod
    def validate_board(cls, v: list[int]) -> list[int]:
        if len(v) != 81:
            raise ValueError("board must have exactly 81 cells")
        if any(not (0 <= c <= 9) for c in v):
            raise ValueError("cell values must be 0–9")
        return v


class XAIResponse(BaseModel):
    cell_importances: list[float] = Field(
        ..., description="81 importance scores, 0.0–1.0 (higher = more influential for difficulty)"
    )
    predicted_difficulty: str
    confidence: float = Field(..., ge=0.0, le=1.0)
    shap_values: dict[str, float] = Field(..., description="Per-feature SHAP values")
    top_cells: list[int] = Field(..., description="Indices of the most influential cells")
    explanation: str


# ── Endpoint ──────────────────────────────────────────────────────────────────

@router.post("/cell-importance", response_model=XAIResponse)
async def cell_importance(req: XAIRequest) -> XAIResponse:
    """
    Explain which cells most influence the predicted difficulty rating.

    Uses SHAP TreeExplainer on the Random Forest classifier (or rule-based
    fallback) and maps feature-level attributions back to individual cells.
    """
    from app.ml.xai import explain_board

    result = explain_board(req.board, req.puzzle)
    return XAIResponse(**result)
