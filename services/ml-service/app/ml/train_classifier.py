"""
Difficulty classifier — training pipeline.

Trains a Random Forest classifier with Optuna hyperparameter tuning,
SHAP explanations, and MLflow experiment tracking.

Usage:
    python -m app.ml.train_classifier
"""

import os
import json
import pickle
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.metrics import classification_report, accuracy_score, confusion_matrix
from sklearn.preprocessing import LabelEncoder

from app.ml.dataset_generator import generate_dataset, FEATURE_NAMES

# ─── Constants ─────────────────────────────────────────────────────────────────

DIFFICULTY_CLASSES = ["super_easy", "easy", "medium", "hard", "super_hard", "extreme"]
MODEL_DIR = Path("ml/models")
DATA_DIR = Path("data")


# ─── Training Pipeline ────────────────────────────────────────────────────────


def prepare_data(
    n_samples: int = 10000,
    test_size: float = 0.2,
    seed: int = 42,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, LabelEncoder]:
    """Generate dataset and split into train/test."""
    dataset = generate_dataset(n_samples=n_samples, seed=seed)
    df = pd.DataFrame(dataset)

    X = df[FEATURE_NAMES].values
    label_encoder = LabelEncoder()
    label_encoder.fit(DIFFICULTY_CLASSES)
    y = label_encoder.transform(df["difficulty"].values)

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=test_size, random_state=seed, stratify=y,
    )
    return X_train, X_test, y_train, y_test, label_encoder


def train_with_optuna(
    X_train: np.ndarray,
    y_train: np.ndarray,
    X_test: np.ndarray,
    y_test: np.ndarray,
    n_trials: int = 50,
    seed: int = 42,
) -> tuple[RandomForestClassifier, dict]:
    """
    Hyperparameter tuning with Optuna.

    Searches over: n_estimators, max_depth, min_samples_split, min_samples_leaf,
    max_features.
    """
    import optuna

    optuna.logging.set_verbosity(optuna.logging.WARNING)

    def objective(trial: optuna.Trial) -> float:
        params = {
            "n_estimators": trial.suggest_int("n_estimators", 50, 500),
            "max_depth": trial.suggest_int("max_depth", 5, 50),
            "min_samples_split": trial.suggest_int("min_samples_split", 2, 20),
            "min_samples_leaf": trial.suggest_int("min_samples_leaf", 1, 10),
            "max_features": trial.suggest_categorical("max_features", ["sqrt", "log2", None]),
            "random_state": seed,
            "n_jobs": -1,
        }
        clf = RandomForestClassifier(**params)

        # 5-fold CV for robust evaluation
        scores = cross_val_score(clf, X_train, y_train, cv=5, scoring="accuracy", n_jobs=-1)
        return scores.mean()

    study = optuna.create_study(
        direction="maximize",
        study_name="difficulty-classifier",
        sampler=optuna.samplers.TPESampler(seed=seed),
    )
    study.optimize(objective, n_trials=n_trials)

    # Train final model with best params
    best_params = study.best_params
    best_params["random_state"] = seed
    best_params["n_jobs"] = -1

    best_model = RandomForestClassifier(**best_params)
    best_model.fit(X_train, y_train)

    # Evaluation
    y_pred = best_model.predict(X_test)
    accuracy = accuracy_score(y_test, y_pred)

    metrics = {
        "best_cv_score": study.best_value,
        "test_accuracy": accuracy,
        "best_params": best_params,
        "n_trials": n_trials,
    }

    return best_model, metrics


def compute_shap_values(
    model: RandomForestClassifier,
    X_sample: np.ndarray,
) -> np.ndarray:
    """Compute SHAP values for a sample of data."""
    import shap

    explainer = shap.TreeExplainer(model)
    shap_values = explainer.shap_values(X_sample)
    return shap_values


