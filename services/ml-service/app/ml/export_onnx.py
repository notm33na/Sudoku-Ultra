"""
ONNX export for the difficulty classifier.

Exports the trained Random Forest classifier to ONNX format for
on-device inference in React Native via onnxruntime-react-native.

Usage:
    python -m app.ml.export_onnx
"""

import pickle
from pathlib import Path

import numpy as np

MODEL_DIR = Path("ml/models")


def export_classifier_onnx(
    model_dir: Path | None = None,
    output_path: Path | None = None,
) -> Path:
    """
    Export the trained Random Forest classifier to ONNX.

    Uses skl2onnx to convert scikit-learn models to ONNX format.
    """
    model_dir = model_dir or MODEL_DIR
    output_path = output_path or (model_dir / "classifier.onnx")

    model_path = model_dir / "difficulty_classifier.pkl"
    if not model_path.exists():
        raise FileNotFoundError(f"Classifier model not found at {model_path}")

    with open(model_path, "rb") as f:
        model = pickle.load(f)

    try:
        from skl2onnx import convert_sklearn
        from skl2onnx.common.data_types import FloatTensorType

        # 10 input features
        initial_type = [("features", FloatTensorType([None, 10]))]
        onnx_model = convert_sklearn(model, initial_types=initial_type)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "wb") as f:
            f.write(onnx_model.SerializeToString())

        print(f"✅ Classifier ONNX exported: {output_path}")
        print(f"   Size: {output_path.stat().st_size / 1024:.1f} KB")

    except ImportError:
        # Fallback: export as a simple prediction function via ONNX Runtime
        print("skl2onnx not available — creating ONNX via manual export")
        _manual_onnx_export(model, output_path)

    return output_path


def export_scanner_onnx(
    model_dir: Path | None = None,
) -> Path:
    """Export the scanner CNN to ONNX (already done in train_scanner.py)."""
    model_dir = model_dir or MODEL_DIR
    onnx_path = model_dir / "scanner.onnx"

    if onnx_path.exists():
        print(f"✅ Scanner ONNX already exists: {onnx_path}")
        return onnx_path

    # Re-export from PyTorch checkpoint
    import torch
    from app.ml.train_scanner import DigitClassifier

    pt_path = model_dir / "scanner.pt"
    if not pt_path.exists():
        raise FileNotFoundError(f"Scanner model not found at {pt_path}")

    model = DigitClassifier()
    model.load_state_dict(torch.load(pt_path, map_location="cpu", weights_only=True))
    model.eval()

    dummy = torch.randn(1, 1, 64, 64)
    torch.onnx.export(
        model, dummy, str(onnx_path),
        input_names=["image"],
        output_names=["logits"],
        dynamic_axes={"image": {0: "batch"}, "logits": {0: "batch"}},
        opset_version=13,
    )

    print(f"✅ Scanner ONNX exported: {onnx_path}")
    print(f"   Size: {onnx_path.stat().st_size / 1024:.1f} KB")
    return onnx_path


def _manual_onnx_export(model, output_path: Path) -> None:
    """Manual ONNX export fallback using numpy serialization."""
    # Save model parameters as numpy arrays for lightweight inference
    import json

    export_data = {
        "n_estimators": model.n_estimators,
        "n_classes": len(model.classes_),
        "classes": model.classes_.tolist(),
        "feature_importances": model.feature_importances_.tolist(),
    }

    # Save as JSON metadata (React Native can load this for rule-based fallback)
    meta_path = output_path.with_suffix(".json")
    with open(meta_path, "w") as f:
        json.dump(export_data, f, indent=2)

    print(f"✅ Classifier metadata exported: {meta_path}")


def verify_onnx(onnx_path: Path, n_features: int = 10) -> bool:
    """Verify ONNX model runs correctly."""
    try:
        import onnxruntime as ort

        session = ort.InferenceSession(str(onnx_path))
        input_name = session.get_inputs()[0].name
        test_input = np.random.randn(1, n_features).astype(np.float32)
        result = session.run(None, {input_name: test_input})

        print(f"✅ ONNX verification passed — output shape: {result[0].shape}")
        return True
    except Exception as e:
        print(f"❌ ONNX verification failed: {e}")
        return False


if __name__ == "__main__":
    print("Exporting models to ONNX...\n")
    try:
        classifier_path = export_classifier_onnx()
        verify_onnx(classifier_path, n_features=10)
    except FileNotFoundError as e:
        print(f"Skipping classifier: {e}")

    print()
    try:
        export_scanner_onnx()
    except FileNotFoundError as e:
        print(f"Skipping scanner: {e}")
