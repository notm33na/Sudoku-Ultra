"""
Tests for adaptive difficulty regression — user dataset, training, inference.
"""

import pytest
import numpy as np


# ─── User Dataset Generator ───────────────────────────────────────────────────


@pytest.mark.unit
class TestUserDatasetGenerator:

    def test_generate_correct_count(self):
        from app.ml.user_dataset_generator import generate_user_dataset
        dataset = generate_user_dataset(n_samples=50, seed=1)
        assert len(dataset) == 50

    def test_balanced_archetypes(self):
        from app.ml.user_dataset_generator import generate_user_dataset
        dataset = generate_user_dataset(n_samples=100, seed=2)
        # 100 / 5 = 20 per archetype
        assert len(dataset) == 100

    def test_all_features_present(self):
        from app.ml.user_dataset_generator import generate_user_dataset, FEATURE_NAMES
        dataset = generate_user_dataset(n_samples=5, seed=3)
        for sample in dataset:
            for feat in FEATURE_NAMES:
                assert feat in sample, f"Missing: {feat}"
            assert "optimal_difficulty_score" in sample

    def test_feature_ranges(self):
        from app.ml.user_dataset_generator import generate_user_dataset
        dataset = generate_user_dataset(n_samples=100, seed=4)
        for sample in dataset:
            assert 0.0 <= sample["hint_rate"] <= 1.0
            assert 0.0 <= sample["error_rate"] <= 1.0
            assert 0.0 <= sample["win_rate"] <= 1.0
            assert sample["session_count"] >= 0
            assert sample["current_streak"] >= 0
            assert 0.0 <= sample["optimal_difficulty_score"] <= 5.0

    def test_reproducible(self):
        from app.ml.user_dataset_generator import generate_user_dataset
        d1 = generate_user_dataset(n_samples=10, seed=99)
        d2 = generate_user_dataset(n_samples=10, seed=99)
        assert d1 == d2

    def test_csv_output(self, tmp_path):
        from app.ml.user_dataset_generator import generate_user_dataset
        import csv
        output = str(tmp_path / "users.csv")
        generate_user_dataset(n_samples=20, output_path=output, seed=5)
        with open(output) as f:
            rows = list(csv.DictReader(f))
        assert len(rows) == 20


# ─── Recommender Inference ─────────────────────────────────────────────────────


@pytest.mark.unit
class TestRecommenderInference:

    def test_fallback_returns_last_played(self):
        from app.services.recommender_service import AdaptiveDifficultyRecommender
        rec = AdaptiveDifficultyRecommender()
        assert not rec.is_loaded

        result = rec.predict({"last_played_difficulty": "hard"})
        assert result["recommended_difficulty"] == "hard"
        assert result["confidence"] == 0.5
        assert "Model not loaded" in result["reasoning"]

    def test_fallback_default(self):
        from app.services.recommender_service import AdaptiveDifficultyRecommender
        rec = AdaptiveDifficultyRecommender()
        result = rec.predict({})
        assert result["recommended_difficulty"] == "easy"

    def test_load_nonexistent(self):
        from pathlib import Path
        from app.services.recommender_service import AdaptiveDifficultyRecommender
        rec = AdaptiveDifficultyRecommender()
        assert not rec.load(Path("/nonexistent"))

    def test_trained_model_inference(self, tmp_path):
        """Full round-trip: train → save → load → predict."""
        import pickle
        from app.ml.train_regression import prepare_data
        from sklearn.ensemble import GradientBoostingRegressor
        from app.services.recommender_service import AdaptiveDifficultyRecommender

        X_train, X_test, y_train, y_test = prepare_data(n_samples=200, seed=42)

        model = GradientBoostingRegressor(n_estimators=10, random_state=42)
        model.fit(X_train, y_train)

        model_path = tmp_path / "adaptive_regression.pkl"
        with open(model_path, "wb") as f:
            pickle.dump(model, f)

        rec = AdaptiveDifficultyRecommender()
        assert rec.load(tmp_path)
        assert rec.is_loaded

        result = rec.predict({
            "avg_solve_time_easy": 30,
            "avg_solve_time_medium": 100,
            "avg_solve_time_hard": 250,
            "hint_rate": 0.02,
            "error_rate": 0.05,
            "current_streak": 20,
            "session_count": 200,
            "last_played_difficulty": "hard",
            "win_rate": 0.85,
        })

        assert result["recommended_difficulty"] in [
            "super_easy", "easy", "medium", "hard", "super_hard", "extreme"
        ]
        assert 0.0 <= result["confidence"] <= 1.0
        assert len(result["reasoning"]) > 0


# ─── Training Pipeline ────────────────────────────────────────────────────────


@pytest.mark.unit
class TestRegressionTraining:

    def test_prepare_data_shapes(self):
        from app.ml.train_regression import prepare_data
        from app.ml.user_dataset_generator import FEATURE_NAMES
        X_train, X_test, y_train, y_test = prepare_data(n_samples=100, seed=1)
        assert X_train.shape[1] == len(FEATURE_NAMES)
        assert len(X_train) + len(X_test) == 100

    def test_quick_train(self):
        from app.ml.train_regression import prepare_data
        from sklearn.ensemble import GradientBoostingRegressor
        from sklearn.metrics import mean_squared_error

        X_train, X_test, y_train, y_test = prepare_data(n_samples=200, seed=42)
        model = GradientBoostingRegressor(n_estimators=10, random_state=42)
        model.fit(X_train, y_train)

        rmse = np.sqrt(mean_squared_error(y_test, model.predict(X_test)))
        assert rmse < 2.0, f"RMSE too high: {rmse}"
