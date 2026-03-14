"""
train_autoencoder.py — Sparse autoencoder for Sudoku anti-cheat anomaly detection.

Architecture (PyTorch):
  Encoder:  10 → 8 → 4 → 2   (ReLU activations)
  Decoder:   2 → 4 → 8 → 10  (ReLU hidden, Sigmoid output for [0,1] features)

Training objective: minimise MSE reconstruction loss on normal session behaviour.
A high reconstruction error at inference time indicates anomalous behaviour.

Outputs (written to ml/models/):
  anomaly_autoencoder.pt    — PyTorch state dict
  anomaly_autoencoder.onnx  — ONNX export for fast inference
  anomaly_meta.json         — threshold + feature stats

Usage:
    from app.ml.train_autoencoder import train_and_save
    meta = train_and_save()
"""

from __future__ import annotations

import json
import math
import pathlib
from typing import Optional

import mlflow
import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset

from app.ml.feature_extractor import (
    FEATURE_DIM,
    generate_normal_features,
    generate_anomalous_features,
)

# ── Paths ─────────────────────────────────────────────────────────────────────

MODELS_DIR = pathlib.Path(__file__).resolve().parents[3] / "ml" / "models"
MODELS_DIR.mkdir(parents=True, exist_ok=True)

PT_PATH = MODELS_DIR / "anomaly_autoencoder.pt"
ONNX_PATH = MODELS_DIR / "anomaly_autoencoder.onnx"
META_PATH = MODELS_DIR / "anomaly_meta.json"

# ── Model Definition ──────────────────────────────────────────────────────────


