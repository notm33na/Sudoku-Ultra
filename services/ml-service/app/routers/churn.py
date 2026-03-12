"""
Churn prediction router.

Receives user engagement features and returns churn risk prediction
using Logistic Regression. Falls back to heuristic if model is not loaded.
"""

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.services.churn_service import churn_predictor

router = APIRouter(prefix="/api/v1", tags=["churn"])


# ─── Request / Response Schemas ────────────────────────────────────────────────


class ChurnFeatures(BaseModel):
    """User engagement features for churn prediction."""

    user_id: str = Field(..., description="User identifier")
    days_since_last_play: int = Field(0, ge=0, description="Days since last session")
    session_frequency: float = Field(3.0, ge=0.0, description="Sessions per week")
    avg_session_duration: float = Field(20.0, ge=0.0, description="Average session in minutes")
    total_games_played: int = Field(0, ge=0, description="Lifetime games completed")
    win_rate_trend: float = Field(0.0, ge=-1.0, le=1.0, description="Win rate change (positive=improving)")
    hint_usage_trend: float = Field(0.0, ge=-1.0, le=1.0, description="Hint usage change (positive=more hints)")
    difficulty_variety: int = Field(1, ge=1, le=6, description="Distinct difficulties played")
    completion_rate: float = Field(0.7, ge=0.0, le=1.0, description="Fraction of started games completed")
    error_rate_trend: float = Field(0.0, ge=-1.0, le=1.0, description="Error rate change (positive=more errors)")
    longest_streak: int = Field(0, ge=0, description="Longest ever daily streak")


class ChurnPrediction(BaseModel):
    """Churn risk prediction response."""

    churn_risk: bool = Field(..., description="Whether user is predicted to churn")
    probability: float = Field(..., ge=0.0, le=1.0, description="Churn probability")
    risk_level: str = Field(..., description="Risk level: low, medium, high, or critical")
    reasoning: str = Field(..., description="Human-readable reasoning")


# ─── Endpoint ──────────────────────────────────────────────────────────────────


@router.post("/predict-churn", response_model=ChurnPrediction)
async def predict_churn(features: ChurnFeatures) -> ChurnPrediction:
    """
    Predict churn risk for a user based on engagement features.

    Uses Logistic Regression trained on player engagement data.
    Falls back to heuristic-based prediction if model is not loaded.
    """
    feature_dict = features.model_dump(exclude={"user_id"})
    result = churn_predictor.predict(feature_dict)

    return ChurnPrediction(
        churn_risk=result["churn_risk"],
        probability=result["probability"],
        risk_level=result["risk_level"],
        reasoning=result["reasoning"],
    )
