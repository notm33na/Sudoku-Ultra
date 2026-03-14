"""
moderate.py — Chat moderation endpoint.

POST /api/v1/moderate
  Request:  ModerationRequest  { text: str }
  Response: ModerationResponse { is_toxic: bool, confidence: float, category: str }

Called by the multiplayer service (Go) before relaying any chat message.
The Go service is responsible for warning / muting logic; this endpoint
only classifies text.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["moderation"])


# ─── Schemas ──────────────────────────────────────────────────────────────────

class ModerationRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=2000, description="Chat message text to classify")

    @field_validator("text")
    @classmethod
    def strip_text(cls, v: str) -> str:
        return v.strip()


class ModerationResponse(BaseModel):
    is_toxic: bool = Field(..., description="True if the message violates community guidelines")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Model confidence (0–1)")
    category: str = Field(
        ...,
        description="clean | toxic | severe_toxic | obscene | threat | insult | identity_hate",
    )


# ─── Endpoint ─────────────────────────────────────────────────────────────────

@router.post(
    "/moderate",
    response_model=ModerationResponse,
    summary="Classify a chat message for toxicity",
    description=(
        "Returns toxicity classification using a fine-tuned DistilBERT model. "
        "Falls back to `unitary/toxic-bert` then to a keyword filter if the model is unavailable."
    ),
)
async def moderate_message(req: ModerationRequest) -> ModerationResponse:
    from app.services.toxicity_service import toxicity_service

    try:
        result = toxicity_service.predict(req.text)
    except Exception as exc:
        logger.exception("Toxicity prediction error")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Moderation error: {exc}",
        ) from exc

    logger.debug(
        "moderate text=%r is_toxic=%s confidence=%.3f category=%s",
        req.text[:50],
        result["is_toxic"],
        result["confidence"],
        result["category"],
    )
    return ModerationResponse(**result)
