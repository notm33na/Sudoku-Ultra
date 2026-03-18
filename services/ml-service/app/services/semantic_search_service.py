"""
Semantic search service — Qdrant operations for puzzle and user collections.

Collections
-----------
puzzles          id = UUID5("puzzle.<puzzle_id>")  vector = 384-dim
user_preferences id = UUID5("user.<user_id>")      vector = 384-dim

All Qdrant calls are lazy-initialised on first use.
"""

from __future__ import annotations

import uuid
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.http.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PointStruct,
    VectorParams,
)

from app.config import settings
from app.logging import setup_logging
from app.ml.embeddings import embed_one
from app.ml.puzzle_embeddings import embed_puzzle, build_puzzle_text
from app.ml.user_embeddings import embed_user, aggregate_sessions

logger = setup_logging()

PUZZLE_COLLECTION = "puzzles"
USER_COLLECTION = "user_preferences"
VECTOR_SIZE = 384

# ── Qdrant client singleton ────────────────────────────────────────────────────

_client: QdrantClient | None = None


def _get_client() -> QdrantClient:
    global _client
    if _client is None:
        _client = QdrantClient(
            url=settings.QDRANT_URL,
            api_key=settings.QDRANT_API_KEY or None,
        )
    return _client


# ── Collection bootstrap ───────────────────────────────────────────────────────

def _ensure_collection(name: str) -> None:
    client = _get_client()
    existing = {c.name for c in client.get_collections().collections}
    if name not in existing:
        client.create_collection(
            collection_name=name,
            vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
        )
        logger.info(f"Created Qdrant collection: {name}")


def ensure_collections() -> None:
    _ensure_collection(PUZZLE_COLLECTION)
    _ensure_collection(USER_COLLECTION)


# ── ID helpers ─────────────────────────────────────────────────────────────────

def _puzzle_uid(puzzle_id: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, f"puzzle.{puzzle_id}"))


def _user_uid(user_id: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, f"user.{user_id}"))


# ── Puzzle indexing ────────────────────────────────────────────────────────────

def index_puzzle(
    puzzle_id: str,
    difficulty: str,
    clue_count: int,
    techniques: list[str] | None = None,
    avg_candidate_count: float | None = None,
    backtrack_depth: int | None = None,
    constraint_density: float | None = None,
    symmetry_score: float | None = None,
    source: str = "engine",
) -> str:
    """
    Embed and upsert a puzzle into the puzzles collection.
    Returns the Qdrant point ID (deterministic UUID).
    """
    _ensure_collection(PUZZLE_COLLECTION)
    vector = embed_puzzle(
        difficulty=difficulty,
        clue_count=clue_count,
        techniques=techniques,
        avg_candidate_count=avg_candidate_count,
        backtrack_depth=backtrack_depth,
        constraint_density=constraint_density,
        symmetry_score=symmetry_score,
        source=source,
    )
    point_id = _puzzle_uid(puzzle_id)
    payload: dict[str, Any] = {
        "puzzle_id": puzzle_id,
        "difficulty": difficulty,
        "clue_count": clue_count,
        "techniques": techniques or [],
        "source": source,
    }
    if avg_candidate_count is not None:
        payload["avg_candidate_count"] = avg_candidate_count
    if backtrack_depth is not None:
        payload["backtrack_depth"] = backtrack_depth

    _get_client().upsert(
        collection_name=PUZZLE_COLLECTION,
        points=[PointStruct(id=point_id, vector=vector, payload=payload)],
    )
    return point_id


# ── User preference indexing ───────────────────────────────────────────────────

def index_user(
    user_id: str,
    sessions: list[dict[str, Any]],
) -> str:
    """
    Aggregate session history and upsert user preference vector.
    Returns the Qdrant point ID.
    """
    _ensure_collection(USER_COLLECTION)
    profile = aggregate_sessions(sessions)
    vector = embed_user(user_id=user_id, **profile)
    point_id = _user_uid(user_id)
    _get_client().upsert(
        collection_name=USER_COLLECTION,
        points=[
            PointStruct(
                id=point_id,
                vector=vector,
                payload={"user_id": user_id, **profile},
            )
        ],
    )
    return point_id


