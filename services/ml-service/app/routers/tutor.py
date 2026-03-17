"""
Tutor router — 3 endpoints.

POST /api/v1/tutor/hint      → next logical hint
POST /api/v1/tutor/explain   → deep technique explanation
POST /api/v1/tutor/followup  → continue conversation
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Body, HTTPException
from pydantic import BaseModel, Field, field_validator

router = APIRouter(prefix="/api/v1/tutor", tags=["tutor"])


# ── Request / Response models ─────────────────────────────────────────────────

class BoardRequest(BaseModel):
    user_id: str = Field(..., description="Authenticated user ID")
    session_id: str | None = Field(None, description="Existing session; creates one if absent")
    board: list[int] = Field(..., description="81-cell board (0 = empty)")
    puzzle: list[int] = Field(..., description="Original puzzle (0 = empty clue cells)")

    @field_validator("board", "puzzle")
    @classmethod
    def validate_board(cls, v: list[int]) -> list[int]:
        if len(v) != 81:
            raise ValueError("board must have exactly 81 cells")
        if any(not (0 <= c <= 9) for c in v):
            raise ValueError("cell values must be 0–9")
        return v


class ExplainRequest(BaseModel):
    user_id: str
    session_id: str | None = None
    board: list[int]
    puzzle: list[int]
    technique_name: str = Field(..., min_length=1)

    @field_validator("board", "puzzle")
    @classmethod
    def validate_board(cls, v: list[int]) -> list[int]:
        if len(v) != 81:
            raise ValueError("board must have exactly 81 cells")
        return v


class FollowupRequest(BaseModel):
    user_id: str
    session_id: str
    board: list[int]
    puzzle: list[int]
    message: str = Field(..., min_length=1, max_length=1000)

    @field_validator("board", "puzzle")
    @classmethod
    def validate_board(cls, v: list[int]) -> list[int]:
        if len(v) != 81:
            raise ValueError("board must have exactly 81 cells")
        return v


class TutorResponse(BaseModel):
    session_id: str
    technique: str
    explanation: str
    highlight_cells: list[int]
    follow_up: str


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/hint", response_model=TutorResponse)
async def hint(req: BoardRequest):
    """Return the next logical hint for the current board state."""
    from app.services.tutor_service import get_hint, get_or_create_session

    session = get_or_create_session(
        user_id=req.user_id,
        board=req.board,
        puzzle=req.puzzle,
        session_id=req.session_id,
    )
    result = get_hint(session)
    return TutorResponse(session_id=session.session_id, **result)


@router.post("/explain", response_model=TutorResponse)
async def explain(req: ExplainRequest):
    """Deep explanation of a named Sudoku technique."""
    from app.services.tutor_service import explain_technique, get_or_create_session

    session = get_or_create_session(
        user_id=req.user_id,
        board=req.board,
        puzzle=req.puzzle,
        session_id=req.session_id,
    )
    result = explain_technique(session, req.technique_name)
    return TutorResponse(session_id=session.session_id, **result)


@router.post("/followup", response_model=TutorResponse)
async def followup(req: FollowupRequest):
    """Continue the tutoring conversation with a student follow-up message."""
    from app.services.tutor_service import get_or_create_session, process_followup
    from app.services.tutor_service import _sessions  # for session existence check

    if req.session_id not in _sessions:
        raise HTTPException(status_code=404, detail="Session not found or expired.")

    session = get_or_create_session(
        user_id=req.user_id,
        board=req.board,
        puzzle=req.puzzle,
        session_id=req.session_id,
    )
    result = process_followup(session, req.message)
    return TutorResponse(session_id=session.session_id, **result)
