"""
Churn predictor — training pipeline.

Trains a Logistic Regression classifier to predict user churn (binary)
from engagement features. Uses Optuna hyperparameter tuning,
ROC-AUC scoring, and optional MLflow tracking.

Usage:
    python -m app.ml.train_churn
"""

import json
import pickle
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.metrics import (
    accuracy_score,
    precision_score,
    recall_score,
    f1_score,
    roc_auc_score,
    classification_report,
)
from sklearn.preprocessing import StandardScaler

from app.ml.churn_dataset_generator import generate_churn_dataset, FEATURE_NAMES
from app.logging import setup_logging

logger = setup_logging()

MODEL_DIR = Path("ml/models")


# ─── Training Pipeline ────────────────────────────────────────────────────────


def prepare_data(
    n_samples: int = 5000,
    test_size: float = 0.2,
    seed: int = 42,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, StandardScaler]:
    """Generate churn dataset, scale features, and split into train/test."""
    dataset = generate_churn_dataset(n_samples=n_samples, seed=seed)
    df = pd.DataFrame(dataset)

    X = df[FEATURE_NAMES].values
    y = df["churned"].values.astype(np.int64)

    # Scale features for Logistic Regression
    scaler = StandardScaler()
    X = scaler.fit_transform(X)

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=test_size, random_state=seed, stratify=y,
    )
    return X_train, X_test, y_train, y_test, scaler


def train_with_optuna(
    X_train: np.ndarray,
    y_train: np.ndarray,
    X_test: np.ndarray,
    y_test: np.ndarray,
    n_trials: int = 40,
    seed: int = 42,
) -> tuple[LogisticRegression, dict]:
    """Hyperparameter tuning with Optuna for Logistic Regression."""
    import optuna

    optuna.logging.set_verbosity(optuna.logging.WARNING)

    def objective(trial: optuna.Trial) -> float:
        C = trial.suggest_float("C", 0.001, 100.0, log=True)
        penalty = trial.suggest_categorical("penalty", ["l1", "l2"])
        solver = "saga" if penalty == "l1" else trial.suggest_categorical(
            "solver", ["lbfgs", "saga"],
        )

        clf = LogisticRegression(
            C=C,
            penalty=penalty,
            solver=solver,
            max_iter=1000,
            random_state=seed,
            n_jobs=-1,
        )
        scores = cross_val_score(
            clf, X_train, y_train, cv=5, scoring="roc_auc", n_jobs=-1,
        )
        return scores.mean()

    study = optuna.create_study(
        direction="maximize",
        study_name="churn-predictor",
        sampler=optuna.samplers.TPESampler(seed=seed),
    )
    study.optimize(objective, n_trials=n_trials)

    # Train final model with best params
    best_params = study.best_params
    solver = best_params.pop("solver", None)
    if best_params.get("penalty") == "l1":
        solver = "saga"
    elif solver is None:
        solver = "lbfgs"

    best_model = LogisticRegression(
        **best_params,
        solver=solver,
        max_iter=1000,
        random_state=seed,
        n_jobs=-1,
    )
    best_model.fit(X_train, y_train)

    # Evaluation
    y_pred = best_model.predict(X_test)
    y_proba = best_model.predict_proba(X_test)[:, 1]

    metrics = {
        "best_cv_auc": study.best_value,
        "test_accuracy": float(accuracy_score(y_test, y_pred)),
        "test_precision": float(precision_score(y_test, y_pred)),
        "test_recall": float(recall_score(y_test, y_pred)),
        "test_f1": float(f1_score(y_test, y_pred)),
        "test_auc_roc": float(roc_auc_score(y_test, y_proba)),
        "best_params": {**best_params, "solver": solver},
        "n_trials": n_trials,
    }

    return best_model, metrics


def train_and_save(
    n_samples: int = 5000,
    n_trials: int = 40,
    seed: int = 42,
    use_mlflow: bool = False,
) -> dict:
    """Full training pipeline: generate data → tune → train → evaluate → save."""
    print("=" * 60)
    print("CHURN PREDICTOR — Training Pipeline")
    print("=" * 60)

    # 1. Prepare data
    print(f"\n[1/4] Generating {n_samples} engagement profiles...")
    X_train, X_test, y_train, y_test, scaler = prepare_data(
        n_samples=n_samples, seed=seed,
    )
    print(f"  Train: {len(X_train)}, Test: {len(X_test)}")
    print(f"  Churn rate (train): {y_train.mean():.2%}")

    # 2. Hyperparameter tuning
    print(f"\n[2/4] Running Optuna ({n_trials} trials)...")
    model, metrics = train_with_optuna(
        X_train, y_train, X_test, y_test, n_trials=n_trials, seed=seed,
    )
    print(f"  Best CV AUC:  {metrics['best_cv_auc']:.4f}")
    print(f"  Test AUC-ROC: {metrics['test_auc_roc']:.4f}")
    print(f"  Test F1:      {metrics['test_f1']:.4f}")

    # 3. Classification report
    print("\n[3/4] Classification report:")
    y_pred = model.predict(X_test)
    print(classification_report(y_test, y_pred, target_names=["active", "churned"]))

    # Feature importance (coefficients)
    print("  Feature coefficients:")
    coefs = dict(zip(FEATURE_NAMES, model.coef_[0]))
    for feat, coef in sorted(coefs.items(), key=lambda x: abs(x[1]), reverse=True):
        print(f"    {feat:30s}: {coef:+.4f}")
    metrics["feature_coefficients"] = {k: round(float(v), 4) for k, v in coefs.items()}

    # 4. Save model + artifacts
    print("\n[4/4] Saving model artifacts...")
    MODEL_DIR.mkdir(parents=True, exist_ok=True)

    model_path = MODEL_DIR / "churn_predictor.pkl"
    scaler_path = MODEL_DIR / "churn_scaler.pkl"
    metrics_path = MODEL_DIR / "churn_metrics.json"

    with open(model_path, "wb") as f:
        pickle.dump(model, f)
    with open(scaler_path, "wb") as f:
        pickle.dump(scaler, f)
    with open(metrics_path, "w") as f:
        json.dump(metrics, f, indent=2, default=str)

    print(f"  Model:   {model_path}")
    print(f"  Scaler:  {scaler_path}")
    print(f"  Metrics: {metrics_path}")

    # MLflow tracking (optional)
    if use_mlflow:
        _log_to_mlflow(model, metrics)

    print(f"\n✅ Training complete — AUC-ROC: {metrics['test_auc_roc']:.4f}")
    return metrics


def _log_to_mlflow(model: LogisticRegression, metrics: dict) -> None:
    """Log training run to MLflow."""
    try:
        import mlflow
        import mlflow.sklearn

        mlflow.set_experiment("sudoku-ultra-churn-predictor")
        with mlflow.start_run(run_name="lr-churn"):
            for k, v in metrics.get("best_params", {}).items():
                mlflow.log_param(k, v)
            mlflow.log_metric("test_auc_roc", metrics["test_auc_roc"])
            mlflow.log_metric("test_f1", metrics["test_f1"])
            mlflow.log_metric("test_accuracy", metrics["test_accuracy"])
            mlflow.sklearn.log_model(model, "model")
            mlflow.register_model(
                f"runs:/{mlflow.active_run().info.run_id}/model",
                "churn-predictor",
            )
        print("  MLflow: logged and registered ✅")
    except Exception as e:
        print(f"  MLflow: skipped ({e})")


if __name__ == "__main__":
    train_and_save(n_samples=5000, n_trials=40, use_mlflow=False)
