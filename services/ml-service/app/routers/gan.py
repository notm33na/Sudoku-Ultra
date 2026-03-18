"""
GAN puzzle generation router.

POST /api/v1/gan/generate   — generate one puzzle
POST /api/v1/gan/batch      — generate 1-10 puzzles
GET  /api/v1/gan/status     — model load status
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field, field_validator

router = APIRouter(prefix="/api/v1/gan", tags=["gan"])

_DIFFICULTIES = Literal["easy", "medium", "hard", "super_hard", "extreme"]
_MODES = Literal["solution", "puzzle", "constrained"]


# ── Request / Response models ─────────────────────────────────────────────────

class GenerateRequest(BaseModel):
    mode: _MODES = "puzzle"
    difficulty: _DIFFICULTIES = "medium"
    symmetric: bool = False


class BatchRequest(BaseModel):
    mode: _MODES = "puzzle"
    difficulty: _DIFFICULTIES = "medium"
    count: int = Field(1, ge=1, le=10)
    symmetric: bool = False


class PuzzleResult(BaseModel):
    solution: list[int] = Field(..., description="81-cell complete solution")
    puzzle: list[int] | None = Field(None, description="81-cell puzzle (0=empty), null for solution mode")
    difficulty: str
    clue_count: int
    source: str = Field(..., description="'gan' or 'backtracking'")
    valid: bool


class GenerateResponse(BaseModel):
    puzzle: PuzzleResult


class BatchResponse(BaseModel):
    puzzles: list[PuzzleResult]
    count: int


class StatusResponse(BaseModel):
    loaded: bool
    model_path: str
    fallback: str | None


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/generate", response_model=GenerateResponse)
async def generate(req: GenerateRequest) -> GenerateResponse:
    """Generate a single puzzle. Falls back to backtracking if GAN not loaded."""
    from app.services.gan_service import gan_service

    results = gan_service.generate(
        mode=req.mode,
        difficulty=req.difficulty,
        count=1,
        symmetric=req.symmetric,
    )
    return GenerateResponse(puzzle=PuzzleResult(**results[0]))


@router.post("/batch", response_model=BatchResponse)
async def batch(req: BatchRequest) -> BatchResponse:
    """Generate 1-10 puzzles in one request."""
    from app.services.gan_service import gan_service

    results = gan_service.generate(
        mode=req.mode,
        difficulty=req.difficulty,
        count=req.count,
        symmetric=req.symmetric,
    )
    return BatchResponse(
        puzzles=[PuzzleResult(**r) for r in results],
        count=len(results),
    )


@router.get("/status", response_model=StatusResponse)
async def status() -> StatusResponse:
    """Return GAN model load status."""
    from app.services.gan_service import gan_service

    return StatusResponse(**gan_service.status())
