"""
GAN puzzle generation service.

Wraps the trained SudokuGenerator for inference.
Falls back to pure backtracking when model weights are unavailable.

Three generation modes
----------------------
solution     — return a complete valid 81-cell solution (no puzzle mask)
puzzle       — return solution + puzzle mask at requested difficulty
constrained  — same as puzzle but enforces 180° rotational symmetry
"""

from __future__ import annotations

import os
import random
from pathlib import Path
from typing import Any

import torch

from app.config import settings
from app.logging import setup_logging
from app.ml.gan import (
    DIFFICULTY_MAP,
    LATENT_DIM,
    NUM_DIFFICULTIES,
    SudokuGenerator,
    _generate_solution_bt,
    _is_valid,
    board_to_onehot,
    grid_from_logits,
    remove_cells,
)

logger = setup_logging()

MODEL_PATH = Path(settings.MODEL_DIR) / "sudoku_gan_generator.pt"

VALID_MODES = {"solution", "puzzle", "constrained"}
VALID_DIFFICULTIES = set(DIFFICULTY_MAP.keys())


class GANPuzzleService:
    def __init__(self) -> None:
        self._generator: SudokuGenerator | None = None
        self._device = torch.device("cpu")
        self._loaded = False

    # ── Lifecycle ──────────────────────────────────────────────────────────

    def load(self) -> bool:
        if not MODEL_PATH.exists():
            logger.warning(f"GAN weights not found at {MODEL_PATH} — using backtracking fallback")
            return False
        try:
            gen = SudokuGenerator(LATENT_DIM, NUM_DIFFICULTIES)
            state = torch.load(MODEL_PATH, map_location="cpu", weights_only=True)
            gen.load_state_dict(state)
            gen.eval()
            self._generator = gen
            self._loaded = True
            logger.info("GAN generator loaded successfully")
            return True
        except Exception as exc:
            logger.warning(f"Failed to load GAN generator: {exc}")
            return False

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    # ── Public API ─────────────────────────────────────────────────────────

    def generate(
        self,
        mode: str = "puzzle",
        difficulty: str = "medium",
        count: int = 1,
        symmetric: bool = False,
    ) -> list[dict[str, Any]]:
        """
        Generate `count` puzzles.

        Returns list of dicts:
            solution      list[int]   81 cells (digits 1-9)
            puzzle        list[int]   81 cells (0 = empty) — only for puzzle/constrained
            difficulty    str
            clue_count    int
            source        str         "gan" | "backtracking"
            valid         bool
        """
        if mode not in VALID_MODES:
            raise ValueError(f"mode must be one of {VALID_MODES}")
        if difficulty not in VALID_DIFFICULTIES:
            raise ValueError(f"difficulty must be one of {sorted(VALID_DIFFICULTIES)}")
        if not 1 <= count <= 10:
            raise ValueError("count must be between 1 and 10")

        results = []
        for _ in range(count):
            results.append(self._generate_one(mode, difficulty, symmetric))
        return results

    # ── Internal ───────────────────────────────────────────────────────────

    def _generate_one(
        self,
        mode: str,
        difficulty: str,
        symmetric: bool,
    ) -> dict[str, Any]:
        diff_idx = DIFFICULTY_MAP[difficulty]

        if self._loaded and self._generator is not None:
            solution = self._gan_solution(diff_idx)
            source = "gan"
        else:
            solution = _generate_solution_bt()
            source = "backtracking"

        valid = _is_valid(solution)
        if not valid:
            # Paranoia: repair
            solution = _generate_solution_bt()
            source = "backtracking"
            valid = True

        if mode == "solution":
            return {
                "solution": solution,
                "puzzle": None,
                "difficulty": difficulty,
                "clue_count": 81,
                "source": source,
                "valid": valid,
            }

        is_symmetric = symmetric or (mode == "constrained")
        puzzle = remove_cells(solution, difficulty=difficulty, symmetric=is_symmetric)
        clue_count = sum(1 for v in puzzle if v != 0)

        return {
            "solution": solution,
            "puzzle": puzzle,
            "difficulty": difficulty,
            "clue_count": clue_count,
            "source": source,
            "valid": valid,
        }

    def _gan_solution(self, diff_idx: int) -> list[int]:
        assert self._generator is not None
        with torch.no_grad():
            z = self._generator.sample_z(1, self._device)
            diff_t = torch.tensor([diff_idx], dtype=torch.long, device=self._device)
            logits = self._generator(z, diff_t)[0]   # (81, 9)
        return grid_from_logits(logits)

    # ── Status ─────────────────────────────────────────────────────────────

    def status(self) -> dict[str, Any]:
        return {
            "loaded": self._loaded,
            "model_path": str(MODEL_PATH),
            "fallback": "backtracking" if not self._loaded else None,
        }


# Singleton
gan_service = GANPuzzleService()
