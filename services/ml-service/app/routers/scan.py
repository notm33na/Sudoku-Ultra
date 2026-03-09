"""
Puzzle scanning router.

Receives an image and returns extracted 9x9 grid using
OpenCV preprocessing + CNN digit recognition.

Fully implemented in Deliverable 4.
"""

from fastapi import APIRouter, UploadFile, File
from pydantic import BaseModel, Field

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

    Fully implemented in Deliverable 4 — currently returns placeholder.
    """
    # D4: OpenCV preprocessing → CNN digit recognition → grid
    return ScanResult(
        grid=[0] * 81,
        confidence=[0.0] * 81,
        warnings=["Scanner not yet implemented — see Deliverable 4"],
    )
