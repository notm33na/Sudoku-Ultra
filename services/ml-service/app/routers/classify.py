"""
Difficulty classification router.

Receives puzzle features and returns ML-predicted difficulty
with SHAP-based explanations. Falls back to rule-based if model
is not loaded.
"""

import time

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.services.classifier_service import classifier
from app.services.monitoring_service import monitoring_service

router = APIRouter(prefix="/api/v1", tags=["classification"])


# ─── Request / Response Schemas ────────────────────────────────────────────────


class PuzzleFeatures(BaseModel):
    """Input features for difficulty classification."""

    clue_count: int = Field(..., ge=17, le=80, description="Number of given clues")
    naked_singles: int = Field(..., ge=0, description="Cells solvable by naked singles")
    hidden_singles: int = Field(..., ge=0, description="Cells solvable by hidden singles")
    naked_pairs: int = Field(0, ge=0, description="Naked pair eliminations found")
    pointing_pairs: int = Field(0, ge=0, description="Pointing pair eliminations found")
    box_line_reduction: int = Field(0, ge=0, description="Box-line reduction eliminations")
    backtrack_depth: int = Field(0, ge=0, description="Max backtracking depth required")
    constraint_density: float = Field(..., ge=0.0, le=1.0, description="Average constraint density")
    symmetry_score: float = Field(0.0, ge=0.0, le=1.0, description="Puzzle symmetry score")
    avg_candidate_count: float = Field(..., ge=0.0, description="Average candidate count per empty cell")


class ClassificationResult(BaseModel):
    """Difficulty classification response with explainability."""

    difficulty: str = Field(..., description="Predicted difficulty class")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Prediction confidence")
    shap_values: dict[str, float] = Field(..., description="SHAP feature importance values")
    explanation: str = Field(..., description="Human-readable explanation of classification")


# ─── Endpoint ──────────────────────────────────────────────────────────────────


@router.post("/classify", response_model=ClassificationResult)
async def classify_difficulty(features: PuzzleFeatures) -> ClassificationResult:
    """
    Classify puzzle difficulty using Random Forest + SHAP.

    If the ML model is loaded, returns ML prediction with SHAP explanation.
    Otherwise, falls back to rule-based classification.
    """
    t0 = time.monotonic()
    feature_dict = features.model_dump()
    result = classifier.predict(feature_dict)
    latency_ms = (time.monotonic() - t0) * 1000

    monitoring_service.record_prediction(
        model_name="difficulty-classifier",
        predicted=result["difficulty"],
        confidence=result["confidence"],
        latency_ms=latency_ms,
    )

    return ClassificationResult(
        difficulty=result["difficulty"],
        confidence=result["confidence"],
        shap_values=result["shap_values"],
        explanation=result["explanation"],
    )
