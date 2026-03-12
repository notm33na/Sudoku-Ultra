"""
OpenCV preprocessing pipeline for Sudoku puzzle scanning.

Pipeline stages:
  1. Grayscale conversion
  2. Gaussian denoising
  3. Adaptive thresholding
  4. Contour detection → find largest quadrilateral
  5. Perspective transform → square grid
  6. Grid extraction → 81 individual cells
"""

import numpy as np

try:
    import cv2
except ImportError:
    cv2 = None  # Graceful degradation — tests can mock

from app.logging import setup_logging

logger = setup_logging()

GRID_SIZE = 9
CELL_SIZE = 64  # Standardized cell size in pixels


class PuzzlePreprocessor:
    """OpenCV pipeline to extract 81 cells from a Sudoku puzzle image."""

    def __init__(self, cell_size: int = CELL_SIZE) -> None:
        self.cell_size = cell_size
        self.grid_size_px = cell_size * GRID_SIZE

    def process(self, image_bytes: bytes) -> tuple[list[np.ndarray], list[str]]:
        """
        Full pipeline: image bytes → 81 cell images.

        Args:
            image_bytes: Raw image bytes (PNG/JPG).

        Returns:
            (cells, warnings) where cells is a list of 81 grayscale cell images
            and warnings is a list of processing warnings.
        """
        if cv2 is None:
            raise ImportError("opencv-python-headless is required for puzzle scanning")

        warnings: list[str] = []

        # 1. Decode image
        img_array = np.frombuffer(image_bytes, dtype=np.uint8)
        img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
        if img is None:
            raise ValueError("Failed to decode image")

        # 2. Grayscale
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        # 3. Denoise
        denoised = cv2.GaussianBlur(gray, (5, 5), 0)

        # 4. Adaptive threshold
        thresh = cv2.adaptiveThreshold(
            denoised, 255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY_INV,
            blockSize=11,
            C=2,
        )

        # 5. Find grid contour
        grid_contour = self._find_grid_contour(thresh)
        if grid_contour is not None:
            # 6. Perspective transform
            warped = self._perspective_transform(gray, grid_contour)
        else:
            warnings.append("Could not detect grid boundary — using center crop")
            warped = self._center_crop(gray)

        # 7. Extract 81 cells
        cells = self._extract_cells(warped)

        return cells, warnings

    def _find_grid_contour(self, thresh: np.ndarray) -> np.ndarray | None:
        """Find the largest quadrilateral contour (the Sudoku grid)."""
        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        if not contours:
            return None

        # Sort by area, largest first
        contours = sorted(contours, key=cv2.contourArea, reverse=True)

        for contour in contours[:5]:
            peri = cv2.arcLength(contour, True)
            approx = cv2.approxPolyDP(contour, 0.02 * peri, True)

            if len(approx) == 4:
                # Verify minimum area (at least 10% of image)
                area = cv2.contourArea(approx)
                img_area = thresh.shape[0] * thresh.shape[1]
                if area > img_area * 0.1:
                    return approx.reshape(4, 2).astype(np.float32)

        return None

    def _perspective_transform(
        self, gray: np.ndarray, corners: np.ndarray
    ) -> np.ndarray:
        """Warp the grid to a square using perspective transform."""
        # Order corners: top-left, top-right, bottom-right, bottom-left
        ordered = self._order_corners(corners)

        dst = np.array([
            [0, 0],
            [self.grid_size_px - 1, 0],
            [self.grid_size_px - 1, self.grid_size_px - 1],
            [0, self.grid_size_px - 1],
        ], dtype=np.float32)

        matrix = cv2.getPerspectiveTransform(ordered, dst)
        warped = cv2.warpPerspective(gray, matrix, (self.grid_size_px, self.grid_size_px))

        return warped

    def _order_corners(self, pts: np.ndarray) -> np.ndarray:
        """Order 4 corners as: TL, TR, BR, BL."""
        rect = np.zeros((4, 2), dtype=np.float32)
        s = pts.sum(axis=1)
        d = np.diff(pts, axis=1).flatten()

        rect[0] = pts[np.argmin(s)]   # top-left: smallest sum
        rect[2] = pts[np.argmax(s)]   # bottom-right: largest sum
        rect[1] = pts[np.argmin(d)]   # top-right: smallest diff
        rect[3] = pts[np.argmax(d)]   # bottom-left: largest diff

        return rect

    def _center_crop(self, gray: np.ndarray) -> np.ndarray:
        """Fallback: center crop and resize to grid size."""
        h, w = gray.shape[:2]
        size = min(h, w)
        y_start = (h - size) // 2
        x_start = (w - size) // 2
        cropped = gray[y_start:y_start + size, x_start:x_start + size]
        return cv2.resize(cropped, (self.grid_size_px, self.grid_size_px))

    def _extract_cells(self, grid: np.ndarray) -> list[np.ndarray]:
        """Split grid image into 81 individual cell images."""
        cells = []
        for row in range(GRID_SIZE):
            for col in range(GRID_SIZE):
                y1 = row * self.cell_size
                y2 = (row + 1) * self.cell_size
                x1 = col * self.cell_size
                x2 = (col + 1) * self.cell_size

                cell = grid[y1:y2, x1:x2]

                # Clean cell: remove border artifacts (inner 70%)
                margin = int(self.cell_size * 0.15)
                cleaned = cell[margin:-margin, margin:-margin]
                cleaned = cv2.resize(cleaned, (self.cell_size, self.cell_size))

                cells.append(cleaned)

        return cells
