"""
Onboarding narration router.

POST /api/v1/onboarding/narrate
  Accepts current step metadata and returns a short LLM-generated tip.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/v1/onboarding", tags=["onboarding"])


class NarrateRequest(BaseModel):
    step_index: int = Field(..., ge=0, le=8, description="0-based step index (0–8)")
    step_title: str = Field(..., min_length=1, max_length=120)
    step_content: str = Field(..., min_length=1, max_length=800)


class NarrateResponse(BaseModel):
    tip: str
    step_index: int


@router.post("/narrate", response_model=NarrateResponse)
async def narrate(req: NarrateRequest) -> NarrateResponse:
    """Return an LLM-generated (or static fallback) tip for an onboarding step."""
    from app.services.onboarding_service import get_narration

    tip = get_narration(req.step_index, req.step_title, req.step_content)
    return NarrateResponse(tip=tip, step_index=req.step_index)
