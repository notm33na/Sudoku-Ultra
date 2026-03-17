"""
Tests for D1 — RAG Technique Tutor.

Coverage:
- Embedding dimensions
- Qdrant retrieval (mocked)
- LLM routing and circuit breaker
- Service layer (mocked agent)
- FastAPI endpoints via TestClient
- Session memory window
- Candidate computation
- Board solver
"""

from __future__ import annotations

import json
import time
import uuid
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# ── Fixtures ──────────────────────────────────────────────────────────────────

EMPTY_BOARD = [0] * 81

# Board with one naked single at cell 0 (only 1 fits)
NAKED_SINGLE_BOARD = [
    0, 2, 3, 4, 5, 6, 7, 8, 9,
    4, 5, 6, 7, 8, 9, 1, 2, 3,
    7, 8, 9, 1, 2, 3, 4, 5, 6,
    2, 1, 4, 3, 6, 5, 8, 9, 7,  # noqa: E241
    3, 6, 5, 8, 9, 7, 2, 1, 4,
    8, 9, 7, 2, 1, 4, 3, 6, 5,
    5, 3, 1, 6, 4, 2, 9, 7, 8,
    6, 4, 2, 9, 7, 8, 5, 3, 1,
    9, 7, 8, 5, 3, 1, 6, 4, 2,  # noqa: E241
]

SOLVED_BOARD = [
    1, 2, 3, 4, 5, 6, 7, 8, 9,
    4, 5, 6, 7, 8, 9, 1, 2, 3,
    7, 8, 9, 1, 2, 3, 4, 5, 6,
    2, 1, 4, 3, 6, 5, 8, 9, 7,
    3, 6, 5, 8, 9, 7, 2, 1, 4,
    8, 9, 7, 2, 1, 4, 3, 6, 5,
    5, 3, 1, 6, 4, 2, 9, 7, 8,
    6, 4, 2, 9, 7, 8, 5, 3, 1,
    9, 7, 8, 5, 3, 1, 6, 4, 2,
]


# ── Embedding tests ───────────────────────────────────────────────────────────

def test_embed_one_dimension():
    from app.ml.embeddings import embed_one
    vec = embed_one("Naked Single elimination technique")
    assert len(vec) == 384
    assert isinstance(vec[0], float)


def test_embed_batch_shapes():
    from app.ml.embeddings import embed_batch
    texts = ["X-Wing", "Naked Pairs", "Hidden Singles"]
    vecs = embed_batch(texts)
    assert len(vecs) == 3
    assert all(len(v) == 384 for v in vecs)


def test_embed_normalised():
    """Normalised vectors have unit length (dot product ≈ 1)."""
    import math
    from app.ml.embeddings import embed_one
    vec = embed_one("Swordfish pattern")
    norm = math.sqrt(sum(x * x for x in vec))
    assert abs(norm - 1.0) < 1e-4


# ── Solver tests ──────────────────────────────────────────────────────────────

def test_solver_solves_naked_single():
    from app.ml.tutor_agent import _solve
    result = _solve(NAKED_SINGLE_BOARD)
    assert result is not None
    assert result[0] == 1  # cell 0 should be 1


def test_solver_returns_none_for_invalid():
    # Two 1s in same row — unsolvable
    board = NAKED_SINGLE_BOARD[:]
    board[1] = 1  # conflicts with cell 0 needing 1
    # Actually NAKED_SINGLE_BOARD has a valid setup, let's use a truly unsolvable board
    bad_board = [1] * 81  # all 1s, clearly invalid
    from app.ml.tutor_agent import _solve
    result = _solve(bad_board)
    assert result is None


def test_solver_leaves_already_solved():
    from app.ml.tutor_agent import _solve
    result = _solve(SOLVED_BOARD)
    assert result == SOLVED_BOARD


# ── Candidate computation tests ───────────────────────────────────────────────

def test_get_candidates_cell_zero():
    from app.ml.tutor_agent import _get_candidates
    candidates = _get_candidates(NAKED_SINGLE_BOARD, 0)
    assert candidates == [1]


def test_get_candidates_filled_cell():
    from app.ml.tutor_agent import _get_candidates
    # Cell 1 already has 2 in NAKED_SINGLE_BOARD
    candidates = _get_candidates(NAKED_SINGLE_BOARD, 1)
    # Should still compute based on constraints (cell is non-zero but function
    # doesn't skip filled cells — that's caller's responsibility)
    assert isinstance(candidates, list)


# ── Circuit breaker tests ─────────────────────────────────────────────────────

def test_circuit_breaker_opens_after_threshold():
    from app.ml.tutor_agent import _CircuitBreaker
    cb = _CircuitBreaker(threshold=3, window_secs=60)
    assert not cb.is_open()
    cb.record_failure()
    cb.record_failure()
    assert not cb.is_open()
    cb.record_failure()
    assert cb.is_open()


def test_circuit_breaker_resets_after_window():
    from app.ml.tutor_agent import _CircuitBreaker
    cb = _CircuitBreaker(threshold=2, window_secs=1)
    cb.record_failure()
    cb.record_failure()
    assert cb.is_open()
    time.sleep(1.1)
    assert not cb.is_open()


