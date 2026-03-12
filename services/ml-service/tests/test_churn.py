"""
Tests for churn predictor — dataset generation, training, inference, API.
"""

import pytest
import numpy as np


# ─── Churn Dataset Generator ─────────────────────────────────────────────────


@pytest.mark.unit
class TestChurnDatasetGenerator:

    def test_generate_correct_count(self):
        from app.ml.churn_dataset_generator import generate_churn_dataset
        dataset = generate_churn_dataset(n_samples=50, seed=1)
        assert len(dataset) == 50

    def test_balanced_archetypes(self):
        from app.ml.churn_dataset_generator import generate_churn_dataset
        dataset = generate_churn_dataset(n_samples=100, seed=2)
        # 100 / 5 archetypes = 20 per archetype
        assert len(dataset) == 100

    def test_all_features_present(self):
        from app.ml.churn_dataset_generator import generate_churn_dataset, FEATURE_NAMES
        dataset = generate_churn_dataset(n_samples=5, seed=3)
        for sample in dataset:
            for feat in FEATURE_NAMES:
                assert feat in sample, f"Missing: {feat}"
            assert "churned" in sample

    def test_feature_ranges(self):
        from app.ml.churn_dataset_generator import generate_churn_dataset
        dataset = generate_churn_dataset(n_samples=100, seed=4)
        for sample in dataset:
            assert sample["days_since_last_play"] >= 0
            assert sample["session_frequency"] >= 0.0
            assert sample["avg_session_duration"] >= 0.0
            assert sample["total_games_played"] >= 0
            assert -1.0 <= sample["win_rate_trend"] <= 1.0
            assert -1.0 <= sample["hint_usage_trend"] <= 1.0
            assert sample["difficulty_variety"] >= 1
            assert 0.0 <= sample["completion_rate"] <= 1.0
            assert -1.0 <= sample["error_rate_trend"] <= 1.0
            assert sample["longest_streak"] >= 0
            assert sample["churned"] in (0, 1)

    def test_both_classes_present(self):
        from app.ml.churn_dataset_generator import generate_churn_dataset
        dataset = generate_churn_dataset(n_samples=500, seed=5)
        labels = [s["churned"] for s in dataset]
        assert 0 in labels and 1 in labels

    def test_reproducible(self):
        from app.ml.churn_dataset_generator import generate_churn_dataset
        d1 = generate_churn_dataset(n_samples=10, seed=99)
        d2 = generate_churn_dataset(n_samples=10, seed=99)
        assert d1 == d2

    def test_csv_output(self, tmp_path):
        from app.ml.churn_dataset_generator import generate_churn_dataset
        import csv
        output = str(tmp_path / "churn.csv")
        generate_churn_dataset(n_samples=20, output_path=output, seed=6)
        with open(output) as f:
            rows = list(csv.DictReader(f))
        assert len(rows) == 20


# ─── Churn Service Inference ─────────────────────────────────────────────────


@pytest.mark.unit
class TestChurnService:

    def test_fallback_returns_result(self):
        from app.services.churn_service import ChurnPredictor
        svc = ChurnPredictor()
        assert not svc.is_loaded

        result = svc.predict({"days_since_last_play": 3, "session_frequency": 4.0})
        assert isinstance(result["churn_risk"], bool)
        assert 0.0 <= result["probability"] <= 1.0
        assert result["risk_level"] in ("low", "medium", "high", "critical")
        assert "Model not loaded" in result["reasoning"]

    def test_fallback_high_risk(self):
        from app.services.churn_service import ChurnPredictor
        svc = ChurnPredictor()
        result = svc.predict({"days_since_last_play": 60, "session_frequency": 0.1})
        assert result["probability"] >= 0.5
        assert result["churn_risk"] is True

    def test_fallback_low_risk(self):
        from app.services.churn_service import ChurnPredictor
        svc = ChurnPredictor()
        result = svc.predict({"days_since_last_play": 1, "session_frequency": 5.0})
        assert result["probability"] < 0.5
        assert result["churn_risk"] is False

    def test_load_nonexistent(self):
        from pathlib import Path
        from app.services.churn_service import ChurnPredictor
        svc = ChurnPredictor()
        assert not svc.load(Path("/nonexistent"))

    def test_trained_model_inference(self, tmp_path):
        """Train a tiny model, save, load, and predict."""
        import pickle
        from sklearn.linear_model import LogisticRegression
        from sklearn.preprocessing import StandardScaler
        from app.ml.train_churn import prepare_data
        from app.services.churn_service import ChurnPredictor

        X_train, X_test, y_train, y_test, scaler = prepare_data(
            n_samples=200, seed=42,
        )

        model = LogisticRegression(max_iter=200, random_state=42)
        model.fit(X_train, y_train)

        model_path = tmp_path / "churn_predictor.pkl"
        scaler_path = tmp_path / "churn_scaler.pkl"
        with open(model_path, "wb") as f:
            pickle.dump(model, f)
        with open(scaler_path, "wb") as f:
            pickle.dump(scaler, f)

        svc = ChurnPredictor()
        assert svc.load(tmp_path)
        assert svc.is_loaded

        result = svc.predict({
            "days_since_last_play": 30,
            "session_frequency": 0.5,
            "avg_session_duration": 8,
            "total_games_played": 100,
            "win_rate_trend": -0.1,
            "hint_usage_trend": 0.2,
            "difficulty_variety": 1,
            "completion_rate": 0.4,
            "error_rate_trend": 0.15,
            "longest_streak": 10,
        })

        assert isinstance(result["churn_risk"], bool)
        assert 0.0 <= result["probability"] <= 1.0
        assert result["risk_level"] in ("low", "medium", "high", "critical")
        assert len(result["reasoning"]) > 0


# ─── Training Pipeline ────────────────────────────────────────────────────────


@pytest.mark.unit
class TestChurnTraining:

    def test_prepare_data_shapes(self):
        from app.ml.train_churn import prepare_data
        from app.ml.churn_dataset_generator import FEATURE_NAMES
        X_train, X_test, y_train, y_test, scaler = prepare_data(
            n_samples=100, seed=1,
        )
        assert X_train.shape[1] == len(FEATURE_NAMES)
        assert len(X_train) + len(X_test) == 100
        assert set(np.unique(y_train)).issubset({0, 1})

    def test_quick_train(self):
        from sklearn.linear_model import LogisticRegression
        from sklearn.metrics import accuracy_score
        from app.ml.train_churn import prepare_data

        X_train, X_test, y_train, y_test, _ = prepare_data(
            n_samples=200, seed=42,
        )
        model = LogisticRegression(max_iter=200, random_state=42)
        model.fit(X_train, y_train)

        accuracy = accuracy_score(y_test, model.predict(X_test))
        assert accuracy > 0.5, f"Accuracy too low: {accuracy}"


# ─── API Endpoint ─────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestChurnAPI:

    @pytest.mark.asyncio
    async def test_predict_churn_endpoint(self, client):
        response = await client.post("/api/v1/predict-churn", json={
            "user_id": "test-user-001",
            "days_since_last_play": 15,
            "session_frequency": 1.0,
            "avg_session_duration": 10.0,
            "total_games_played": 80,
            "win_rate_trend": -0.05,
            "hint_usage_trend": 0.1,
            "difficulty_variety": 2,
            "completion_rate": 0.6,
            "error_rate_trend": 0.05,
            "longest_streak": 8,
        })
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data["churn_risk"], bool)
        assert 0.0 <= data["probability"] <= 1.0
        assert data["risk_level"] in ("low", "medium", "high", "critical")
        assert len(data["reasoning"]) > 0
