"""
Puzzle scanning router.

Receives an image and returns extracted 9x9 grid using
OpenCV preprocessing + CNN digit recognition.
"""

from fastapi import APIRouter, UploadFile, File
from pydantic import BaseModel, Field

from app.services.scanner_service import scanner_service

router = APIRouter(prefix="/api/v1", tags=["scanner"])


class ScanResult(BaseModel):
    """Puzzle scan result."""

    grid: list[int] = Field(..., min_length=81, max_length=81, description="81-cell grid (0=empty)")
    confidence: list[float] = Field(..., min_length=81, max_length=81, description="Per-cell confidence")
    warnings: list[str] = Field(default_factory=list, description="Processing warnings")


@router.post("/scan", response_model=ScanResult)
async def scan_puzzle(image: UploadFile = File(...)) -> ScanResult:
    """
    Scan a physical Sudoku puzzle from an image.

    Pipeline: Image → OpenCV preprocessing → CNN digit recognition → grid.
    """
    image_bytes = await image.read()

    result = scanner_service.scan(image_bytes)

    return ScanResult(
        grid=result["grid"],
        confidence=result["confidence"],
        warnings=result["warnings"],
    )
