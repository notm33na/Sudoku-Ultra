"""
Edge AI / ONNX export router.

Provides endpoints to download exported ONNX models and
batch inference for offline sync.
"""

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.services.classifier_service import classifier

router = APIRouter(prefix="/api/v1/edge", tags=["edge-ai"])

MODEL_DIR = Path("ml/models")


class BatchClassifyRequest(BaseModel):
    """Batch classification request for offline sync."""
    puzzles: list[dict[str, float]] = Field(
        ..., min_length=1, max_length=100,
        description="List of feature dicts to classify"
    )


class BatchClassifyResult(BaseModel):
    """Batch classification response."""
    results: list[dict] = Field(..., description="Classification results")
    count: int = Field(..., description="Number of puzzles classified")


@router.get("/models/classifier")
async def download_classifier_model():
    """Download the ONNX classifier model for on-device inference."""
    onnx_path = MODEL_DIR / "classifier.onnx"
    json_path = MODEL_DIR / "classifier.json"

    if onnx_path.exists():
        return FileResponse(
            str(onnx_path),
            media_type="application/octet-stream",
            filename="classifier.onnx",
        )
    elif json_path.exists():
        return FileResponse(
            str(json_path),
            media_type="application/json",
            filename="classifier.json",
        )
    else:
        return {"error": "Model not exported yet. Run: python -m app.ml.export_onnx"}


@router.get("/models/scanner")
async def download_scanner_model():
    """Download the ONNX scanner model for on-device digit recognition."""
    onnx_path = MODEL_DIR / "scanner.onnx"

    if onnx_path.exists():
        return FileResponse(
            str(onnx_path),
            media_type="application/octet-stream",
            filename="scanner.onnx",
        )
    else:
        return {"error": "Scanner model not exported yet. Run: python -m app.ml.export_onnx"}


@router.post("/batch-classify", response_model=BatchClassifyResult)
async def batch_classify(request: BatchClassifyRequest) -> BatchClassifyResult:
    """
    Batch classify puzzles for offline sync.

    Useful when the mobile app comes online after offline play
    and needs to sync difficulty labels for multiple puzzles.
    """
    results = []
    for puzzle_features in request.puzzles:
        result = classifier.predict(puzzle_features)
        results.append(result)

    return BatchClassifyResult(
        results=results,
        count=len(results),
    )


@router.get("/status")
async def edge_ai_status():
    """Check available edge AI models and versions."""
    models = {}

    classifier_onnx = MODEL_DIR / "classifier.onnx"
    classifier_json = MODEL_DIR / "classifier.json"
    scanner_onnx = MODEL_DIR / "scanner.onnx"

    models["classifier"] = {
        "onnx_available": classifier_onnx.exists(),
        "json_available": classifier_json.exists(),
        "size_kb": round(classifier_onnx.stat().st_size / 1024, 1) if classifier_onnx.exists() else None,
    }
    models["scanner"] = {
        "onnx_available": scanner_onnx.exists(),
        "size_kb": round(scanner_onnx.stat().st_size / 1024, 1) if scanner_onnx.exists() else None,
    }

    return {
        "edge_ai_enabled": True,
        "models": models,
    }