def train_and_save(
    n_samples: int = 10000,
    n_trials: int = 50,
    seed: int = 42,
    use_mlflow: bool = False,
) -> dict:
    """
    Full training pipeline: generate data → tune → train → evaluate → save.

    Returns metrics dict.
    """
    print("=" * 60)
    print("DIFFICULTY CLASSIFIER — Training Pipeline")
    print("=" * 60)

    # 1. Prepare data
    print(f"\n[1/5] Generating {n_samples} synthetic puzzles...")
    X_train, X_test, y_train, y_test, label_encoder = prepare_data(
        n_samples=n_samples, seed=seed,
    )
    print(f"  Train: {len(X_train)}, Test: {len(X_test)}")

    # 2. Hyperparameter tuning
    print(f"\n[2/5] Running Optuna ({n_trials} trials)...")
    model, metrics = train_with_optuna(
        X_train, y_train, X_test, y_test, n_trials=n_trials, seed=seed,
    )
    print(f"  Best CV accuracy: {metrics['best_cv_score']:.4f}")
    print(f"  Test accuracy:    {metrics['test_accuracy']:.4f}")
    print(f"  Best params: {json.dumps(metrics['best_params'], indent=2, default=str)}")

    # 3. Classification report
    print("\n[3/5] Classification report:")
    y_pred = model.predict(X_test)
    report = classification_report(
        y_test, y_pred,
        target_names=label_encoder.classes_,
        output_dict=True,
    )
    print(classification_report(y_test, y_pred, target_names=label_encoder.classes_))
    metrics["classification_report"] = report

    # 4. Feature importance
    print("[4/5] Feature importance:")
    importances = dict(zip(FEATURE_NAMES, model.feature_importances_))
    for feat, imp in sorted(importances.items(), key=lambda x: -x[1]):
        print(f"  {feat:25s}: {imp:.4f}")
    metrics["feature_importances"] = importances

    # 5. Save model + artifacts
    print("\n[5/5] Saving model artifacts...")
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    model_path = MODEL_DIR / "difficulty_classifier.pkl"
    encoder_path = MODEL_DIR / "label_encoder.pkl"
    metrics_path = MODEL_DIR / "classifier_metrics.json"

    with open(model_path, "wb") as f:
        pickle.dump(model, f)
    with open(encoder_path, "wb") as f:
        pickle.dump(label_encoder, f)

    # Save metrics (convert numpy types for JSON)
    serializable_metrics = {
        k: (v if not isinstance(v, np.floating) else float(v))
        for k, v in metrics.items()
    }
    with open(metrics_path, "w") as f:
        json.dump(serializable_metrics, f, indent=2, default=str)

    print(f"  Model:   {model_path}")
    print(f"  Encoder: {encoder_path}")
    print(f"  Metrics: {metrics_path}")

    # MLflow tracking (optional)
    if use_mlflow:
        _log_to_mlflow(model, metrics, model_path)

    print(f"\n✅ Training complete — accuracy: {metrics['test_accuracy']:.4f}")
    return metrics


def _log_to_mlflow(model: RandomForestClassifier, metrics: dict, model_path: Path) -> None:
    """Log training run to MLflow."""
    try:
        import mlflow
        import mlflow.sklearn

        mlflow.set_experiment("sudoku-ultra-difficulty-classifier")
        with mlflow.start_run(run_name="rf-classifier"):
            # Log params
            for k, v in metrics.get("best_params", {}).items():
                mlflow.log_param(k, v)
            # Log metrics
            mlflow.log_metric("test_accuracy", metrics["test_accuracy"])
            mlflow.log_metric("cv_score", metrics["best_cv_score"])
            # Log model
            mlflow.sklearn.log_model(model, "model")
            # Register model
            mlflow.register_model(
                f"runs:/{mlflow.active_run().info.run_id}/model",
                "difficulty-classifier",
            )
        print("  MLflow: logged and registered ✅")
    except Exception as e:
        print(f"  MLflow: skipped ({e})")


if __name__ == "__main__":
    train_and_save(n_samples=10000, n_trials=50, use_mlflow=False)
