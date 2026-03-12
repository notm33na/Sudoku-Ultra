"""
Player skill clustering — training pipeline.

K-Means clustering on user skill features to segment players into
5 tiers: Beginner, Casual, Intermediate, Advanced, Expert.

Includes elbow method and silhouette score validation.

Usage:
    python -m app.ml.train_clustering
"""

import json
import pickle
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import silhouette_score

from app.ml.skill_dataset_generator import generate_skill_dataset, FEATURE_NAMES, CLUSTER_LABELS

MODEL_DIR = Path("ml/models")
K = 5  # Number of clusters


def prepare_data(
    n_samples: int = 2500,
    seed: int = 42,
) -> tuple[np.ndarray, np.ndarray, StandardScaler]:
    """Generate dataset, scale features."""
    dataset = generate_skill_dataset(n_samples=n_samples, seed=seed)
    df = pd.DataFrame(dataset)
    X = df[FEATURE_NAMES].values

    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    return X, X_scaled, scaler


def elbow_analysis(X_scaled: np.ndarray, max_k: int = 10, seed: int = 42) -> dict[int, float]:
    """Run elbow method — compute inertia for k=2..max_k."""
    inertias = {}
    for k in range(2, max_k + 1):
        km = KMeans(n_clusters=k, random_state=seed, n_init=10)
        km.fit(X_scaled)
        inertias[k] = float(km.inertia_)
    return inertias


def silhouette_analysis(X_scaled: np.ndarray, max_k: int = 10, seed: int = 42) -> dict[int, float]:
    """Compute silhouette score for k=2..max_k."""
    scores = {}
    for k in range(2, max_k + 1):
        km = KMeans(n_clusters=k, random_state=seed, n_init=10)
        labels = km.fit_predict(X_scaled)
        scores[k] = float(silhouette_score(X_scaled, labels))
    return scores


def train_and_save(
    n_samples: int = 2500,
    seed: int = 42,
    use_mlflow: bool = False,
) -> dict:
    """Full training pipeline for skill clustering."""
    print("=" * 60)
    print("PLAYER SKILL CLUSTERING — Training Pipeline")
    print("=" * 60)

    print(f"\n[1/5] Generating {n_samples} user skill profiles...")
    X_raw, X_scaled, scaler = prepare_data(n_samples=n_samples, seed=seed)
    print(f"  Samples: {len(X_raw)}, Features: {X_raw.shape[1]}")

    print("\n[2/5] Elbow analysis (k=2..10)...")
    inertias = elbow_analysis(X_scaled, seed=seed)
    for k, inertia in inertias.items():
        marker = " ← selected" if k == K else ""
        print(f"  k={k:2d}: inertia={inertia:10.1f}{marker}")

    print("\n[3/5] Silhouette analysis (k=2..10)...")
    sil_scores = silhouette_analysis(X_scaled, seed=seed)
    for k, score in sil_scores.items():
        marker = " ← selected" if k == K else ""
        print(f"  k={k:2d}: silhouette={score:.4f}{marker}")

    print(f"\n[4/5] Training K-Means (k={K})...")
    model = KMeans(n_clusters=K, random_state=seed, n_init=10)
    labels = model.fit_predict(X_scaled)
    final_silhouette = float(silhouette_score(X_scaled, labels))
    print(f"  Silhouette score: {final_silhouette:.4f}")

    # Map cluster IDs to skill labels by sorting centroids on avg_solve_time_easy
    centroid_order = np.argsort(model.cluster_centers_[:, 0])[::-1]  # highest solve time = beginner
    label_map = {int(centroid_order[i]): CLUSTER_LABELS[i] for i in range(K)}
    print("  Cluster mapping:")
    for cluster_id, label in sorted(label_map.items()):
        count = int((labels == cluster_id).sum())
        print(f"    Cluster {cluster_id} → {label} ({count} users)")

    # Cluster distribution
    from collections import Counter
    dist = Counter(label_map[l] for l in labels)
    print(f"  Distribution: {dict(sorted(dist.items()))}")

    metrics = {
        "k": K,
        "silhouette_score": final_silhouette,
        "inertia": float(model.inertia_),
        "elbow_inertias": inertias,
        "silhouette_scores": sil_scores,
        "label_map": label_map,
        "cluster_distribution": dict(dist),
    }

    print("\n[5/5] Saving model artifacts...")
    MODEL_DIR.mkdir(parents=True, exist_ok=True)

    model_path = MODEL_DIR / "skill_clustering.pkl"
    scaler_path = MODEL_DIR / "skill_scaler.pkl"
    label_map_path = MODEL_DIR / "cluster_label_map.json"
    metrics_path = MODEL_DIR / "clustering_metrics.json"

    with open(model_path, "wb") as f:
        pickle.dump(model, f)
    with open(scaler_path, "wb") as f:
        pickle.dump(scaler, f)
    with open(label_map_path, "w") as f:
        json.dump({str(k): v for k, v in label_map.items()}, f, indent=2)
    with open(metrics_path, "w") as f:
        json.dump(metrics, f, indent=2, default=str)

    print(f"  Model:     {model_path}")
    print(f"  Scaler:    {scaler_path}")
    print(f"  Label map: {label_map_path}")

    if use_mlflow:
        _log_to_mlflow(model, metrics)

    print(f"\n✅ Training complete — silhouette: {final_silhouette:.4f}")
    return metrics


def _log_to_mlflow(model: KMeans, metrics: dict) -> None:
    try:
        import mlflow
        import mlflow.sklearn

        mlflow.set_experiment("sudoku-ultra-skill-clustering")
        with mlflow.start_run(run_name="kmeans-clustering"):
            mlflow.log_param("k", metrics["k"])
            mlflow.log_metric("silhouette_score", metrics["silhouette_score"])
            mlflow.log_metric("inertia", metrics["inertia"])
            mlflow.sklearn.log_model(model, "model")
        print("  MLflow: logged ✅")
    except Exception as e:
        print(f"  MLflow: skipped ({e})")


if __name__ == "__main__":
    train_and_save(n_samples=2500)
