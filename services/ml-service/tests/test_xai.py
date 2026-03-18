"""
Tests for D2 — XAI Technique Overlay.

Coverage:
- Feature extraction from board
- SHAP-to-cell mapping shape and normalisation
- top_cells ordering
- Rule-based fallback when classifier not loaded
- Full explain_board pipeline (mocked classifier)
- FastAPI endpoint: valid request, invalid board, response schema
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# ── Fixtures ──────────────────────────────────────────────────────────────────

# Near-complete board with one empty cell at index 0
NEAR_COMPLETE = [
    0, 2, 3, 4, 5, 6, 7, 8, 9,
    4, 5, 6, 7, 8, 9, 1, 2, 3,
    7, 8, 9, 1, 2, 3, 4, 5, 6,
    2, 1, 4, 3, 6, 5, 8, 9, 7,
    3, 6, 5, 8, 9, 7, 2, 1, 4,
    8, 9, 7, 2, 1, 4, 3, 6, 5,
    5, 3, 1, 6, 4, 2, 9, 7, 8,
    6, 4, 2, 9, 7, 8, 5, 3, 1,
    9, 7, 8, 5, 3, 1, 6, 4, 2,
]

EMPTY_BOARD = [0] * 81

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

UNIFORM_SHAP = {
    "clue_count": 0.1,
    "naked_singles": 0.1,
    "hidden_singles": 0.1,
    "naked_pairs": 0.1,
    "pointing_pairs": 0.05,
    "box_line_reduction": 0.05,
    "backtrack_depth": 0.2,
    "constraint_density": 0.1,
    "symmetry_score": 0.05,
    "avg_candidate_count": 0.15,
}


# ── Feature extraction tests ──────────────────────────────────────────────────

def test_extract_features_returns_all_keys():
    from app.ml.xai import extract_features
    from app.ml.dataset_generator import FEATURE_NAMES

    features = extract_features(NEAR_COMPLETE, NEAR_COMPLETE)
    for name in FEATURE_NAMES:
        assert name in features, f"Missing feature: {name}"


def test_extract_features_clue_count():
    from app.ml.xai import extract_features

    # NEAR_COMPLETE puzzle has 80 given cells (index 0 is 0)
    features = extract_features(NEAR_COMPLETE, NEAR_COMPLETE)
    assert features["clue_count"] == 80.0


def test_extract_features_naked_singles():
    from app.ml.xai import extract_features

    # NEAR_COMPLETE has exactly one empty cell with one candidate
    features = extract_features(NEAR_COMPLETE, NEAR_COMPLETE)
    assert features["naked_singles"] == 1.0


def test_extract_features_solved_board():
    from app.ml.xai import extract_features

    features = extract_features(SOLVED_BOARD, SOLVED_BOARD)
    assert features["clue_count"] == 81.0
    assert features["naked_singles"] == 0.0
    assert features["avg_candidate_count"] == 0.0


def test_extract_features_empty_board():
    from app.ml.xai import extract_features

    features = extract_features(EMPTY_BOARD, EMPTY_BOARD)
    assert features["clue_count"] == 0.0
    assert features["naked_singles"] == 0.0
    assert features["avg_candidate_count"] == 9.0  # all 9 digits possible everywhere


def test_extract_features_constraint_density_range():
    from app.ml.xai import extract_features

    features = extract_features(NEAR_COMPLETE, NEAR_COMPLETE)
    assert 0.0 <= features["constraint_density"] <= 1.0


def test_extract_features_symmetry_score_range():
    from app.ml.xai import extract_features

    features = extract_features(NEAR_COMPLETE, NEAR_COMPLETE)
    assert 0.0 <= features["symmetry_score"] <= 1.0


# ── SHAP-to-cell mapping tests ────────────────────────────────────────────────

def test_map_shap_to_cells_length():
    from app.ml.xai import map_shap_to_cells

    importances = map_shap_to_cells(NEAR_COMPLETE, NEAR_COMPLETE, UNIFORM_SHAP)
    assert len(importances) == 81


def test_map_shap_to_cells_range():
    from app.ml.xai import map_shap_to_cells

    importances = map_shap_to_cells(NEAR_COMPLETE, NEAR_COMPLETE, UNIFORM_SHAP)
    assert all(0.0 <= v <= 1.0 for v in importances), "All scores must be 0–1"


def test_map_shap_to_cells_normalised():
    """Max value should be 1.0 when there is any non-zero importance."""
    from app.ml.xai import map_shap_to_cells

    importances = map_shap_to_cells(NEAR_COMPLETE, NEAR_COMPLETE, UNIFORM_SHAP)
    assert max(importances) == pytest.approx(1.0)


def test_map_shap_to_cells_solved_board_all_zero():
    """Solved board has no empty cells — importances should all be 0 or only clue/symmetry weight."""
    from app.ml.xai import map_shap_to_cells

    shap = {k: 0.0 for k in UNIFORM_SHAP}
    shap["clue_count"] = 1.0
    importances = map_shap_to_cells(SOLVED_BOARD, SOLVED_BOARD, shap)
    # clue_count weight distributed to all 81 given cells
    assert all(v >= 0.0 for v in importances)


def test_map_shap_zero_shap_all_zero():
    """Zero SHAP values → all cell importances are 0."""
    from app.ml.xai import map_shap_to_cells

    zero_shap = {k: 0.0 for k in UNIFORM_SHAP}
    importances = map_shap_to_cells(NEAR_COMPLETE, NEAR_COMPLETE, zero_shap)
    assert all(v == 0.0 for v in importances)


def test_map_shap_naked_single_gets_weight():
    """Cell 0 (the naked single) should receive naked_singles weight."""
    from app.ml.xai import map_shap_to_cells

    shap = {k: 0.0 for k in UNIFORM_SHAP}
    shap["naked_singles"] = 1.0
    importances = map_shap_to_cells(NEAR_COMPLETE, NEAR_COMPLETE, shap)
    # Cell 0 is the only empty cell and is a naked single
    assert importances[0] == pytest.approx(1.0)
    # All other cells were filled, so after normalisation they should be 0
    assert all(importances[i] == 0.0 for i in range(1, 81))


# ── top_cells tests ───────────────────────────────────────────────────────────

def test_top_cells_ordering():
    from app.ml.xai import top_cells

    importances = [0.0] * 81
    importances[5] = 0.9
    importances[20] = 0.7
    importances[63] = 0.5
    result = top_cells(importances, n=3)
    assert result[0] == 5
    assert result[1] == 20
    assert result[2] == 63


def test_top_cells_n_limit():
    from app.ml.xai import top_cells

    importances = [float(i) / 80 for i in range(81)]
    result = top_cells(importances, n=5)
    assert len(result) == 5


def test_top_cells_zero_excluded():
    from app.ml.xai import top_cells

    importances = [0.0] * 81
    importances[10] = 0.5
    result = top_cells(importances, n=9)
    assert 10 in result
    assert len(result) == 1  # only 1 non-zero cell


# ── explain_board integration test (mocked classifier) ───────────────────────

def test_explain_board_structure():
    mock_result = {
        "difficulty": "hard",
        "confidence": 0.82,
        "shap_values": UNIFORM_SHAP,
        "explanation": "Classified as hard.",
    }
    with patch("app.ml.xai.classifier") as mock_clf:
        mock_clf.predict.return_value = mock_result
        from app.ml.xai import explain_board

        result = explain_board(NEAR_COMPLETE, NEAR_COMPLETE)

    assert result["predicted_difficulty"] == "hard"
    assert result["confidence"] == pytest.approx(0.82)
    assert len(result["cell_importances"]) == 81
    assert isinstance(result["top_cells"], list)
    assert "shap_values" in result
    assert "explanation" in result


def test_explain_board_rule_based_fallback():
    """Works end-to-end when classifier uses rule-based fallback."""
    from app.ml.xai import explain_board

    # classifier.predict uses rule-based when model not loaded
    result = explain_board(NEAR_COMPLETE, NEAR_COMPLETE)
    assert len(result["cell_importances"]) == 81
    assert result["predicted_difficulty"] in [
        "super_easy", "easy", "medium", "hard", "super_hard", "extreme"
    ]


# ── FastAPI endpoint tests ────────────────────────────────────────────────────

@pytest.fixture
def client():
    from app.main import create_app
    return TestClient(create_app())


def test_cell_importance_endpoint_200(client):
    resp = client.post(
        "/api/v1/xai/cell-importance",
        json={"board": NEAR_COMPLETE, "puzzle": NEAR_COMPLETE},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "cell_importances" in data
    assert len(data["cell_importances"]) == 81
    assert "predicted_difficulty" in data
    assert "confidence" in data
    assert "top_cells" in data
    assert "shap_values" in data
    assert "explanation" in data


def test_cell_importance_endpoint_invalid_board(client):
    resp = client.post(
        "/api/v1/xai/cell-importance",
        json={"board": [0] * 80, "puzzle": [0] * 81},
    )
    assert resp.status_code == 422


def test_cell_importance_endpoint_invalid_values(client):
    bad_board = NEAR_COMPLETE[:]
    bad_board[0] = 10  # out of range
    resp = client.post(
        "/api/v1/xai/cell-importance",
        json={"board": bad_board, "puzzle": NEAR_COMPLETE},
    )
    assert resp.status_code == 422


def test_cell_importance_scores_range(client):
    resp = client.post(
        "/api/v1/xai/cell-importance",
        json={"board": NEAR_COMPLETE, "puzzle": NEAR_COMPLETE},
    )
    assert resp.status_code == 200
    scores = resp.json()["cell_importances"]
    assert all(0.0 <= s <= 1.0 for s in scores), "All scores must be in [0, 1]"


def test_cell_importance_confidence_range(client):
    resp = client.post(
        "/api/v1/xai/cell-importance",
        json={"board": NEAR_COMPLETE, "puzzle": NEAR_COMPLETE},
    )
    assert resp.status_code == 200
    assert 0.0 <= resp.json()["confidence"] <= 1.0


def test_cell_importance_solved_board(client):
    """Fully solved board should still return valid response."""
    resp = client.post(
        "/api/v1/xai/cell-importance",
        json={"board": SOLVED_BOARD, "puzzle": SOLVED_BOARD},
    )
    assert resp.status_code == 200
    scores = resp.json()["cell_importances"]
    assert len(scores) == 81
