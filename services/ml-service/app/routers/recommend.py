"""
Adaptive difficulty recommendation router.

Predicts the optimal next difficulty for a user based on
their gameplay history.

Fully implemented in Deliverable 3.
"""

from fastapi import APIRouter
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/v1", tags=["recommendation"])


class UserFeatures(BaseModel):
    """User gameplay features for difficulty prediction."""

    user_id: str = Field(..., description="User identifier")
    avg_solve_time_per_difficulty: dict[str, float] = Field(
        default_factory=dict, description="Avg solve time per difficulty in seconds"
    )
    hint_rate: float = Field(0.0, ge=0.0, le=1.0, description="Fraction of games where hints were used")
    error_rate: float = Field(0.0, ge=0.0, le=1.0, description="Fraction of games with errors")
    current_streak: int = Field(0, ge=0, description="Current daily streak")
    session_count: int = Field(0, ge=0, description="Total sessions played")
    last_played_difficulty: str = Field("easy", description="Most recent difficulty played")
    win_rate: float = Field(0.0, ge=0.0, le=1.0, description="Fraction of games completed successfully")


class RecommendationResult(BaseModel):
    """Difficulty recommendation response."""

    recommended_difficulty: str = Field(..., description="Recommended difficulty level")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Prediction confidence")
    reasoning: str = Field(..., description="Human-readable reasoning")


@router.post("/recommend-difficulty", response_model=RecommendationResult)
async def recommend_difficulty(features: UserFeatures) -> RecommendationResult:
    """
    Recommend optimal difficulty for a user.

    Fully implemented in Deliverable 3 — currently returns last played difficulty.
    """
    # D3: Gradient Boosting Regressor prediction
    return RecommendationResult(
        recommended_difficulty=features.last_played_difficulty,
        confidence=0.5,
        reasoning=f"Fallback: returning last played difficulty '{features.last_played_difficulty}'. "
        "ML model not yet loaded — will use Gradient Boosting in Deliverable 3.",
    )