# ── Search: similar puzzles by puzzle_id ──────────────────────────────────────

def similar_puzzles(
    puzzle_id: str,
    top_k: int = 5,
    difficulty_filter: str | None = None,
) -> list[dict[str, Any]]:
    """
    Find the top-k puzzles most similar to the given puzzle_id.
    Returns empty list if the puzzle is not indexed.
    """
    _ensure_collection(PUZZLE_COLLECTION)
    point_id = _puzzle_uid(puzzle_id)
    client = _get_client()

    try:
        points = client.retrieve(
            collection_name=PUZZLE_COLLECTION,
            ids=[point_id],
            with_vectors=True,
        )
    except Exception:
        return []

    if not points or not points[0].vector:
        return []

    query_vector = points[0].vector
    flt = (
        Filter(must=[FieldCondition(key="difficulty", match=MatchValue(value=difficulty_filter))])
        if difficulty_filter
        else None
    )

    results = client.search(
        collection_name=PUZZLE_COLLECTION,
        query_vector=query_vector,
        limit=top_k + 1,  # +1 because the query puzzle itself will be returned
        query_filter=flt,
        with_payload=True,
    )
    return [
        {**r.payload, "score": r.score}
        for r in results
        if r.payload.get("puzzle_id") != puzzle_id
    ][:top_k]


# ── Search: puzzles by feature description ────────────────────────────────────

def similar_puzzles_by_features(
    difficulty: str,
    clue_count: int,
    techniques: list[str] | None = None,
    top_k: int = 5,
) -> list[dict[str, Any]]:
    """Find puzzles similar to the given feature description (no stored puzzle needed)."""
    _ensure_collection(PUZZLE_COLLECTION)
    vector = embed_puzzle(difficulty=difficulty, clue_count=clue_count, techniques=techniques)
    results = _get_client().search(
        collection_name=PUZZLE_COLLECTION,
        query_vector=vector,
        limit=top_k,
        with_payload=True,
    )
    return [{**r.payload, "score": r.score} for r in results]


# ── Search: puzzles for a user ────────────────────────────────────────────────

def puzzles_for_user(
    user_id: str,
    top_k: int = 5,
    exclude_puzzle_ids: list[str] | None = None,
) -> list[dict[str, Any]]:
    """
    Cross-collection search: use the user's preference vector to find
    similar puzzles in the puzzles collection.
    """
    _ensure_collection(PUZZLE_COLLECTION)
    _ensure_collection(USER_COLLECTION)
    client = _get_client()

    point_id = _user_uid(user_id)
    try:
        user_points = client.retrieve(
            collection_name=USER_COLLECTION,
            ids=[point_id],
            with_vectors=True,
        )
    except Exception:
        return []

    if not user_points or not user_points[0].vector:
        return []

    results = client.search(
        collection_name=PUZZLE_COLLECTION,
        query_vector=user_points[0].vector,
        limit=top_k + len(exclude_puzzle_ids or []),
        with_payload=True,
    )
    excluded = set(exclude_puzzle_ids or [])
    return [
        {**r.payload, "score": r.score}
        for r in results
        if r.payload.get("puzzle_id") not in excluded
    ][:top_k]


# ── Search: puzzles by technique ─────────────────────────────────────────────

def puzzles_by_technique(
    technique_name: str,
    top_k: int = 5,
    difficulty_filter: str | None = None,
) -> list[dict[str, Any]]:
    """
    Find puzzles that exercise a specific technique via semantic search
    on technique-aware puzzle descriptions.
    """
    _ensure_collection(PUZZLE_COLLECTION)
    # Embed a query describing the desired technique
    query_text = (
        f"Sudoku puzzle that requires the {technique_name} technique. "
        f"Techniques required: {technique_name}."
    )
    vector = embed_one(query_text)
    flt = (
        Filter(must=[FieldCondition(key="difficulty", match=MatchValue(value=difficulty_filter))])
        if difficulty_filter
        else None
    )
    results = _get_client().search(
        collection_name=PUZZLE_COLLECTION,
        query_vector=vector,
        limit=top_k,
        query_filter=flt,
        with_payload=True,
    )
    return [{**r.payload, "score": r.score} for r in results]
