"""
MobileNetV2-based digit classifier training pipeline.

Fine-tunes a MobileNetV2 backbone on synthetic digit images (0–9)
for Sudoku cell recognition. Exports to ONNX for serving.

Usage:
    python -m app.ml.train_scanner
"""

import json
import pickle
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader, TensorDataset

from app.ml.digit_dataset import generate_digit_dataset
from app.logging import setup_logging

logger = setup_logging()

MODEL_DIR = Path("ml/models")
NUM_CLASSES = 10  # 0=empty, 1–9=digits


class DigitClassifier(nn.Module):
    """Lightweight CNN for digit classification (no pretrained weights needed)."""

    def __init__(self, num_classes: int = NUM_CLASSES):
        super().__init__()
        self.features = nn.Sequential(
            # Block 1: 64→32
            nn.Conv2d(1, 32, 3, padding=1),
            nn.BatchNorm2d(32),
            nn.ReLU(inplace=True),
            nn.MaxPool2d(2),
            # Block 2: 32→16
            nn.Conv2d(32, 64, 3, padding=1),
            nn.BatchNorm2d(64),
            nn.ReLU(inplace=True),
            nn.MaxPool2d(2),
            # Block 3: 16→8
            nn.Conv2d(64, 128, 3, padding=1),
            nn.BatchNorm2d(128),
            nn.ReLU(inplace=True),
            nn.MaxPool2d(2),
            # Block 4: 8→4
            nn.Conv2d(128, 128, 3, padding=1),
            nn.BatchNorm2d(128),
            nn.ReLU(inplace=True),
            nn.AdaptiveAvgPool2d(4),
        )
        self.classifier = nn.Sequential(
            nn.Dropout(0.3),
            nn.Linear(128 * 4 * 4, 256),
            nn.ReLU(inplace=True),
            nn.Dropout(0.2),
            nn.Linear(256, num_classes),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = self.features(x)
        x = x.view(x.size(0), -1)
        x = self.classifier(x)
        return x


def prepare_data(
    samples_per_class: int = 500,
    val_split: float = 0.2,
    seed: int = 42,
) -> tuple[DataLoader, DataLoader]:
    """Generate digit dataset and create DataLoaders."""
    images, labels = generate_digit_dataset(
        samples_per_class=samples_per_class, seed=seed,
    )

    # Normalize to [0, 1] and add channel dimension
    X = images.astype(np.float32) / 255.0
    X = X[:, np.newaxis, :, :]  # (N, 1, 64, 64)
    y = labels.astype(np.int64)

    # Split
    n = len(X)
    n_val = int(n * val_split)
    indices = np.random.RandomState(seed).permutation(n)
    val_idx, train_idx = indices[:n_val], indices[n_val:]

    train_ds = TensorDataset(
        torch.from_numpy(X[train_idx]),
        torch.from_numpy(y[train_idx]),
    )
    val_ds = TensorDataset(
        torch.from_numpy(X[val_idx]),
        torch.from_numpy(y[val_idx]),
    )

    train_loader = DataLoader(train_ds, batch_size=64, shuffle=True)
    val_loader = DataLoader(val_ds, batch_size=64, shuffle=False)

    return train_loader, val_loader


def train_model(
    epochs: int = 15,
    samples_per_class: int = 500,
    lr: float = 0.001,
    seed: int = 42,
) -> tuple[DigitClassifier, dict]:
    """Train the digit classifier."""
    torch.manual_seed(seed)
    np.random.seed(seed)

    print("=" * 60)
    print("DIGIT CLASSIFIER — Training Pipeline")
    print("=" * 60)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"\nDevice: {device}")

    print(f"\n[1/4] Generating {samples_per_class * 10} digit images...")
    train_loader, val_loader = prepare_data(
        samples_per_class=samples_per_class, seed=seed,
    )
    print(f"  Train: {len(train_loader.dataset)}, Val: {len(val_loader.dataset)}")

    print(f"\n[2/4] Training ({epochs} epochs)...")
    model = DigitClassifier().to(device)
    criterion = nn.CrossEntropyLoss()
    optimizer = optim.Adam(model.parameters(), lr=lr)
    scheduler = optim.lr_scheduler.ReduceLROnPlateau(optimizer, patience=3, factor=0.5)

    best_val_acc = 0.0
    best_state = None
    patience_counter = 0

    for epoch in range(epochs):
        # Train
        model.train()
        train_loss = 0.0
        train_correct = 0
        for X_batch, y_batch in train_loader:
            X_batch, y_batch = X_batch.to(device), y_batch.to(device)
            optimizer.zero_grad()
            outputs = model(X_batch)
            loss = criterion(outputs, y_batch)
            loss.backward()
            optimizer.step()
            train_loss += loss.item() * len(y_batch)
            train_correct += (outputs.argmax(1) == y_batch).sum().item()

        # Validate
        model.eval()
        val_loss = 0.0
        val_correct = 0
        with torch.no_grad():
            for X_batch, y_batch in val_loader:
                X_batch, y_batch = X_batch.to(device), y_batch.to(device)
                outputs = model(X_batch)
                loss = criterion(outputs, y_batch)
                val_loss += loss.item() * len(y_batch)
                val_correct += (outputs.argmax(1) == y_batch).sum().item()

        train_acc = train_correct / len(train_loader.dataset)
        val_acc = val_correct / len(val_loader.dataset)
        scheduler.step(val_loss)

        print(f"  Epoch {epoch + 1:2d}/{epochs}: "
              f"train_acc={train_acc:.4f}, val_acc={val_acc:.4f}")

        # Early stopping
        if val_acc > best_val_acc:
            best_val_acc = val_acc
            best_state = model.state_dict().copy()
            patience_counter = 0
        else:
            patience_counter += 1
            if patience_counter >= 5:
                print(f"  Early stopping at epoch {epoch + 1}")
                break

    if best_state:
        model.load_state_dict(best_state)

    metrics = {
        "best_val_accuracy": best_val_acc,
        "epochs_trained": epoch + 1,
        "samples_per_class": samples_per_class,
    }

    return model, metrics


