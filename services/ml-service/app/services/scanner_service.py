"""
Puzzle scanner inference service.

Combines the OpenCV preprocessing pipeline with the digit classifier
to extract a 9x9 grid from an image.
"""

from pathlib import Path
from typing import Any

import numpy as np

try:
    import cv2
except ImportError:
    cv2 = None

import torch

from app.ml.preprocessing import PuzzlePreprocessor
from app.ml.train_scanner import DigitClassifier, NUM_CLASSES
from app.logging import setup_logging

logger = setup_logging()

MODEL_DIR = Path("ml/models")


class ScannerService:
    """
    Full puzzle scanning pipeline:
    Image → OpenCV preprocessing → CNN digit recognition → 9x9 grid.
    """

    def __init__(self) -> None:
        self.preprocessor = PuzzlePreprocessor()
        self.model: DigitClassifier | None = None
        self._loaded = False

    def load(self, model_dir: Path | None = None) -> bool:
        """Load the digit classifier model."""
        model_dir = model_dir or MODEL_DIR
        model_path = model_dir / "scanner.pt"

        if not model_path.exists():
            logger.warning(f"Scanner model not found at {model_dir} — using fallback")
            return False

        try:
            self.model = DigitClassifier(num_classes=NUM_CLASSES)
            state_dict = torch.load(model_path, map_location="cpu", weights_only=True)
            self.model.load_state_dict(state_dict)
            self.model.eval()
            self._loaded = True
            logger.info("Scanner model loaded successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to load scanner model: {e}")
            return False

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    def scan(self, image_bytes: bytes) -> dict[str, Any]:
        """
        Scan an image and extract the Sudoku grid.

        Returns:
            {grid: int[81], confidence: float[81], warnings: str[]}
        """
        warnings: list[str] = []

        if cv2 is None:
            return self._unavailable_fallback("OpenCV not installed")

        # 1. Preprocess
        try:
            cells, preprocess_warnings = self.preprocessor.process(image_bytes)
            warnings.extend(preprocess_warnings)
        except Exception as e:
            return self._unavailable_fallback(f"Preprocessing failed: {e}")

        if len(cells) != 81:
            return self._unavailable_fallback(f"Expected 81 cells, got {len(cells)}")

        # 2. Classify each cell
        if not self._loaded or self.model is None:
            warnings.append("Digit classifier not loaded — all cells returned as empty")
            return {
                "grid": [0] * 81,
                "confidence": [0.0] * 81,
                "warnings": warnings,
            }

        grid = []
        confidences = []

        with torch.no_grad():
            for cell_img in cells:
                digit, conf = self._classify_cell(cell_img)
                grid.append(digit)
                confidences.append(conf)

        # Flag low-confidence cells
        low_conf_count = sum(1 for c in confidences if c < 0.7)
        if low_conf_count > 0:
            warnings.append(
                f"{low_conf_count} cell(s) with confidence < 70% — review recommended"
            )

        return {
            "grid": grid,
            "confidence": confidences,
            "warnings": warnings,
        }

    def _classify_cell(self, cell_img: np.ndarray) -> tuple[int, float]:
        """Classify a single cell image."""
        # Normalize
        img = cell_img.astype(np.float32) / 255.0
        tensor = torch.from_numpy(img).unsqueeze(0).unsqueeze(0)  # (1, 1, 64, 64)

        logits = self.model(tensor)
        probs = torch.softmax(logits, dim=1)[0]
        digit = int(probs.argmax())
        confidence = float(probs[digit])

        return digit, round(confidence, 4)

    def _unavailable_fallback(self, reason: str) -> dict[str, Any]:
        """Return empty grid when scanning is unavailable."""
        return {
            "grid": [0] * 81,
            "confidence": [0.0] * 81,
            "warnings": [f"Scanner unavailable: {reason}"],
        }


# Singleton
scanner_service = ScannerService()
