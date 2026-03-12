"""
Player skill clustering router.

Assigns users to skill tiers: Beginner, Casual, Intermediate, Advanced, Expert.
"""

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.services.clustering_service import skill_clustering_service

router = APIRouter(prefix="/api/v1", tags=["clustering"])


class SkillFeatures(BaseModel):
    """User skill features for cluster assignment."""

    user_id: str = Field(..., description="User identifier")
    avg_solve_time_easy: float = Field(120.0, ge=0.0, description="Avg solve time for easy puzzles (seconds)")
    avg_solve_time_medium: float = Field(300.0, ge=0.0, description="Avg solve time for medium puzzles")
    avg_solve_time_hard: float = Field(600.0, ge=0.0, description="Avg solve time for hard puzzles")
    hint_rate: float = Field(0.2, ge=0.0, le=1.0, description="Fraction of games with hints used")
    error_rate: float = Field(0.15, ge=0.0, le=1.0, description="Fraction of games with errors")
    difficulty_preference_mode: int = Field(2, ge=0, le=5, description="Most played difficulty (0–5)")
    session_length_avg: float = Field(20.0, ge=0.0, description="Average session length (minutes)")
    days_active_last_30: int = Field(10, ge=0, le=30, description="Days active in last 30")


class ClusterResult(BaseModel):
    """Skill cluster assignment response."""

    cluster: str = Field(..., description="Skill tier label")
    cluster_id: int = Field(..., ge=0, description="Cluster ID")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Assignment confidence")
    reasoning: str = Field(..., description="Human-readable reasoning")


@router.post("/skill-cluster", response_model=ClusterResult)
async def assign_skill_cluster(features: SkillFeatures) -> ClusterResult:
    """Assign a user to a skill cluster based on gameplay features."""
    feature_dict = features.model_dump(exclude={"user_id"})
    result = skill_clustering_service.predict(feature_dict)

    return ClusterResult(
        cluster=result["cluster"],
        cluster_id=result["cluster_id"],
        confidence=result["confidence"],
        reasoning=result["reasoning"],
    )
