"""
bot_service.py — Inference service for the RL Sudoku bot.

get_move(board, solution, tier) → { cell_index, digit, confidence, source }

Tier resolution:
  1. Try to load MaskablePPO model for the requested tier from ml/models/rl_bot_{tier}.zip
  2. If unavailable (model file missing or SB3 not installed), fall back to
     constraint-propagation rule-based solver (always produces a correct move).

Rule-based strategy (tiered):
  easy   → random valid cell from least-constrained set
  medium → MRV (minimum remaining values — most constrained empty cell)
  hard   → MRV with deterministic tie-breaking by cell index
"""

from __future__ import annotations

import logging
import pathlib
import random
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

MODELS_DIR = pathlib.Path("ml/models")

try:
    from sb3_contrib import MaskablePPO
    _SB3_AVAILABLE = True
except ImportError:
    _SB3_AVAILABLE = False
    logger.info("sb3-contrib not installed — bot will use rule-based fallback only")


class BotService:
    """
    Singleton-style service that caches loaded PPO models in memory.
    Thread-safe: models are read-only after loading; no shared mutable state.
    """

    def __init__(self) -> None:
        self._models: dict[str, Any] = {}  # tier → MaskablePPO | None

    # ─── Public API ───────────────────────────────────────────────────────────

    def get_move(
        self,
        board: list[int],
        solution: list[int],
        tier: str = "medium",
    ) -> dict:
        """
        Given the bot's current board and the authoritative solution, return the
        next move as {cell_index, digit, confidence, source}.

        board    – 81-element list; 0=empty, 1–9=filled digit (bot's own board)
        solution – 81-element list; the complete, correct solution
        tier     – "easy" | "medium" | "hard"
        """
        if len(board) != 81 or len(solution) != 81:
            raise ValueError("board and solution must be 81-element lists")

        model = self._get_model(tier)
        if model is not None:
            move = self._rl_move(model, board, solution, tier)
            if move is not None:
                return move
            # RL produced an invalid/stuck action — fall through to rule-based.

        return self._rule_based_move(board, solution, tier)

    # ─── Model Loading ────────────────────────────────────────────────────────

    def _get_model(self, tier: str):
        if not _SB3_AVAILABLE:
            return None
        if tier not in self._models:
            self._models[tier] = self._load_model(tier)
        return self._models[tier]

    def _load_model(self, tier: str):
        path = MODELS_DIR / f"rl_bot_{tier}.zip"
        if not path.exists():
            logger.debug(f"RL model not found at {path}; using rule-based fallback")
            return None
        try:
            model = MaskablePPO.load(str(path))
            logger.info(f"Loaded RL bot model: tier={tier!r}")
            return model
        except Exception as exc:
            logger.warning(f"Failed to load RL model for tier={tier!r}: {exc}")
            return None

    # ─── RL Inference ─────────────────────────────────────────────────────────

    def _rl_move(self, model, board: list[int], solution: list[int], tier: str) -> Optional[dict]:
        from app.ml.sudoku_env import SudokuEnv

        # Build a throwaway env to compute observation and action mask.
        # The puzzle is inferred: cells where board[i] != 0 are "given".
        # We use a single-element pool; reset() will load it.
        puzzle = board[:]  # treat current board as the puzzle
        env = SudokuEnv([(puzzle, solution)], max_steps=1)
        obs, _ = env.reset()
        # Manually set board to the actual bot board state (env.reset copies puzzle).
        env._board = np.array(board, dtype=np.int32)
        env._puzzle = np.array(puzzle, dtype=np.int32)
        env._solution = np.array(solution, dtype=np.int32)
        obs = env._get_obs()

        action_mask = env.get_action_mask()
        if not action_mask.any():
            return None  # no valid moves

        action, _ = model.predict(obs, action_masks=action_mask, deterministic=True)
        action = int(action)

        if not action_mask[action]:
            # Model chose an invalid action despite masking — shouldn't happen
            # with MaskablePPO but guard it anyway.
            return None

        cell_index = action // 9
        digit = action % 9 + 1
        confidence = float(np.max(model.policy.get_distribution(
            model.policy.obs_to_tensor(obs[None])[0]
        ).distribution.probs.detach().cpu().numpy()))

        return {
            "cell_index": cell_index,
            "digit": digit,
            "confidence": round(confidence, 4),
            "source": "rl",
        }

    # ─── Rule-Based Fallback ──────────────────────────────────────────────────

    def _rule_based_move(self, board: list[int], solution: list[int], tier: str) -> dict:
        """
        MRV (minimum remaining values) cell selection.
        - hard/medium: pick the most constrained empty cell (fewest valid digits)
        - easy: pick a random empty cell
        Always fills with the solution value (bot knows the answer).
        """
        empty_cells = [i for i in range(81) if board[i] == 0 and solution[i] != 0]
        if not empty_cells:
            # Shouldn't happen — caller should stop when puzzle complete.
            raise RuntimeError("No empty cells remaining")

        if tier == "easy":
            cell_index = random.choice(empty_cells)
        else:
            # MRV: prefer the cell with the fewest valid candidates.
            board_arr = np.array(board, dtype=np.int32)

            def candidate_count(i: int) -> int:
                return sum(
                    1 for d in range(1, 10)
                    if _is_candidate(board_arr, i, d)
                )

            scored = sorted(empty_cells, key=lambda i: (candidate_count(i), i))
            cell_index = scored[0]

        digit = solution[cell_index]
        return {
            "cell_index": cell_index,
            "digit": digit,
            "confidence": 1.0,
            "source": "fallback",
        }


# ─── Constraint Helper ────────────────────────────────────────────────────────

def _is_candidate(board: np.ndarray, cell: int, digit: int) -> bool:
    row, col = cell // 9, cell % 9
    br, bc = (row // 3) * 3, (col // 3) * 3
    if digit in board[row * 9 : row * 9 + 9]:
        return False
    if digit in board[col::9]:
        return False
    for r in range(br, br + 3):
        for c in range(bc, bc + 3):
            if board[r * 9 + c] == digit:
                return False
    return True


# ─── Module-Level Singleton ───────────────────────────────────────────────────

bot_service = BotService()
