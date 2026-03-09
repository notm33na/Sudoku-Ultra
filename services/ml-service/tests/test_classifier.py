"""
Tests for difficulty classifier — dataset generation, training, inference.
"""

import pytest
import numpy as np

from app.ml.dataset_generator import (
    generate_dataset,
    generate_sample,
    FEATURE_NAMES,
    DIFFICULTY_PROFILES,
)
from app.services.classifier_service import DifficultyClassifier, DIFFICULTY_CLASSES


# ─── Dataset Generator ─────────────────────────────────────────────────────────


@pytest.mark.unit
class TestDatasetGenerator:

    def test_generate_correct_count(self):
        dataset = generate_dataset(n_samples=60, seed=1)
        assert len(dataset) == 60

    def test_balanced_classes(self):
        dataset = generate_dataset(n_samples=600, seed=2)
        from collections import Counter
        dist = Counter(s["difficulty"] for s in dataset)
        assert len(dist) == 6
        for cls in DIFFICULTY_PROFILES:
            assert dist[cls] == 100

    def test_all_features_present(self):
        dataset = generate_dataset(n_samples=6, seed=3)
        for sample in dataset:
            for feat in FEATURE_NAMES:
                assert feat in sample, f"Missing feature: {feat}"
            assert "difficulty" in sample

    def test_feature_ranges_valid(self):
        dataset = generate_dataset(n_samples=100, seed=4)
        for sample in dataset:
            assert 17 <= sample["clue_count"] <= 80
            assert 0.0 <= sample["constraint_density"] <= 1.0
            assert 0.0 <= sample["symmetry_score"] <= 1.0
            assert sample["avg_candidate_count"] >= 0.0
            assert sample["naked_singles"] >= 0
            assert sample["hidden_singles"] >= 0

    def test_cross_feature_constraint(self):
        """naked_singles + hidden_singles should not exceed 81 - clue_count."""
        dataset = generate_dataset(n_samples=500, seed=5)
        for sample in dataset:
            empty_cells = 81 - sample["clue_count"]
            assert sample["naked_singles"] + sample["hidden_singles"] <= empty_cells + 1  # +1 rounding

    def test_reproducible_with_seed(self):
        d1 = generate_dataset(n_samples=10, seed=99)
        d2 = generate_dataset(n_samples=10, seed=99)
        assert d1 == d2

    def test_csv_output(self, tmp_path):
        output = str(tmp_path / "test.csv")
        generate_dataset(n_samples=30, output_path=output, seed=6)
        import csv
        with open(output) as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        assert len(rows) == 30
        assert set(FEATURE_NAMES + ["difficulty"]) == set(rows[0].keys())


# ─── Classifier Inference ──────────────────────────────────────────────────────


@pytest.mark.unit
class TestClassifierInference:

    def test_rule_based_fallback(self):
        clf = DifficultyClassifier()
        assert not clf.is_loaded

        result = clf.predict({"clue_count": 50, "constraint_density": 0.8, "avg_candidate_count": 1.5})
        assert result["difficulty"] == "super_easy"
        assert result["confidence"] == 0.5
        assert "Rule-based fallback" in result["explanation"]
        assert isinstance(result["shap_values"], dict)

    def test_fallback_extreme(self):
        clf = DifficultyClassifier()
        result = clf.predict({"clue_count": 17})
        assert result["difficulty"] == "extreme"

    def test_fallback_medium(self):
        clf = DifficultyClassifier()
        result = clf.predict({"clue_count": 30})
        assert result["difficulty"] == "medium"

    def test_fallback_all_classes(self):
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
            assert result["difficulty"] == expected, (
                f"clue_count={clue_count}: expected {expected}, got {result['difficulty']}"
            )

    def test_load_nonexistent_model(self):
        from pathlib import Path
        clf = DifficultyClassifier()
        assert not clf.load(Path("/nonexistent/path"))
        assert not clf.is_loaded


# ─── Training Pipeline (lightweight) ──────────────────────────────────────────


@pytest.mark.unit
class TestTrainingPipeline:

    def test_prepare_data_shapes(self):
        from app.ml.train_classifier import prepare_data
        X_train, X_test, y_train, y_test, encoder = prepare_data(n_samples=120, seed=1)
        assert X_train.shape[1] == len(FEATURE_NAMES)
        assert len(X_train) + len(X_test) == 120
        assert len(np.unique(y_train)) == 6
        assert set(encoder.classes_) == set(DIFFICULTY_CLASSES)

    def test_quick_train(self, tmp_path):
        """Train with minimal settings to verify pipeline works end-to-end."""
        from app.ml.train_classifier import prepare_data
        from sklearn.ensemble import RandomForestClassifier
        from sklearn.metrics import accuracy_score

        X_train, X_test, y_train, y_test, encoder = prepare_data(n_samples=300, seed=42)
        model = RandomForestClassifier(n_estimators=10, random_state=42)
        model.fit(X_train, y_train)

        accuracy = accuracy_score(y_test, model.predict(X_test))
        assert accuracy > 0.5, f"Accuracy too low: {accuracy}"

    def test_trained_model_with_inference(self, tmp_path):
        """Train a model, save it, load it, and run inference."""
        import pickle
        from app.ml.train_classifier import prepare_data

        X_train, X_test, y_train, y_test, encoder = prepare_data(n_samples=300, seed=42)

        from sklearn.ensemble import RandomForestClassifier
        model = RandomForestClassifier(n_estimators=10, random_state=42)
        model.fit(X_train, y_train)

        # Save
        model_path = tmp_path / "difficulty_classifier.pkl"
        encoder_path = tmp_path / "label_encoder.pkl"
        with open(model_path, "wb") as f:
            pickle.dump(model, f)
        with open(encoder_path, "wb") as f:
            pickle.dump(encoder, f)

        # Load via classifier service
        clf = DifficultyClassifier()
        assert clf.load(tmp_path)
        assert clf.is_loaded

        result = clf.predict({
            "clue_count": 20,
            "naked_singles": 3,
            "hidden_singles": 2,
            "naked_pairs": 5,
            "pointing_pairs": 4,
            "box_line_reduction": 3,
            "backtrack_depth": 8,
            "constraint_density": 0.1,
            "symmetry_score": 0.1,
            "avg_candidate_count": 5.5,
        })

        assert result["difficulty"] in DIFFICULTY_CLASSES
        assert 0.0 <= result["confidence"] <= 1.0
        assert isinstance(result["shap_values"], dict)
        assert len(result["shap_values"]) == len(FEATURE_NAMES)
