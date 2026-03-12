"""
Tests for on-device edge AI — ONNX export, batch classification, fallback chain.
"""

import pytest
import numpy as np


# ─── ONNX Export ──────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestONNXExport:

    def test_manual_export_fallback(self, tmp_path):
        """When skl2onnx is unavailable, manual JSON export should work."""
        import pickle
        from pathlib import Path
        from sklearn.ensemble import RandomForestClassifier
        from app.ml.export_onnx import _manual_onnx_export

        # Train a tiny model
        from app.ml.train_classifier import prepare_data
        X_train, _, y_train, _, encoder = prepare_data(n_samples=120, seed=42)
        model = RandomForestClassifier(n_estimators=5, random_state=42)
        model.fit(X_train, y_train)

        output_path = tmp_path / "classifier.onnx"
        _manual_onnx_export(model, output_path)

        json_path = output_path.with_suffix(".json")
        assert json_path.exists()

        import json
        with open(json_path) as f:
            data = json.load(f)
        assert "n_estimators" in data
        assert "classes" in data
        assert data["n_estimators"] == 5

    def test_export_classifier_not_found(self, tmp_path):
        from app.ml.export_onnx import export_classifier_onnx
        with pytest.raises(FileNotFoundError):
            export_classifier_onnx(model_dir=tmp_path)


# ─── Edge AI Router ──────────────────────────────────────────────────────────


@pytest.mark.unit
class TestEdgeAIRouter:

    @pytest.fixture
    def client(self):
        """Create test client with edge router."""
        from fastapi.testclient import TestClient
        from app.main import create_app
        app = create_app()
        return TestClient(app)

    def test_edge_status(self, client):
        response = client.get("/api/v1/edge/status")
        assert response.status_code == 200
        data = response.json()
        assert data["edge_ai_enabled"] is True
        assert "models" in data

    def test_batch_classify_single(self, client):
        response = client.post(
            "/api/v1/edge/batch-classify",
            json={
                "puzzles": [{
                    "clue_count": 30,
                    "naked_singles": 10,
                    "hidden_singles": 8,
                    "naked_pairs": 2,
                    "pointing_pairs": 1,
                    "box_line_reduction": 0,
                    "backtrack_depth": 0,
                    "constraint_density": 0.45,
                    "symmetry_score": 0.5,
                    "avg_candidate_count": 3.0,
                }]
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 1
        assert len(data["results"]) == 1
        assert "difficulty" in data["results"][0]

    def test_batch_classify_multiple(self, client):
        puzzles = []
        for clue_count in [50, 35, 25, 18]:
            puzzles.append({
                "clue_count": clue_count,
                "constraint_density": 0.5,
                "avg_candidate_count": 3.0,
            })

        response = client.post(
            "/api/v1/edge/batch-classify",
            json={"puzzles": puzzles},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 4
        assert len(data["results"]) == 4

    def test_classifier_model_not_found(self, client):
        response = client.get("/api/v1/edge/models/classifier")
        assert response.status_code == 200
        data = response.json()
        assert "error" in data

    def test_scanner_model_not_found(self, client):
        response = client.get("/api/v1/edge/models/scanner")
        assert response.status_code == 200
        data = response.json()
        assert "error" in data


# ─── Fallback Chain Logic ────────────────────────────────────────────────────


@pytest.mark.unit
class TestFallbackChain:

    def test_rule_based_all_difficulties(self):
        """Verify rule-based classification covers all difficulty classes."""
        from app.services.classifier_service import DifficultyClassifier
        clf = DifficultyClassifier()

        test_cases = [
            (50, "super_easy"),
            (40, "easy"),
            (30, "medium"),
            (27, "hard"),
            (23, "super_hard"),
            (18, "extreme"),
        ]

        for clue_count, expected in test_cases:
            result = clf.predict({"clue_count": clue_count})
            assert result["difficulty"] == expected
            assert result["confidence"] == 0.5
            assert "Rule-based fallback" in result["explanation"]

    def test_batch_performance(self, tmp_path):
        """Batch classification of 100 puzzles should complete quickly."""
        import time
        from app.services.classifier_service import DifficultyClassifier
        clf = DifficultyClassifier()

        puzzles = [{"clue_count": np.random.randint(17, 55)} for _ in range(100)]
        start = time.time()
        results = [clf.predict(p) for p in puzzles]
        elapsed = time.time() - start

        assert len(results) == 100
        assert elapsed < 1.0, f"Batch of 100 took {elapsed:.2f}s — too slow"
