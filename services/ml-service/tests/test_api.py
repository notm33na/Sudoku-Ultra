"""
Tests for health, classification, scan, and recommendation endpoints.
"""

import pytest


# ─── Health ────────────────────────────────────────────────────────────────────


@pytest.mark.unit
async def test_health_returns_200(client):
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "ml-service"
    assert "version" in data
    assert "timestamp" in data
    assert "models_loaded" in data


@pytest.mark.unit
async def test_health_models_loaded_is_dict(client):
    response = await client.get("/health")
    models = response.json()["models_loaded"]
    assert isinstance(models, dict)
    assert "difficulty_classifier" in models
    assert "puzzle_scanner" in models


# ─── Classify ──────────────────────────────────────────────────────────────────


@pytest.mark.unit
async def test_classify_returns_difficulty(client):
    payload = {
        "clue_count": 35,
        "naked_singles": 20,
        "hidden_singles": 10,
        "naked_pairs": 2,
        "pointing_pairs": 1,
        "box_line_reduction": 0,
        "backtrack_depth": 0,
        "constraint_density": 0.4,
        "symmetry_score": 0.5,
        "avg_candidate_count": 3.2,
    }
    response = await client.post("/api/v1/classify", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["difficulty"] in ["super_easy", "easy", "medium", "hard", "super_hard", "extreme"]
    assert 0.0 <= data["confidence"] <= 1.0
    assert "shap_values" in data
    assert "explanation" in data


@pytest.mark.unit
async def test_classify_easy_puzzle(client):
    payload = {
        "clue_count": 50,
        "naked_singles": 30,
        "hidden_singles": 1,
        "constraint_density": 0.8,
        "avg_candidate_count": 1.5,
    }
    response = await client.post("/api/v1/classify", json=payload)
    assert response.status_code == 200
    assert response.json()["difficulty"] == "super_easy"


@pytest.mark.unit
async def test_classify_hard_puzzle(client):
    payload = {
        "clue_count": 20,
        "naked_singles": 5,
        "hidden_singles": 3,
        "backtrack_depth": 5,
        "constraint_density": 0.2,
        "avg_candidate_count": 5.0,
    }
    response = await client.post("/api/v1/classify", json=payload)
    assert response.status_code == 200
    assert response.json()["difficulty"] == "extreme"


@pytest.mark.unit
async def test_classify_validates_input(client):
    payload = {"clue_count": -1, "naked_singles": 0, "hidden_singles": 0, "constraint_density": 0.5, "avg_candidate_count": 3.0}
    response = await client.post("/api/v1/classify", json=payload)
    assert response.status_code == 422


# ─── Scan ──────────────────────────────────────────────────────────────────────


@pytest.mark.unit
async def test_scan_returns_placeholder(client):
    # Create a minimal PNG file (1x1 pixel)
    import io

    fake_image = io.BytesIO(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
    response = await client.post(
        "/api/v1/scan",
        files={"image": ("test.png", fake_image, "image/png")},
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data["grid"]) == 81
    assert len(data["confidence"]) == 81
    assert "warnings" in data


# ─── Recommend ─────────────────────────────────────────────────────────────────


@pytest.mark.unit
async def test_recommend_returns_fallback(client):
    payload = {
        "user_id": "test-user-123",
        "avg_solve_time_per_difficulty": {"easy": 120.0, "medium": 300.0},
        "hint_rate": 0.1,
        "error_rate": 0.05,
        "current_streak": 5,
        "session_count": 20,
        "last_played_difficulty": "medium",
        "win_rate": 0.85,
    }
    response = await client.post("/api/v1/recommend-difficulty", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["recommended_difficulty"] == "medium"
    assert 0.0 <= data["confidence"] <= 1.0
    assert "reasoning" in data


# ─── Model Registry ──────────────────────────────────────────────────────────


@pytest.mark.unit
def test_model_registry_register_and_get(model_registry):
    model_registry.register("test_model", {"type": "mock"}, {"accuracy": 0.95})
    assert model_registry.is_loaded("test_model")
    assert model_registry.get("test_model") == {"type": "mock"}
    assert model_registry.get_metadata("test_model")["accuracy"] == 0.95


@pytest.mark.unit
def test_model_registry_missing_model(model_registry):
    assert not model_registry.is_loaded("nonexistent")
    assert model_registry.get("nonexistent") is None


@pytest.mark.unit
def test_model_registry_list_models(model_registry):
    status = model_registry.list_models()
    assert "difficulty_classifier" in status
    assert all(v is False for v in status.values())