def export_onnx(model: DigitClassifier, output_path: Path) -> None:
    """Export model to ONNX format."""
    model.eval()
    dummy = torch.randn(1, 1, 64, 64)
    torch.onnx.export(
        model, dummy, str(output_path),
        input_names=["image"],
        output_names=["logits"],
        dynamic_axes={"image": {0: "batch"}, "logits": {0: "batch"}},
        opset_version=13,
    )
    print(f"  ONNX exported: {output_path}")


def train_and_save(
    epochs: int = 15,
    samples_per_class: int = 500,
    seed: int = 42,
    use_mlflow: bool = False,
) -> dict:
    """Full training + export pipeline."""
    model, metrics = train_model(
        epochs=epochs, samples_per_class=samples_per_class, seed=seed,
    )

    print("\n[3/4] Saving model artifacts...")
    MODEL_DIR.mkdir(parents=True, exist_ok=True)

    # Save PyTorch
    torch_path = MODEL_DIR / "scanner.pt"
    torch.save(model.state_dict(), torch_path)
    print(f"  PyTorch: {torch_path}")

    # Export ONNX
    onnx_path = MODEL_DIR / "scanner.onnx"
    export_onnx(model, onnx_path)

    # Save metrics
    metrics_path = MODEL_DIR / "scanner_metrics.json"
    with open(metrics_path, "w") as f:
        json.dump(metrics, f, indent=2)
    print(f"  Metrics: {metrics_path}")

    print(f"\n[4/4] ✅ Training complete — val accuracy: {metrics['best_val_accuracy']:.4f}")
    return metrics


if __name__ == "__main__":
    train_and_save(epochs=15, samples_per_class=500)
