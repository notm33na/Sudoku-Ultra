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


def export_clustering_onnx(
    model_dir: Path | None = None,
    output_path: Path | None = None,
) -> Path:
    """
    Export the trained K-Means clustering model to ONNX.

    The clustering model is a scikit-learn Pipeline (StandardScaler + KMeans).
    Converts via skl2onnx; output node is the cluster label (int64).
    """
    model_dir = model_dir or MODEL_DIR
    output_path = output_path or (model_dir / "clustering.onnx")

    # Try pipeline first, then bare KMeans + separate scaler
    pipeline_path = model_dir / "skill_clustering_pipeline.pkl"
    model_path = model_dir / "skill_clustering.pkl"
    scaler_path = model_dir / "clustering_scaler.pkl"

    if pipeline_path.exists():
        with open(pipeline_path, "rb") as f:
            pipeline = pickle.load(f)
        n_features = pipeline.named_steps["kmeans"].cluster_centers_.shape[1]
    elif model_path.exists():
        with open(model_path, "rb") as f:
            kmeans = pickle.load(f)
        n_features = kmeans.cluster_centers_.shape[1]

        if scaler_path.exists():
            from sklearn.pipeline import Pipeline as SKPipeline
            from sklearn.preprocessing import StandardScaler
            with open(scaler_path, "rb") as f:
                scaler = pickle.load(f)
            pipeline = SKPipeline([("scaler", scaler), ("kmeans", kmeans)])
        else:
            from sklearn.pipeline import Pipeline as SKPipeline
            pipeline = SKPipeline([("kmeans", kmeans)])
    else:
        raise FileNotFoundError(
            f"Clustering model not found — expected {pipeline_path} or {model_path}"
        )

    from skl2onnx import convert_sklearn
    from skl2onnx.common.data_types import FloatTensorType

    initial_type = [("features", FloatTensorType([None, n_features]))]
    onnx_model = convert_sklearn(pipeline, initial_types=initial_type)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "wb") as f:
        f.write(onnx_model.SerializeToString())

    print(f"✅ Clustering ONNX exported: {output_path}")
    print(f"   Features: {n_features}  Size: {output_path.stat().st_size / 1024:.1f} KB")
    return output_path


def export_scanner_tflite(
    model_dir: Path | None = None,
) -> Path | None:
    """
    Export the scanner CNN to TFLite for iOS on-device inference.

    Requires: pip install onnx2tf
    onnx2tf converts the scanner.onnx to a TFLite flatbuffer in ml/models/.

    Returns the .tflite path, or None if onnx2tf is not available.
    """
    model_dir = model_dir or MODEL_DIR
    onnx_path = model_dir / "scanner.onnx"
    tflite_path = model_dir / "scanner.tflite"

    if tflite_path.exists():
        print(f"✅ Scanner TFLite already exists: {tflite_path}")
        return tflite_path

    if not onnx_path.exists():
        print(f"⚠ scanner.onnx not found — run export_scanner_onnx() first")
        return None

    try:
        import onnx2tf  # pip install onnx2tf

        print(f"Converting {onnx_path} → TFLite via onnx2tf...")
        onnx2tf.convert(
            input_onnx_file_path=str(onnx_path),
            output_folder_path=str(model_dir / "_tflite_tmp"),
            output_tfv1_pb=False,
            output_saved_model=False,
            output_keras_v3=False,
            output_integer_quant_type="int8",  # quantise for mobile
            quant_type="per-tensor",
            not_use_onnxsim=False,
            verbosity="error",
        )
        # onnx2tf places the .tflite in the output folder
        import shutil
        tmp_dir = model_dir / "_tflite_tmp"
        candidates = list(tmp_dir.glob("*.tflite"))
        if candidates:
            shutil.move(str(candidates[0]), str(tflite_path))
            shutil.rmtree(str(tmp_dir), ignore_errors=True)
            print(f"✅ Scanner TFLite exported: {tflite_path}")
            print(f"   Size: {tflite_path.stat().st_size / 1024:.1f} KB")
            return tflite_path
        else:
            print("❌ onnx2tf ran but produced no .tflite file")
            return None

    except ImportError:
        print(
            "⚠ onnx2tf not installed — TFLite export skipped.\n"
            "  Install with: pip install onnx2tf\n"
            "  The app uses scanner.onnx via onnxruntime-react-native as primary path."
        )
        return None
    except Exception as e:
        print(f"❌ TFLite export failed: {e}")
        return None


if __name__ == "__main__":
    print("Exporting models to ONNX + TFLite...\n")
    try:
        classifier_path = export_classifier_onnx()
        verify_onnx(classifier_path, n_features=10)
    except FileNotFoundError as e:
        print(f"Skipping classifier: {e}")

    print()
    try:
        clustering_path = export_clustering_onnx()
        verify_onnx(clustering_path, n_features=8)
    except (FileNotFoundError, ImportError) as e:
        print(f"Skipping clustering: {e}")

    print()
    try:
        scanner_path = export_scanner_onnx()
        print()
        export_scanner_tflite()  # optional — requires onnx2tf
    except FileNotFoundError as e:
        print(f"Skipping scanner: {e}")
