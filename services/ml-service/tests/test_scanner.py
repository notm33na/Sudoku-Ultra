"""
Tests for CV puzzle scanner — preprocessing, digit dataset, training, inference.
"""

import pytest
import numpy as np

try:
    import cv2
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False


# ─── Preprocessing Pipeline ──────────────────────────────────────────────────


@pytest.mark.unit
@pytest.mark.skipif(not HAS_CV2, reason="opencv not installed")
class TestPreprocessing:

    def _make_test_image(self) -> bytes:
        """Create a simple test image with a grid-like pattern."""
        img = np.ones((500, 500, 3), dtype=np.uint8) * 255
        # Draw a grid
        for i in range(10):
            pos = int(50 + i * 44)
            cv2.line(img, (50, pos), (446, pos), 0, 2)
            cv2.line(img, (pos, 50), (pos, 446), 0, 2)
        _, buf = cv2.imencode(".png", img)
        return buf.tobytes()

    def test_process_returns_81_cells(self):
        from app.ml.preprocessing import PuzzlePreprocessor
        pp = PuzzlePreprocessor()
        img_bytes = self._make_test_image()
        cells, warnings = pp.process(img_bytes)
        assert len(cells) == 81
        assert all(isinstance(c, np.ndarray) for c in cells)

    def test_cells_are_correct_shape(self):
        from app.ml.preprocessing import PuzzlePreprocessor, CELL_SIZE
        pp = PuzzlePreprocessor()
        img_bytes = self._make_test_image()
        cells, _ = pp.process(img_bytes)
        for cell in cells:
            assert cell.shape == (CELL_SIZE, CELL_SIZE)

    def test_invalid_image_raises(self):
        from app.ml.preprocessing import PuzzlePreprocessor
        pp = PuzzlePreprocessor()
        with pytest.raises(ValueError, match="Failed to decode"):
            pp.process(b"not an image")


# ─── Digit Dataset ────────────────────────────────────────────────────────────


@pytest.mark.unit
@pytest.mark.skipif(not HAS_CV2, reason="opencv not installed")
class TestDigitDataset:

    def test_generate_correct_count(self):
        from app.ml.digit_dataset import generate_digit_dataset
        imgs, lbls = generate_digit_dataset(samples_per_class=5, seed=1)
        assert len(imgs) == 50  # 10 classes × 5
        assert len(lbls) == 50

    def test_all_classes_present(self):
        from app.ml.digit_dataset import generate_digit_dataset
        _, lbls = generate_digit_dataset(samples_per_class=10, seed=2)
        assert set(lbls.tolist()) == set(range(10))

    def test_image_shape(self):
        from app.ml.digit_dataset import generate_digit_dataset, CELL_SIZE
        imgs, _ = generate_digit_dataset(samples_per_class=2, seed=3)
        assert imgs.shape[1:] == (CELL_SIZE, CELL_SIZE)

    def test_reproducible(self):
        from app.ml.digit_dataset import generate_digit_dataset
        i1, l1 = generate_digit_dataset(samples_per_class=5, seed=99)
        i2, l2 = generate_digit_dataset(samples_per_class=5, seed=99)
        np.testing.assert_array_equal(i1, i2)
        np.testing.assert_array_equal(l1, l2)


# ─── Digit Classifier Model ──────────────────────────────────────────────────


@pytest.mark.unit
class TestDigitClassifierModel:

    def test_model_forward_shape(self):
        import torch
        from app.ml.train_scanner import DigitClassifier
        model = DigitClassifier()
        x = torch.randn(4, 1, 64, 64)
        out = model(x)
        assert out.shape == (4, 10)

    def test_model_output_is_logits(self):
        import torch
        from app.ml.train_scanner import DigitClassifier
        model = DigitClassifier()
        x = torch.randn(1, 1, 64, 64)
        out = model(x)
        # Logits can be any real number
        assert not torch.isnan(out).any()


# ─── Scanner Service ─────────────────────────────────────────────────────────


@pytest.mark.unit
class TestScannerService:

    def test_fallback_when_not_loaded(self):
        from app.services.scanner_service import ScannerService
        svc = ScannerService()
        result = svc.scan(b"dummy")
        assert len(result["grid"]) == 81
        assert all(g == 0 for g in result["grid"])
        assert len(result["warnings"]) > 0

    def test_load_nonexistent(self):
        from pathlib import Path
        from app.services.scanner_service import ScannerService
        svc = ScannerService()
        assert not svc.load(Path("/nonexistent"))

    @pytest.mark.skipif(not HAS_CV2, reason="opencv not installed")
    def test_scan_with_trained_model(self, tmp_path):
        """Train a tiny model, save, load, and scan."""
        import torch
        from app.ml.train_scanner import DigitClassifier
        from app.services.scanner_service import ScannerService

        model = DigitClassifier()
        model_path = tmp_path / "scanner.pt"
        torch.save(model.state_dict(), model_path)

        svc = ScannerService()
        assert svc.load(tmp_path)

        # Create a simple test image
        img = np.ones((500, 500, 3), dtype=np.uint8) * 255
        _, buf = cv2.imencode(".png", img)

        result = svc.scan(buf.tobytes())
        assert len(result["grid"]) == 81
        assert len(result["confidence"]) == 81
        assert all(0.0 <= c <= 1.0 for c in result["confidence"])
