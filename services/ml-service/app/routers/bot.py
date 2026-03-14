"""
bot.py — RL Bot move endpoint.

POST /api/v1/bot/move
  Request:  BotMoveRequest
  Response: BotMoveResponse

Called by the multiplayer service (Go) each time the bot needs to make its
next move. The Go service tracks the bot's board state and passes it here.
The solution is passed so the service can validate the move is correct before
broadcasting it.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field, model_validator

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/bot", tags=["bot"])


# ─── Schemas ──────────────────────────────────────────────────────────────────

class BotMoveRequest(BaseModel):
    board: list[int] = Field(
        ...,
        description="Current bot board state — 81 ints, 0=empty, 1–9=filled",
    )
    solution: list[int] = Field(
        ...,
        description="Authoritative puzzle solution — 81 ints",
    )
    tier: str = Field(
        default="medium",
        description="Bot difficulty tier: easy | medium | hard",
    )

    @model_validator(mode="after")
    def validate_lengths(self) -> "BotMoveRequest":
        if len(self.board) != 81:
            raise ValueError("board must have exactly 81 elements")
        if len(self.solution) != 81:
            raise ValueError("solution must have exactly 81 elements")
        if self.tier not in ("easy", "medium", "hard"):
            raise ValueError("tier must be 'easy', 'medium', or 'hard'")
        for v in self.board:
            if not (0 <= v <= 9):
                raise ValueError("board values must be in range 0–9")
        for v in self.solution:
            if not (1 <= v <= 9):
                raise ValueError("solution values must be in range 1–9")
        return self


class BotMoveResponse(BaseModel):
    cell_index: int = Field(..., description="Cell to fill (0–80)")
    digit: int = Field(..., description="Digit to place (1–9)")
    confidence: float = Field(..., description="Model confidence (1.0 for rule-based fallback)")
    source: str = Field(..., description="'rl' if PPO model was used, 'fallback' otherwise")


# ─── Endpoint ─────────────────────────────────────────────────────────────────

@router.post(
    "/move",
    response_model=BotMoveResponse,
    summary="Get next bot move",
    description=(
        "Returns the bot's next cell fill. Uses a trained PPO model when available; "
        "falls back to a constraint-propagation solver."
    ),
)
async def get_bot_move(req: BotMoveRequest) -> BotMoveResponse:
    from app.services.bot_service import bot_service

    # Quick guard: if all cells are filled, there's nothing to do.
    empty_count = sum(1 for v in req.board if v == 0)
    if empty_count == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="All cells already filled — puzzle is complete",
        )

    try:
        result = bot_service.get_move(req.board, req.solution, req.tier)
    except Exception as exc:
        logger.exception("Bot move failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Bot move error: {exc}",
        ) from exc

    logger.debug(
        "bot_move tier=%s cell=%d digit=%d source=%s confidence=%.3f",
        req.tier,
        result["cell_index"],
        result["digit"],
        result["source"],
        result["confidence"],
    )
    return BotMoveResponse(**result)
