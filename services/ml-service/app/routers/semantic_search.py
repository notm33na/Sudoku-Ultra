"""
Semantic search router — puzzle and user embedding endpoints.

POST /api/v1/search/index/puzzle          — index or update a puzzle
POST /api/v1/search/index/user            — index or update a user's preference
POST /api/v1/search/puzzles/similar       — find puzzles similar to a given one
POST /api/v1/search/puzzles/for-user      — personalised puzzle recommendations
POST /api/v1/search/puzzles/by-technique  — puzzles that exercise a technique
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field, field_validator

router = APIRouter(prefix="/api/v1/search", tags=["semantic-search"])

_DIFFICULTIES = ("easy", "medium", "hard", "super_hard", "extreme",
                 "super_easy", "extreme")


# ── Shared sub-models ─────────────────────────────────────────────────────────

class PuzzleResult(BaseModel):
    puzzle_id: str
    difficulty: str
    clue_count: int
    techniques: list[str]
    source: str
    score: float


# ── Index puzzle ──────────────────────────────────────────────────────────────

class IndexPuzzleRequest(BaseModel):
    puzzle_id: str = Field(..., min_length=1)
    difficulty: str
    clue_count: int = Field(..., ge=17, le=81)
    techniques: list[str] = []
    avg_candidate_count: float | None = None
    backtrack_depth: int | None = None
    constraint_density: float | None = None
    symmetry_score: float | None = None
    source: str = "engine"


class IndexResponse(BaseModel):
    point_id: str
    message: str


@router.post("/index/puzzle", response_model=IndexResponse)
async def index_puzzle(req: IndexPuzzleRequest) -> IndexResponse:
    """Index or update a puzzle's embedding in Qdrant."""
    from app.services.semantic_search_service import index_puzzle as _index

    point_id = _index(
        puzzle_id=req.puzzle_id,
        difficulty=req.difficulty,
        clue_count=req.clue_count,
        techniques=req.techniques or None,
        avg_candidate_count=req.avg_candidate_count,
        backtrack_depth=req.backtrack_depth,
        constraint_density=req.constraint_density,
        symmetry_score=req.symmetry_score,
        source=req.source,
    )
    return IndexResponse(point_id=point_id, message="Puzzle indexed.")


# ── Index user ────────────────────────────────────────────────────────────────

class SessionRecord(BaseModel):
    difficulty: str
    time_elapsed_ms: int = Field(..., ge=0)
    hints_used: int = Field(0, ge=0)
    status: str = "completed"
    score: int = 0


class IndexUserRequest(BaseModel):
    user_id: str = Field(..., min_length=1)
    sessions: list[SessionRecord] = Field(..., min_length=1)


@router.post("/index/user", response_model=IndexResponse)
async def index_user(req: IndexUserRequest) -> IndexResponse:
    """Index or update a user's preference vector in Qdrant."""
    from app.services.semantic_search_service import index_user as _index

    sessions_dicts = [s.model_dump() for s in req.sessions]
    point_id = _index(user_id=req.user_id, sessions=sessions_dicts)
    return IndexResponse(point_id=point_id, message="User preference indexed.")


# ── Similar puzzles by puzzle_id ──────────────────────────────────────────────

class SimilarByIdRequest(BaseModel):
    puzzle_id: str = Field(..., min_length=1)
    top_k: int = Field(5, ge=1, le=20)
    difficulty_filter: str | None = None


class SearchResponse(BaseModel):
    results: list[dict[str, Any]]
    count: int


@router.post("/puzzles/similar", response_model=SearchResponse)
async def similar_puzzles(req: SimilarByIdRequest) -> SearchResponse:
    """Find puzzles semantically similar to the given puzzle_id."""
    from app.services.semantic_search_service import similar_puzzles as _search

    results = _search(
        puzzle_id=req.puzzle_id,
        top_k=req.top_k,
        difficulty_filter=req.difficulty_filter,
    )
    return SearchResponse(results=results, count=len(results))


# ── Similar puzzles by features (no stored puzzle needed) ────────────────────

class SimilarByFeaturesRequest(BaseModel):
    difficulty: str
    clue_count: int = Field(..., ge=17, le=81)
    techniques: list[str] = []
    top_k: int = Field(5, ge=1, le=20)


@router.post("/puzzles/similar-features", response_model=SearchResponse)
async def similar_by_features(req: SimilarByFeaturesRequest) -> SearchResponse:
    """Find puzzles matching a feature description (no existing puzzle required)."""
    from app.services.semantic_search_service import similar_puzzles_by_features

    results = similar_puzzles_by_features(
        difficulty=req.difficulty,
        clue_count=req.clue_count,
        techniques=req.techniques or None,
        top_k=req.top_k,
    )
    return SearchResponse(results=results, count=len(results))


# ── Personalised puzzles for user ─────────────────────────────────────────────

class ForUserRequest(BaseModel):
    user_id: str = Field(..., min_length=1)
    top_k: int = Field(5, ge=1, le=20)
    exclude_puzzle_ids: list[str] = []


@router.post("/puzzles/for-user", response_model=SearchResponse)
async def puzzles_for_user(req: ForUserRequest) -> SearchResponse:
    """Return personalised puzzle recommendations for a user."""
    from app.services.semantic_search_service import puzzles_for_user as _search

    results = _search(
        user_id=req.user_id,
        top_k=req.top_k,
        exclude_puzzle_ids=req.exclude_puzzle_ids or None,
    )
    return SearchResponse(results=results, count=len(results))


# ── Puzzles by technique ──────────────────────────────────────────────────────

class ByTechniqueRequest(BaseModel):
    technique_name: str = Field(..., min_length=1)
    top_k: int = Field(5, ge=1, le=20)
    difficulty_filter: str | None = None


@router.post("/puzzles/by-technique", response_model=SearchResponse)
async def by_technique(req: ByTechniqueRequest) -> SearchResponse:
    """Find puzzles that exercise a named technique."""
    from app.services.semantic_search_service import puzzles_by_technique as _search

    results = _search(
        technique_name=req.technique_name,
        top_k=req.top_k,
        difficulty_filter=req.difficulty_filter,
    )
    return SearchResponse(results=results, count=len(results))
