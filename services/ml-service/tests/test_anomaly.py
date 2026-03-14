"""
test_anomaly.py — pytest suite for the anomaly detection service and API.

Tests are grouped:
  - Feature extractor (unit)
  - AnomalyService heuristic fallback (no model required)
  - FastAPI endpoint via httpx Client
"""

from __future__ import annotations

import pytest
import numpy as np


# ─── Feature Extractor ────────────────────────────────────────────────────────

class TestFeatureExtractor:
    def test_output_shape(self):
        from app.ml.feature_extractor import extract_features
        f = extract_features(
            time_elapsed_ms=180_000,
            cells_filled=40,
            errors_count=3,
            hints_used=1,
            difficulty="easy",
        )
        assert f.shape == (10,)

    def test_all_features_in_unit_range(self):
        from app.ml.feature_extractor import extract_features
        f = extract_features(
            time_elapsed_ms=300_000,
            cells_filled=45,
            errors_count=5,
            hints_used=2,
            difficulty="medium",
        )
        assert np.all(f >= 0.0), "All features must be >= 0"
        assert np.all(f <= 1.0), "All features must be <= 1"

    def test_dtype_is_float32(self):
        from app.ml.feature_extractor import extract_features
        f = extract_features(
            time_elapsed_ms=120_000, cells_filled=30,
            errors_count=0, hints_used=0, difficulty="beginner",
        )
        assert f.dtype == np.float32

    def test_fast_solver_has_low_time_features(self):
        from app.ml.feature_extractor import extract_features
        fast = extract_features(
            time_elapsed_ms=5_000,  # 5 s total — superhuman
            cells_filled=45,
            errors_count=0,
            hints_used=0,
            difficulty="medium",
            cell_fill_times_ms=[100] * 45,
        )
        # f0 = time_mean_norm — very fast → very low
        assert fast[0] < 0.02

    def test_high_fill_rate_for_fast_solver(self):
        from app.ml.feature_extractor import extract_features
        f = extract_features(
            time_elapsed_ms=10_000,  # 10 s for 50 cells → 5 cells/s
            cells_filled=50,
            errors_count=0,
            hints_used=0,
            difficulty="hard",
        )
        assert f[6] > 0.5  # fill_rate_norm above average

    def test_zero_errors_gives_zero_error_rate(self):
        from app.ml.feature_extractor import extract_features
        f = extract_features(
            time_elapsed_ms=300_000, cells_filled=45,
            errors_count=0, hints_used=0, difficulty="medium",
        )
        assert f[4] == pytest.approx(0.0)

    def test_error_rate_bounded(self):
        from app.ml.feature_extractor import extract_features
        f = extract_features(
            time_elapsed_ms=600_000, cells_filled=5,
            errors_count=200, hints_used=0, difficulty="hard",
        )
        assert 0.0 <= f[4] <= 1.0

    def test_hint_rate_reflects_hints(self):
        from app.ml.feature_extractor import extract_features
        f = extract_features(
            time_elapsed_ms=300_000, cells_filled=45,
            errors_count=0, hints_used=45, difficulty="medium",
        )
        assert f[5] == pytest.approx(1.0)  # hint_rate saturated

    def test_cell_fill_times_improve_accuracy(self):
        from app.ml.feature_extractor import extract_features
        # With per-cell times we can compute exact min/percentiles.
        f_with = extract_features(
            time_elapsed_ms=90_000, cells_filled=30,
            errors_count=0, hints_used=0, difficulty="easy",
            cell_fill_times_ms=list(range(1000, 4000, 100)),
        )
        f_without = extract_features(
            time_elapsed_ms=90_000, cells_filled=30,
            errors_count=0, hints_used=0, difficulty="easy",
        )
        # Both should produce valid outputs regardless of cell times.
        assert f_with.shape == (10,)
        assert f_without.shape == (10,)

    def test_generate_normal_features_shape(self):
        from app.ml.feature_extractor import generate_normal_features
        X = generate_normal_features(n=500)
        assert X.shape == (500, 10)

    def test_generate_normal_features_range(self):
        from app.ml.feature_extractor import generate_normal_features
        X = generate_normal_features(n=1_000)
        assert np.all(X >= 0.0)
        assert np.all(X <= 1.0)

    def test_generate_anomalous_features_shape(self):
        from app.ml.feature_extractor import generate_anomalous_features
        X = generate_anomalous_features(n=100)
        assert X.shape == (100, 10)

    def test_anomalous_has_lower_time_mean_than_normal(self):
        from app.ml.feature_extractor import generate_normal_features, generate_anomalous_features
        normal = generate_normal_features(n=500)
        anon = generate_anomalous_features(n=200)
        # Feature 0 = time_mean_norm — anomalous should be much lower.
        assert anon[:, 0].mean() < normal[:, 0].mean()


# ─── AnomalyService Heuristic ─────────────────────────────────────────────────