class SparseAutoencoder(nn.Module):
    """
    Sparse autoencoder with a 2-dimensional bottleneck.

    Sparsity is enforced via L1 regularisation on the encoder output during training.
    """

    def __init__(self, input_dim: int = FEATURE_DIM) -> None:
        super().__init__()
        self.encoder = nn.Sequential(
            nn.Linear(input_dim, 8),
            nn.ReLU(),
            nn.Linear(8, 4),
            nn.ReLU(),
            nn.Linear(4, 2),
            nn.ReLU(),
        )
        self.decoder = nn.Sequential(
            nn.Linear(2, 4),
            nn.ReLU(),
            nn.Linear(4, 8),
            nn.ReLU(),
            nn.Linear(8, input_dim),
            nn.Sigmoid(),  # all features normalised to [0, 1]
        )

    def forward(self, x: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        latent = self.encoder(x)
        recon = self.decoder(latent)
        return recon, latent

    def reconstruct(self, x: torch.Tensor) -> torch.Tensor:
        """ONNX-exportable forward that returns only the reconstruction."""
        recon, _ = self.forward(x)
        return recon


# ── Training ──────────────────────────────────────────────────────────────────


def _mse(recon: torch.Tensor, original: torch.Tensor) -> torch.Tensor:
    return torch.mean((recon - original) ** 2, dim=1)


def train_and_save(
    n_normal: int = 10_000,
    epochs: int = 200,
    batch_size: int = 256,
    lr: float = 1e-3,
    sparsity_weight: float = 1e-4,
    anomaly_threshold_sigma: float = 2.0,
    seed: int = 42,
) -> dict:
    """
    Train the autoencoder on synthetic normal sessions and save artefacts.

    Returns
    -------
    dict with keys: threshold, mean_train_error, std_train_error, auc_roc,
                    pt_path, onnx_path, meta_path.
    """
    torch.manual_seed(seed)
    rng = np.random.default_rng(seed)

    # ── Data ──────────────────────────────────────────────────────────────────
    X_normal = generate_normal_features(n=n_normal, rng=rng)
    X_tensor = torch.from_numpy(X_normal)

    n_val = int(n_normal * 0.1)
    X_train_t = X_tensor[n_val:]
    X_val_t = X_tensor[:n_val]

    train_loader = DataLoader(
        TensorDataset(X_train_t),
        batch_size=batch_size,
        shuffle=True,
    )

    # ── Model ─────────────────────────────────────────────────────────────────
    model = SparseAutoencoder()
    optimiser = torch.optim.Adam(model.parameters(), lr=lr)

    # ── MLflow ────────────────────────────────────────────────────────────────
    mlflow.set_experiment("anomaly_autoencoder")
    with mlflow.start_run(run_name="autoencoder_train"):
        mlflow.log_params(
            {
                "n_normal": n_normal,
                "epochs": epochs,
                "batch_size": batch_size,
                "lr": lr,
                "sparsity_weight": sparsity_weight,
                "threshold_sigma": anomaly_threshold_sigma,
            }
        )

        # ── Training loop ──────────────────────────────────────────────────────
        model.train()
        for epoch in range(epochs):
            epoch_loss = 0.0
            for (batch,) in train_loader:
                optimiser.zero_grad()
                recon, latent = model(batch)
                mse_loss = torch.mean(_mse(recon, batch))
                sparsity_loss = sparsity_weight * torch.mean(torch.abs(latent))
                loss = mse_loss + sparsity_loss
                loss.backward()
                optimiser.step()
                epoch_loss += loss.item()

            if (epoch + 1) % 50 == 0:
                avg = epoch_loss / len(train_loader)
                mlflow.log_metric("train_loss", avg, step=epoch + 1)

        # ── Threshold computation on validation set ────────────────────────────
        model.eval()
        with torch.no_grad():
            val_recon, _ = model(X_val_t)
            val_errors = _mse(val_recon, X_val_t).numpy()

        mean_err = float(np.mean(val_errors))
        std_err = float(np.std(val_errors))
        threshold = mean_err + anomaly_threshold_sigma * std_err

        mlflow.log_metrics(
            {
                "val_mean_error": mean_err,
                "val_std_error": std_err,
                "threshold": threshold,
            }
        )

        # ── Evaluate on anomalous data ─────────────────────────────────────────
        X_anon = generate_anomalous_features(n=500, rng=rng)
        X_anon_t = torch.from_numpy(X_anon)
        with torch.no_grad():
            anon_recon, _ = model(X_anon_t)
            anon_errors = _mse(anon_recon, X_anon_t).numpy()

        true_positives = int(np.sum(anon_errors > threshold))
        detection_rate = true_positives / len(anon_errors)
        val_false_positives = int(np.sum(val_errors > threshold))
        false_positive_rate = val_false_positives / len(val_errors)

        mlflow.log_metrics(
            {
                "detection_rate": detection_rate,
                "false_positive_rate": false_positive_rate,
            }
        )

        # ── Save PyTorch state dict ────────────────────────────────────────────
        torch.save(model.state_dict(), PT_PATH)

        # ── ONNX export ───────────────────────────────────────────────────────
        dummy = torch.zeros(1, FEATURE_DIM)
        torch.onnx.export(
            model,
            dummy,
            str(ONNX_PATH),
            input_names=["features"],
            output_names=["reconstruction", "latent"],
            opset_version=17,
            dynamic_axes={"features": {0: "batch"}, "reconstruction": {0: "batch"}},
        )

        # ── Meta file ─────────────────────────────────────────────────────────
        meta = {
            "threshold": threshold,
            "mean_train_error": mean_err,
            "std_train_error": std_err,
            "detection_rate": detection_rate,
            "false_positive_rate": false_positive_rate,
            "feature_dim": FEATURE_DIM,
            "epochs": epochs,
            "n_train": n_normal - n_val,
        }
        META_PATH.write_text(json.dumps(meta, indent=2))

        mlflow.log_artifact(str(PT_PATH))
        mlflow.log_artifact(str(ONNX_PATH))
        mlflow.log_artifact(str(META_PATH))

    return {
        **meta,
        "pt_path": str(PT_PATH),
        "onnx_path": str(ONNX_PATH),
        "meta_path": str(META_PATH),
    }
