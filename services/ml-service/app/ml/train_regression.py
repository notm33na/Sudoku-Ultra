"""
Adaptive difficulty regression — training pipeline.

Trains a Gradient Boosting Regressor to predict the optimal difficulty
score (0–5) for a user based on their gameplay features.

Usage:
    python -m app.ml.train_regression
"""

import json
import pickle
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score

from app.ml.user_dataset_generator import (
    generate_user_dataset,
    FEATURE_NAMES,
    DIFFICULTY_NAMES,
)

MODEL_DIR = Path("ml/models")


def prepare_data(
    n_samples: int = 5000,
    test_size: float = 0.2,
    seed: int = 42,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Generate user dataset and split into train/test."""
    dataset = generate_user_dataset(n_samples=n_samples, seed=seed)
    df = pd.DataFrame(dataset)

    X = df[FEATURE_NAMES].values
    y = df["optimal_difficulty_score"].values

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=test_size, random_state=seed,
    )
    return X_train, X_test, y_train, y_test


def train_with_optuna(
    X_train: np.ndarray,
    y_train: np.ndarray,
    X_test: np.ndarray,
    y_test: np.ndarray,
    n_trials: int = 40,
    seed: int = 42,
) -> tuple[GradientBoostingRegressor, dict]:
    """Hyperparameter tuning with Optuna for GBR."""
    import optuna

    optuna.logging.set_verbosity(optuna.logging.WARNING)

    def objective(trial: optuna.Trial) -> float:
        params = {
            "n_estimators": trial.suggest_int("n_estimators", 50, 400),
            "max_depth": trial.suggest_int("max_depth", 3, 15),
            "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.3, log=True),
            "min_samples_split": trial.suggest_int("min_samples_split", 2, 20),
            "min_samples_leaf": trial.suggest_int("min_samples_leaf", 1, 10),
            "subsample": trial.suggest_float("subsample", 0.6, 1.0),
            "random_state": seed,
        }
        reg = GradientBoostingRegressor(**params)
        scores = cross_val_score(reg, X_train, y_train, cv=5, scoring="neg_mean_squared_error")
        return scores.mean()

    study = optuna.create_study(
        direction="maximize",
        study_name="adaptive-difficulty",
        sampler=optuna.samplers.TPESampler(seed=seed),
    )
    study.optimize(objective, n_trials=n_trials)

    best_params = study.best_params
    best_params["random_state"] = seed

    best_model = GradientBoostingRegressor(**best_params)
    best_model.fit(X_train, y_train)

    y_pred = best_model.predict(X_test)
    metrics = {
        "best_cv_neg_mse": study.best_value,
        "test_rmse": float(np.sqrt(mean_squared_error(y_test, y_pred))),
        "test_mae": float(mean_absolute_error(y_test, y_pred)),
        "test_r2": float(r2_score(y_test, y_pred)),
        "best_params": best_params,
        "n_trials": n_trials,
    }

    return best_model, metrics


def train_and_save(
    n_samples: int = 5000,
    n_trials: int = 40,
    seed: int = 42,
    use_mlflow: bool = False,
) -> dict:
    """Full training pipeline for adaptive difficulty regression."""
    print("=" * 60)
    print("ADAPTIVE DIFFICULTY REGRESSION — Training Pipeline")
    print("=" * 60)

    print(f"\n[1/4] Generating {n_samples} user profiles...")
    X_train, X_test, y_train, y_test = prepare_data(n_samples=n_samples, seed=seed)
    print(f"  Train: {len(X_train)}, Test: {len(X_test)}")

    print(f"\n[2/4] Running Optuna ({n_trials} trials)...")
    model, metrics = train_with_optuna(
        X_train, y_train, X_test, y_test, n_trials=n_trials, seed=seed,
    )
    print(f"  RMSE: {metrics['test_rmse']:.4f}")
    print(f"  MAE:  {metrics['test_mae']:.4f}")
    print(f"  R²:   {metrics['test_r2']:.4f}")

    print("\n[3/4] Feature importance:")
    importances = dict(zip(FEATURE_NAMES, model.feature_importances_))
    for feat, imp in sorted(importances.items(), key=lambda x: -x[1]):
        print(f"  {feat:30s}: {imp:.4f}")
    metrics["feature_importances"] = importances

    print("\n[4/4] Saving model artifacts...")
    MODEL_DIR.mkdir(parents=True, exist_ok=True)

    model_path = MODEL_DIR / "adaptive_regression.pkl"
    metrics_path = MODEL_DIR / "regression_metrics.json"

    with open(model_path, "wb") as f:
        pickle.dump(model, f)
    with open(metrics_path, "w") as f:
        json.dump(metrics, f, indent=2, default=str)

    print(f"  Model:   {model_path}")
    print(f"  Metrics: {metrics_path}")

    if use_mlflow:
        _log_to_mlflow(model, metrics)

    print(f"\n✅ Training complete — RMSE: {metrics['test_rmse']:.4f}, R²: {metrics['test_r2']:.4f}")
    return metrics


def _log_to_mlflow(model: GradientBoostingRegressor, metrics: dict) -> None:
    """Log to MLflow."""
    try:
        import mlflow
        import mlflow.sklearn

        mlflow.set_experiment("sudoku-ultra-adaptive-difficulty")
        with mlflow.start_run(run_name="gbr-regression"):
            for k, v in metrics.get("best_params", {}).items():
                mlflow.log_param(k, v)
            mlflow.log_metric("test_rmse", metrics["test_rmse"])
            mlflow.log_metric("test_mae", metrics["test_mae"])
            mlflow.log_metric("test_r2", metrics["test_r2"])
            mlflow.sklearn.log_model(model, "model")
            mlflow.register_model(
                f"runs:/{mlflow.active_run().info.run_id}/model",
                "adaptive-difficulty",
            )
        print("  MLflow: logged and registered ✅")
    except Exception as e:
        print(f"  MLflow: skipped ({e})")


if __name__ == "__main__":
    train_and_save(n_samples=5000, n_trials=40, use_mlflow=False)
