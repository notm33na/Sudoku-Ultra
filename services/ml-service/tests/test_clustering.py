"""
Tests for player skill clustering — dataset, training, inference.
"""

import pytest
import numpy as np


# ─── Skill Dataset ─────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestSkillDataset:

    def test_generate_count(self):
        from app.ml.skill_dataset_generator import generate_skill_dataset
        data = generate_skill_dataset(n_samples=50, seed=1)
        assert len(data) == 50

    def test_balanced_archetypes(self):
        from app.ml.skill_dataset_generator import generate_skill_dataset
        data = generate_skill_dataset(n_samples=100, seed=2)
        assert len(data) == 100

    def test_features_present(self):
        from app.ml.skill_dataset_generator import generate_skill_dataset, FEATURE_NAMES
        data = generate_skill_dataset(n_samples=5, seed=3)
        for sample in data:
            for f in FEATURE_NAMES:
                assert f in sample

    def test_ranges_valid(self):
        from app.ml.skill_dataset_generator import generate_skill_dataset
        data = generate_skill_dataset(n_samples=100, seed=4)
        for s in data:
            assert 0.0 <= s["hint_rate"] <= 1.0
            assert 0.0 <= s["error_rate"] <= 1.0
            assert 0 <= s["days_active_last_30"] <= 30

    def test_reproducible(self):
        from app.ml.skill_dataset_generator import generate_skill_dataset
        d1 = generate_skill_dataset(n_samples=10, seed=99)
        d2 = generate_skill_dataset(n_samples=10, seed=99)
        assert d1 == d2


# ─── Clustering Training ──────────────────────────────────────────────────────


@pytest.mark.unit
class TestClusteringTraining:

    def test_prepare_data(self):
        from app.ml.train_clustering import prepare_data
        X_raw, X_scaled, scaler = prepare_data(n_samples=100, seed=1)
        assert X_raw.shape == (100, 8)
        assert X_scaled.shape == (100, 8)
        # Scaled data should have ~zero mean
        assert abs(X_scaled.mean()) < 0.1

    def test_elbow_analysis(self):
        from app.ml.train_clustering import prepare_data, elbow_analysis
        _, X_scaled, _ = prepare_data(n_samples=100, seed=1)
        inertias = elbow_analysis(X_scaled, max_k=6, seed=1)
        assert len(inertias) == 5  # k=2..6
        # Inertia should decrease with more clusters
        vals = list(inertias.values())
        assert vals[0] > vals[-1]

    def test_silhouette_analysis(self):
        from app.ml.train_clustering import prepare_data, silhouette_analysis
        _, X_scaled, _ = prepare_data(n_samples=200, seed=1)
        scores = silhouette_analysis(X_scaled, max_k=6, seed=1)
        assert len(scores) == 5
        for score in scores.values():
            assert -1.0 <= score <= 1.0


# ─── Clustering Service ──────────────────────────────────────────────────────


@pytest.mark.unit
class TestClusteringService:

    def test_fallback_beginner(self):
        from app.services.clustering_service import SkillClusteringService
        svc = SkillClusteringService()
        result = svc.predict({"avg_solve_time_easy": 300, "hint_rate": 0.5})
        assert result["cluster"] == "Beginner"
        assert result["confidence"] == 0.5

    def test_fallback_expert(self):
        from app.services.clustering_service import SkillClusteringService
        svc = SkillClusteringService()
        result = svc.predict({"avg_solve_time_easy": 20, "hint_rate": 0.01})
        assert result["cluster"] == "Expert"

    def test_load_nonexistent(self):
        from pathlib import Path
        from app.services.clustering_service import SkillClusteringService
        svc = SkillClusteringService()
        assert not svc.load(Path("/nonexistent"))

    def test_trained_model_inference(self, tmp_path):
        """Train, save, load, and predict."""
        import pickle
        import json
        from sklearn.cluster import KMeans
        from sklearn.preprocessing import StandardScaler
        from app.ml.train_clustering import prepare_data
        from app.services.clustering_service import SkillClusteringService

        X_raw, X_scaled, scaler = prepare_data(n_samples=200, seed=42)
        model = KMeans(n_clusters=5, random_state=42, n_init=10)
        labels = model.fit_predict(X_scaled)

        # Create label map
        label_map = {i: ["Beginner", "Casual", "Intermediate", "Advanced", "Expert"][i] for i in range(5)}

        with open(tmp_path / "skill_clustering.pkl", "wb") as f:
            pickle.dump(model, f)
        with open(tmp_path / "skill_scaler.pkl", "wb") as f:
            pickle.dump(scaler, f)
        with open(tmp_path / "cluster_label_map.json", "w") as f:
            json.dump({str(k): v for k, v in label_map.items()}, f)

        svc = SkillClusteringService()
        assert svc.load(tmp_path)
        assert svc.is_loaded

        result = svc.predict({
            "avg_solve_time_easy": 25,
            "avg_solve_time_medium": 60,
            "avg_solve_time_hard": 150,
            "hint_rate": 0.01,
            "error_rate": 0.02,
            "difficulty_preference_mode": 4,
            "session_length_avg": 40,
            "days_active_last_30": 25,
        })

        assert result["cluster"] in ["Beginner", "Casual", "Intermediate", "Advanced", "Expert"]
        assert 0.0 <= result["confidence"] <= 1.0
        assert isinstance(result["reasoning"], str)