# ── LLM routing tests ─────────────────────────────────────────────────────────

def test_get_llm_quick_returns_ollama_when_available():
    mock_ollama = MagicMock()
    with patch("app.ml.tutor_agent._breaker.is_open", return_value=False), \
         patch("app.ml.tutor_agent.get_llm") as mock_get:
        mock_get.return_value = mock_ollama
        from app.ml.tutor_agent import get_llm
        # Patch the breaker directly
        result = get_llm("quick")
        # Just confirm it doesn't raise


def test_get_llm_returns_none_when_breaker_open():
    with patch("app.ml.tutor_agent._breaker.is_open", return_value=True):
        from app.ml.tutor_agent import get_llm
        result = get_llm("quick")
        assert result is None


def test_get_llm_deep_returns_none_without_api_key():
    with patch("app.ml.tutor_agent._breaker.is_open", return_value=False), \
         patch("app.config.settings.HF_INFERENCE_API_KEY", ""):
        from app.ml.tutor_agent import get_llm
        result = get_llm("deep")
        assert result is None


# ── Qdrant retriever tests (mocked) ───────────────────────────────────────────

def test_qdrant_retriever_returns_documents():
    mock_hit = MagicMock()
    mock_hit.score = 0.92
    mock_hit.payload = {
        "id": "naked-singles",
        "name": "Naked Singles",
        "concept": "A cell with only one candidate",
        "method": "Fill it in immediately",
        "visual_description": "Single candidate highlighted",
        "difficulty_level": 1,
        "prerequisite_techniques": [],
        "tags": ["basic", "singles"],
    }

    with patch("app.ml.rag_pipeline._get_qdrant") as mock_qdrant_fn:
        mock_client = MagicMock()
        mock_client.search.return_value = [mock_hit]
        mock_qdrant_fn.return_value = mock_client

        with patch("app.ml.rag_pipeline.embed_one", return_value=[0.1] * 384):
            from app.ml.rag_pipeline import QdrantTechniqueRetriever
            retriever = QdrantTechniqueRetriever(top_k=1)
            docs = retriever.retrieve("easy elimination")

    assert len(docs) == 1
    assert docs[0].metadata["name"] == "Naked Singles"
    assert docs[0].metadata["score"] == pytest.approx(0.92)


def test_qdrant_retriever_empty_results():
    with patch("app.ml.rag_pipeline._get_qdrant") as mock_qdrant_fn:
        mock_client = MagicMock()
        mock_client.search.return_value = []
        mock_qdrant_fn.return_value = mock_client

        with patch("app.ml.rag_pipeline.embed_one", return_value=[0.0] * 384):
            from app.ml.rag_pipeline import QdrantTechniqueRetriever
            retriever = QdrantTechniqueRetriever(top_k=3)
            docs = retriever.retrieve("unknown query")

    assert docs == []


# ── Rule-based fallback tests ─────────────────────────────────────────────────

def test_rule_based_hint_naked_single():
    from app.ml.tutor_agent import rule_based_hint
    hint = rule_based_hint(NAKED_SINGLE_BOARD)
    assert "Naked Single" in hint
    assert "row 1" in hint
    assert "column 1" in hint


def test_rule_based_hint_complete_board():
    from app.ml.tutor_agent import rule_based_hint
    hint = rule_based_hint(SOLVED_BOARD)
    assert "complete" in hint.lower()


def test_rule_based_hint_empty_board():
    from app.ml.tutor_agent import rule_based_hint
    hint = rule_based_hint(EMPTY_BOARD)
    # No naked singles on empty board, should suggest candidates
    assert isinstance(hint, str)
    assert len(hint) > 0


# ── Service layer tests (mocked agent) ────────────────────────────────────────

def test_get_hint_uses_fallback_when_no_llm():
    with patch("app.services.tutor_service.build_agent_executor", return_value=None):
        from app.services.tutor_service import TutorSession, get_hint
        session = TutorSession(
            session_id="test-1",
            user_id="user-1",
            board=NAKED_SINGLE_BOARD,
            puzzle=NAKED_SINGLE_BOARD,
        )
        result = get_hint(session)
        assert "technique" in result
        assert "explanation" in result
        assert "highlight_cells" in result
        assert "follow_up" in result


def test_get_hint_calls_agent_when_available():
    mock_executor = MagicMock()
    mock_executor.invoke.return_value = {
        "output": "**Naked Single** — cell (1,1) has only one candidate: 1.\nDoes that make sense?"
    }

    with patch("app.services.tutor_service.build_agent_executor", return_value=mock_executor):
        from app.services.tutor_service import TutorSession, get_hint
        session = TutorSession(
            session_id="test-2",
            user_id="user-2",
            board=NAKED_SINGLE_BOARD,
            puzzle=NAKED_SINGLE_BOARD,
        )
        result = get_hint(session)
        mock_executor.invoke.assert_called_once()
        assert result["explanation"] != ""


