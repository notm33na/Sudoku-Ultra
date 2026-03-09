"""
Adaptive difficulty recommendation router.

Predicts the optimal next difficulty for a user based on
their gameplay history using Gradient Boosting Regression.
"""

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.services.recommender_service import recommender

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

    Uses Gradient Boosting Regressor trained on user gameplay features.
    Falls back to last_played_difficulty if model is not loaded.
    """
    # Extract features into flat dict for inference
    solve_times = features.avg_solve_time_per_difficulty
    feature_dict = {
        "avg_solve_time_easy": solve_times.get("easy", solve_times.get("super_easy", 120)),
        "avg_solve_time_medium": solve_times.get("medium", 300),
        "avg_solve_time_hard": solve_times.get("hard", solve_times.get("super_hard", 600)),
        "hint_rate": features.hint_rate,
        "error_rate": features.error_rate,
        "current_streak": features.current_streak,
        "session_count": features.session_count,
        "last_played_difficulty": features.last_played_difficulty,
        "win_rate": features.win_rate,
    }

    result = recommender.predict(feature_dict)

    return RecommendationResult(
        recommended_difficulty=result["recommended_difficulty"],
        confidence=result["confidence"],
        reasoning=result["reasoning"],
    )
