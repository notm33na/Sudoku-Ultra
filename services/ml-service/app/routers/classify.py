"""
Difficulty classification router.

Receives puzzle features and returns ML-predicted difficulty
with SHAP-based explanations.

Fully implemented in Deliverable 2.
"""

from fastapi import APIRouter
from pydantic import BaseModel, Field

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

    Fully implemented in Deliverable 2 — currently returns rule-based fallback.
    """
    # Rule-based fallback (replaced by ML model in D2)
    clue_count = features.clue_count
    if clue_count >= 45:
        difficulty = "super_easy"
    elif clue_count >= 36:
        difficulty = "easy"
    elif clue_count >= 30:
        difficulty = "medium"
    elif clue_count >= 26:
        difficulty = "hard"
    elif clue_count >= 22:
        difficulty = "super_hard"
    else:
        difficulty = "extreme"

    return ClassificationResult(
        difficulty=difficulty,
        confidence=0.5,  # Low confidence — rule-based fallback
        shap_values={
            "clue_count": 0.3,
            "naked_singles": 0.15,
            "hidden_singles": 0.1,
            "naked_pairs": 0.05,
            "pointing_pairs": 0.03,
            "box_line_reduction": 0.02,
            "backtrack_depth": 0.15,
            "constraint_density": 0.1,
            "symmetry_score": 0.02,
            "avg_candidate_count": 0.08,
        },
        explanation=f"Rule-based fallback: {clue_count} clues → {difficulty}. "
        "ML model not yet loaded — will use Random Forest + SHAP in Deliverable 2.",
    )