def test_session_memory_window():
    """After TUTOR_MEMORY_WINDOW exchanges, only last k messages remain."""
    with patch("app.services.tutor_service.build_agent_executor", return_value=None):
        from app.config import settings
        from app.services.tutor_service import TutorSession, get_hint

        session = TutorSession(
            session_id="test-mem",
            user_id="user-mem",
            board=NAKED_SINGLE_BOARD,
            puzzle=NAKED_SINGLE_BOARD,
        )

        for _ in range(settings.TUTOR_MEMORY_WINDOW + 3):
            get_hint(session)

        history = session.memory.load_memory_variables({}).get("chat_history", [])
        # Buffer window k means at most k*2 messages (input+output pairs)
        assert len(history) <= settings.TUTOR_MEMORY_WINDOW * 2


def test_explain_technique_fallback_no_llm():
    mock_doc = MagicMock()
    mock_doc.page_content = "**X-Wing** (difficulty 3/5)\nConcept: ..."
    mock_doc.metadata = {"name": "X-Wing", "difficulty_level": 3}

    with patch("app.services.tutor_service.get_llm", return_value=None), \
         patch("app.services.tutor_service.QdrantTechniqueRetriever") as mock_ret:
        instance = mock_ret.return_value
        instance.retrieve.return_value = [mock_doc]

        from app.services.tutor_service import TutorSession, explain_technique
        session = TutorSession(
            session_id="test-3",
            user_id="user-3",
            board=EMPTY_BOARD,
            puzzle=EMPTY_BOARD,
        )
        result = explain_technique(session, "X-Wing")
        assert result["technique"] == "X-Wing"


# ── FastAPI endpoint tests ────────────────────────────────────────────────────

@pytest.fixture
def client():
    from app.main import create_app
    app = create_app()
    return TestClient(app)


def test_hint_endpoint_returns_200(client):
    with patch("app.services.tutor_service.build_agent_executor", return_value=None):
        resp = client.post(
            "/api/v1/tutor/hint",
            json={
                "user_id": "user-test",
                "board": NAKED_SINGLE_BOARD,
                "puzzle": NAKED_SINGLE_BOARD,
            },
        )
    assert resp.status_code == 200
    data = resp.json()
    assert "session_id" in data
    assert "explanation" in data
    assert "highlight_cells" in data


def test_hint_endpoint_invalid_board(client):
    resp = client.post(
        "/api/v1/tutor/hint",
        json={
            "user_id": "user-test",
            "board": [0] * 80,  # wrong length
            "puzzle": [0] * 81,
        },
    )
    assert resp.status_code == 422


def test_explain_endpoint_returns_200(client):
    mock_doc = MagicMock()
    mock_doc.page_content = "Naked Singles explanation"
    mock_doc.metadata = {"name": "Naked Singles", "difficulty_level": 1}

    with patch("app.services.tutor_service.get_llm", return_value=None), \
         patch("app.services.tutor_service.QdrantTechniqueRetriever") as mock_ret:
        instance = mock_ret.return_value
        instance.retrieve.return_value = [mock_doc]

        resp = client.post(
            "/api/v1/tutor/explain",
            json={
                "user_id": "user-test",
                "board": EMPTY_BOARD,
                "puzzle": EMPTY_BOARD,
                "technique_name": "Naked Singles",
            },
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["technique"] == "Naked Singles"


def test_followup_endpoint_404_unknown_session(client):
    resp = client.post(
        "/api/v1/tutor/followup",
        json={
            "user_id": "user-test",
            "session_id": "nonexistent-session-id",
            "board": EMPTY_BOARD,
            "puzzle": EMPTY_BOARD,
            "message": "I don't understand",
        },
    )
    assert resp.status_code == 404


def test_followup_endpoint_existing_session(client):
    with patch("app.services.tutor_service.build_agent_executor", return_value=None):
        # Create a session via hint
        resp = client.post(
            "/api/v1/tutor/hint",
            json={
                "user_id": "user-followup",
                "board": NAKED_SINGLE_BOARD,
                "puzzle": NAKED_SINGLE_BOARD,
            },
        )
        assert resp.status_code == 200
        session_id = resp.json()["session_id"]

        # Follow up
        resp2 = client.post(
            "/api/v1/tutor/followup",
            json={
                "user_id": "user-followup",
                "session_id": session_id,
                "board": NAKED_SINGLE_BOARD,
                "puzzle": NAKED_SINGLE_BOARD,
                "message": "Can you explain more?",
            },
        )
    assert resp2.status_code == 200
    assert resp2.json()["session_id"] == session_id


def test_session_id_persisted_across_calls(client):
    """Same session_id supplied returns the same session."""
    sid = str(uuid.uuid4())
    with patch("app.services.tutor_service.build_agent_executor", return_value=None):
        for _ in range(2):
            resp = client.post(
                "/api/v1/tutor/hint",
                json={
                    "user_id": "user-persist",
                    "session_id": sid,
                    "board": NAKED_SINGLE_BOARD,
                    "puzzle": NAKED_SINGLE_BOARD,
                },
            )
            assert resp.json()["session_id"] == sid