class TestAnomalyServiceHeuristic:
    """Force heuristic path by ensuring no model is loaded."""

    @pytest.fixture(autouse=True)
    def force_heuristic(self, monkeypatch):
        from app.services.anomaly_service import AnomalyService
        # Patch _ensure_loaded to mark loaded but leave model refs None.
        monkeypatch.setattr(AnomalyService, "_ensure_loaded", lambda self: None)

    def _svc(self):
        from app.services.anomaly_service import AnomalyService
        svc = AnomalyService()
        svc._loaded = True  # skip lazy load in this instance
        return svc

    def test_normal_session_not_anomalous(self):
        svc = self._svc()
        result = svc.score(
            time_elapsed_ms=300_000,
            cells_filled=45,
            errors_count=4,
            hints_used=2,
            difficulty="medium",
        )
        assert not result["is_anomalous"]

    def test_superhuman_session_flagged(self):
        svc = self._svc()
        result = svc.score(
            time_elapsed_ms=3_000,     # 3 s total → fill_rate very high
            cells_filled=50,
            errors_count=0,
            hints_used=0,
            difficulty="hard",
            cell_fill_times_ms=[60] * 50,  # 60 ms/cell
        )
        assert result["is_anomalous"]

    def test_result_has_required_keys(self):
        svc = self._svc()
        result = svc.score(
            time_elapsed_ms=120_000, cells_filled=35,
            errors_count=2, hints_used=1, difficulty="easy",
        )
        for key in ("anomaly_score", "reconstruction_error", "threshold", "is_anomalous"):
            assert key in result, f"Missing key: {key}"

    def test_anomaly_score_is_float(self):
        svc = self._svc()
        result = svc.score(
            time_elapsed_ms=180_000, cells_filled=40,
            errors_count=0, hints_used=0, difficulty="easy",
        )
        assert isinstance(result["anomaly_score"], float)

    def test_is_anomalous_is_bool(self):
        svc = self._svc()
        result = svc.score(
            time_elapsed_ms=180_000, cells_filled=40,
            errors_count=0, hints_used=0, difficulty="easy",
        )
        assert isinstance(result["is_anomalous"], bool)


# ─── FastAPI Endpoint ──────────────────────────────────────────────────────────

class TestAnomalyEndpoint:
    @pytest.fixture()
    def client(self, monkeypatch):
        from app.services.anomaly_service import AnomalyService
        monkeypatch.setattr(AnomalyService, "_ensure_loaded", lambda self: None)
        from starlette.testclient import TestClient
        from app.main import create_app
        app = create_app()
        with TestClient(app, raise_server_exceptions=True) as c:
            yield c

    def _valid_body(self, **kwargs):
        base = {
            "session_id": "sess-001",
            "user_id": "user-001",
            "difficulty": "easy",
            "time_elapsed_ms": 180_000,
            "cells_filled": 40,
            "errors_count": 3,
            "hints_used": 1,
        }
        base.update(kwargs)
        return base

    def test_normal_session_returns_200(self, client):
        resp = client.post("/api/v1/anomaly/score", json=self._valid_body())
        assert resp.status_code == 200

    def test_response_has_all_fields(self, client):
        resp = client.post("/api/v1/anomaly/score", json=self._valid_body())
        body = resp.json()
        for field in ("session_id", "user_id", "anomaly_score",
                      "reconstruction_error", "threshold", "is_anomalous"):
            assert field in body

    def test_session_id_echoed(self, client):
        resp = client.post("/api/v1/anomaly/score", json=self._valid_body())
        assert resp.json()["session_id"] == "sess-001"

    def test_invalid_difficulty_returns_422(self, client):
        resp = client.post("/api/v1/anomaly/score",
                           json=self._valid_body(difficulty="impossible"))
        assert resp.status_code == 422

    def test_too_short_time_returns_422(self, client):
        resp = client.post("/api/v1/anomaly/score",
                           json=self._valid_body(time_elapsed_ms=500))
        assert resp.status_code == 422

    def test_negative_errors_returns_422(self, client):
        resp = client.post("/api/v1/anomaly/score",
                           json=self._valid_body(errors_count=-1))
        assert resp.status_code == 422

    def test_cells_filled_over_81_returns_422(self, client):
        resp = client.post("/api/v1/anomaly/score",
                           json=self._valid_body(cells_filled=82))
        assert resp.status_code == 422

    def test_optional_cells_to_fill_accepted(self, client):
        resp = client.post("/api/v1/anomaly/score",
                           json=self._valid_body(cells_to_fill=45))
        assert resp.status_code == 200

    def test_optional_cell_fill_times_accepted(self, client):
        resp = client.post(
            "/api/v1/anomaly/score",
            json=self._valid_body(cell_fill_times_ms=[800, 1200, 900, 1500] * 10),
        )
        assert resp.status_code == 200

    def test_is_anomalous_is_boolean(self, client):
        resp = client.post("/api/v1/anomaly/score", json=self._valid_body())
        assert isinstance(resp.json()["is_anomalous"], bool)

    def test_anomaly_score_is_numeric(self, client):
        resp = client.post("/api/v1/anomaly/score", json=self._valid_body())
        score = resp.json()["anomaly_score"]
        assert isinstance(score, (int, float))
        assert score >= 0.0
