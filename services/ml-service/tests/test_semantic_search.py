"""
Tests for D6 — Embeddings & Semantic Search.

Coverage:
- Puzzle text builder correctness
- Puzzle embedding dimensions + normalisation
- User text builder correctness
- User embedding dimensions
- aggregate_sessions aggregation logic
- Qdrant service methods (Qdrant mocked)
- All 6 FastAPI endpoints: index/puzzle, index/user, similar, similar-features, for-user, by-technique
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


# ── Fixtures ──────────────────────────────────────────────────────────────────

SESSIONS = [
    {"difficulty": "hard", "time_elapsed_ms": 480_000, "hints_used": 1, "status": "completed", "score": 800},
    {"difficulty": "hard", "time_elapsed_ms": 420_000, "hints_used": 0, "status": "completed", "score": 900},
    {"difficulty": "medium", "time_elapsed_ms": 250_000, "hints_used": 2, "status": "completed", "score": 700},
    {"difficulty": "hard", "time_elapsed_ms": 390_000, "hints_used": 0, "status": "completed", "score": 950},
    {"difficulty": "super_hard", "time_elapsed_ms": 720_000, "hints_used": 3, "status": "completed", "score": 600},
    {"difficulty": "hard", "time_elapsed_ms": 360_000, "hints_used": 0, "status": "completed", "score": 980},
]


# ── Puzzle text builder tests ─────────────────────────────────────────────────

def test_puzzle_text_contains_difficulty():
    from app.ml.puzzle_embeddings import build_puzzle_text
    text = build_puzzle_text("hard", 24)
    assert "hard" in text
    assert "24" in text


def test_puzzle_text_includes_techniques():
    from app.ml.puzzle_embeddings import build_puzzle_text
    text = build_puzzle_text("hard", 24, techniques=["x-wing", "pointing-pairs"])
    assert "x-wing" in text
    assert "pointing-pairs" in text


def test_puzzle_text_no_techniques():
    from app.ml.puzzle_embeddings import build_puzzle_text
    text = build_puzzle_text("easy", 40)
    assert "techniques" not in text


def test_puzzle_text_all_fields():
    from app.ml.puzzle_embeddings import build_puzzle_text
    text = build_puzzle_text(
        "extreme", 15,
        techniques=["aic"],
        avg_candidate_count=2.1,
        backtrack_depth=5,
        constraint_density=0.9,
        symmetry_score=0.0,
        source="gan",
    )
    assert "aic" in text
    assert "2.1" in text
    assert "gan" in text


# ── Puzzle embedding tests ────────────────────────────────────────────────────

def test_embed_puzzle_dimension():
    from app.ml.puzzle_embeddings import embed_puzzle
    vec = embed_puzzle("medium", 30)
    assert len(vec) == 384


def test_embed_puzzle_normalised():
    import math
    from app.ml.puzzle_embeddings import embed_puzzle
    vec = embed_puzzle("medium", 30)
    norm = math.sqrt(sum(x * x for x in vec))
    assert abs(norm - 1.0) < 1e-4


def test_embed_puzzle_different_difficulties_differ():
    from app.ml.puzzle_embeddings import embed_puzzle
    v_easy = embed_puzzle("easy", 40)
    v_hard = embed_puzzle("hard", 22)
    dot = sum(a * b for a, b in zip(v_easy, v_hard))
    assert dot < 0.99, "Easy and hard embeddings should not be identical"


def test_embed_puzzle_from_features():
    from app.ml.puzzle_embeddings import embed_puzzle_from_features
    features = {
        "clue_count": 28.0, "avg_candidate_count": 3.5,
        "backtrack_depth": 1.0, "constraint_density": 0.75,
        "symmetry_score": 0.5,
    }
    vec = embed_puzzle_from_features(features, "medium")
    assert len(vec) == 384


# ── User text builder tests ───────────────────────────────────────────────────

def test_user_text_contains_skill():
    from app.ml.user_embeddings import build_user_text
    text = build_user_text(
        user_id="u1", skill_level="advanced",
        preferred_difficulty="hard", session_count=20,
    )
    assert "advanced" in text
    assert "hard" in text


def test_user_text_with_hints():
    from app.ml.user_embeddings import build_user_text
    text = build_user_text(
        user_id="u1", skill_level="beginner",
        preferred_difficulty="easy", session_count=5,
        hint_usage_rate=0.8,
    )
    assert "0.8" in text or "0.80" in text


# ── User embedding tests ──────────────────────────────────────────────────────

def test_embed_user_dimension():
    from app.ml.user_embeddings import embed_user
    vec = embed_user("u1", "advanced", "hard", 20)
    assert len(vec) == 384


# ── Session aggregation tests ─────────────────────────────────────────────────

def test_aggregate_sessions_preferred_difficulty():
    from app.ml.user_embeddings import aggregate_sessions
    profile = aggregate_sessions(SESSIONS)
    assert profile["preferred_difficulty"] == "hard"


def test_aggregate_sessions_session_count():
    from app.ml.user_embeddings import aggregate_sessions
    profile = aggregate_sessions(SESSIONS)
    assert profile["session_count"] == len(SESSIONS)


def test_aggregate_sessions_hint_rate():
    from app.ml.user_embeddings import aggregate_sessions
    profile = aggregate_sessions(SESSIONS)
    expected_rate = (1 + 0 + 2 + 0 + 3 + 0) / len(SESSIONS)
    assert abs(profile["hint_usage_rate"] - expected_rate) < 0.01


def test_aggregate_sessions_skill_level():
    from app.ml.user_embeddings import aggregate_sessions
    profile = aggregate_sessions(SESSIONS)
    # hard preferred + low hint rate → advanced
    assert profile["skill_level"] in {"advanced", "expert"}


def test_aggregate_sessions_empty():
    from app.ml.user_embeddings import aggregate_sessions
    profile = aggregate_sessions([])
    assert profile["skill_level"] == "beginner"
    assert profile["session_count"] == 0


def test_aggregate_sessions_improvement_trend():
    from app.ml.user_embeddings import aggregate_sessions
    # Decreasing solve times → improving
    sessions = [
        {"difficulty": "hard", "time_elapsed_ms": 600_000 - i * 50_000,
         "hints_used": 0, "status": "completed", "score": 800}
        for i in range(8)
    ]
    profile = aggregate_sessions(sessions)
    assert profile["improvement_trend"] == "improving"


# ── Semantic search service tests (Qdrant mocked) ────────────────────────────

def _make_mock_hit(puzzle_id: str, difficulty: str, score: float = 0.9):
    hit = MagicMock()
    hit.score = score
    hit.payload = {
        "puzzle_id": puzzle_id, "difficulty": difficulty,
        "clue_count": 28, "techniques": [], "source": "engine",
    }
    return hit


def test_index_puzzle_calls_upsert():
    mock_client = MagicMock()
    with patch("app.services.semantic_search_service._get_client", return_value=mock_client), \
         patch("app.services.semantic_search_service._ensure_collection"), \
         patch("app.ml.puzzle_embeddings.embed_puzzle", return_value=[0.1] * 384):
        from app.services.semantic_search_service import index_puzzle
        point_id = index_puzzle("puzzle-1", "hard", 24)
        mock_client.upsert.assert_called_once()
        assert isinstance(point_id, str)


def test_similar_puzzles_empty_when_not_indexed():
    mock_client = MagicMock()
    mock_client.retrieve.return_value = []
    with patch("app.services.semantic_search_service._get_client", return_value=mock_client), \
         patch("app.services.semantic_search_service._ensure_collection"):
        from app.services.semantic_search_service import similar_puzzles
        results = similar_puzzles("nonexistent-puzzle")
        assert results == []


def test_similar_puzzles_filters_self():
    mock_client = MagicMock()
    # Return the query puzzle itself + one other
    mock_point = MagicMock()
    mock_point.vector = [0.1] * 384
    mock_client.retrieve.return_value = [mock_point]
    mock_client.search.return_value = [
        _make_mock_hit("query-puzzle", "hard", 1.0),  # self — should be filtered
        _make_mock_hit("other-puzzle", "hard", 0.85),
    ]
    with patch("app.services.semantic_search_service._get_client", return_value=mock_client), \
         patch("app.services.semantic_search_service._ensure_collection"):
        from app.services.semantic_search_service import similar_puzzles
        results = similar_puzzles("query-puzzle", top_k=5)
        ids = [r["puzzle_id"] for r in results]
        assert "query-puzzle" not in ids
        assert "other-puzzle" in ids


def test_puzzles_by_technique():
    mock_client = MagicMock()
    mock_client.search.return_value = [_make_mock_hit("p1", "hard", 0.8)]
    with patch("app.services.semantic_search_service._get_client", return_value=mock_client), \
         patch("app.services.semantic_search_service._ensure_collection"), \
         patch("app.ml.embeddings.embed_one", return_value=[0.1] * 384):
        from app.services.semantic_search_service import puzzles_by_technique
        results = puzzles_by_technique("x-wing", top_k=1)
        assert len(results) == 1
        assert results[0]["puzzle_id"] == "p1"


# ── FastAPI endpoint tests ────────────────────────────────────────────────────

@pytest.fixture
def client():
    from app.main import create_app
    return TestClient(create_app())


def test_index_puzzle_endpoint(client):
    with patch("app.services.semantic_search_service._get_client") as mock_get, \
         patch("app.services.semantic_search_service._ensure_collection"), \
         patch("app.ml.puzzle_embeddings.embed_puzzle", return_value=[0.1] * 384):
        mock_client = MagicMock()
        mock_get.return_value = mock_client
        resp = client.post("/api/v1/search/index/puzzle", json={
            "puzzle_id": "abc-123",
            "difficulty": "hard",
            "clue_count": 24,
            "techniques": ["x-wing"],
        })
    assert resp.status_code == 200
    assert "point_id" in resp.json()


def test_index_user_endpoint(client):
    with patch("app.services.semantic_search_service._get_client") as mock_get, \
         patch("app.services.semantic_search_service._ensure_collection"), \
         patch("app.ml.user_embeddings.embed_user", return_value=[0.1] * 384):
        mock_client = MagicMock()
        mock_get.return_value = mock_client
        resp = client.post("/api/v1/search/index/user", json={
            "user_id": "user-1",
            "sessions": [s for s in SESSIONS],
        })
    assert resp.status_code == 200
    assert resp.json()["message"] == "User preference indexed."


def test_similar_endpoint_empty_result(client):
    with patch("app.services.semantic_search_service._get_client") as mock_get, \
         patch("app.services.semantic_search_service._ensure_collection"):
        mock_client = MagicMock()
        mock_client.retrieve.return_value = []
        mock_get.return_value = mock_client
        resp = client.post("/api/v1/search/puzzles/similar", json={"puzzle_id": "nonexistent"})
    assert resp.status_code == 200
    assert resp.json()["count"] == 0


def test_similar_features_endpoint(client):
    with patch("app.services.semantic_search_service._get_client") as mock_get, \
         patch("app.services.semantic_search_service._ensure_collection"), \
         patch("app.ml.puzzle_embeddings.embed_puzzle", return_value=[0.1] * 384):
        mock_client = MagicMock()
        mock_client.search.return_value = [_make_mock_hit("p1", "medium")]
        mock_get.return_value = mock_client
        resp = client.post("/api/v1/search/puzzles/similar-features", json={
            "difficulty": "medium",
            "clue_count": 30,
            "techniques": ["naked-pairs"],
        })
    assert resp.status_code == 200
    assert resp.json()["count"] == 1


def test_for_user_endpoint_user_not_indexed(client):
    with patch("app.services.semantic_search_service._get_client") as mock_get, \
         patch("app.services.semantic_search_service._ensure_collection"):
        mock_client = MagicMock()
        mock_client.retrieve.return_value = []
        mock_get.return_value = mock_client
        resp = client.post("/api/v1/search/puzzles/for-user", json={"user_id": "unknown-user"})
    assert resp.status_code == 200
    assert resp.json()["count"] == 0


def test_by_technique_endpoint(client):
    with patch("app.services.semantic_search_service._get_client") as mock_get, \
         patch("app.services.semantic_search_service._ensure_collection"), \
         patch("app.ml.embeddings.embed_one", return_value=[0.1] * 384):
        mock_client = MagicMock()
        mock_client.search.return_value = [_make_mock_hit("p1", "hard")]
        mock_get.return_value = mock_client
        resp = client.post("/api/v1/search/puzzles/by-technique", json={
            "technique_name": "x-wing",
            "top_k": 3,
        })
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 1
    assert data["results"][0]["puzzle_id"] == "p1"


def test_by_technique_with_difficulty_filter(client):
    with patch("app.services.semantic_search_service._get_client") as mock_get, \
         patch("app.services.semantic_search_service._ensure_collection"), \
         patch("app.ml.embeddings.embed_one", return_value=[0.1] * 384):
        mock_client = MagicMock()
        mock_client.search.return_value = []
        mock_get.return_value = mock_client
        resp = client.post("/api/v1/search/puzzles/by-technique", json={
            "technique_name": "swordfish",
            "top_k": 5,
            "difficulty_filter": "expert",
        })
    assert resp.status_code == 200
    # Should still call search (even with empty result) without error
    mock_client.search.assert_called_once()
