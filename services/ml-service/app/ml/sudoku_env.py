"""
sudoku_env.py — Custom Gymnasium environment for Sudoku RL bot training.

Observation space: Box(0, 9, (810,), dtype=np.int32)
  obs[0:81]    – current board state (0=empty, 1–9=filled digit)
  obs[81:810]  – candidate mask; obs[81 + i*9 + (d-1)] = 1 if digit d is
                  a valid candidate for cell i on the current board

Action space: Discrete(729)
  action = cell_index * 9 + (digit - 1)   →   cell_index ∈ [0,80], digit ∈ [1,9]

Rewards:
  +1.0   correct digit placed
  +10.0  puzzle complete (bonus stacked on the +1.0)
  -0.5   incorrect digit, cell already filled, or given cell overwrite
  -0.1   per step (time penalty to encourage speed)

Episode ends when:
  - All non-given cells are filled correctly (terminated=True)
  - _max_steps reached (truncated=True)
"""

from __future__ import annotations

import random
from typing import Optional

import numpy as np
from gymnasium import Env, spaces


class SudokuEnv(Env):
    """Single-puzzle Sudoku environment that samples from a pool each reset."""

    metadata = {"render_modes": ["ansi"]}

    def __init__(
        self,
        puzzles: list[tuple[list[int], list[int]]],
        max_steps: int = 400,
        render_mode: Optional[str] = None,
    ) -> None:
        super().__init__()
        if not puzzles:
            raise ValueError("puzzles list must not be empty")
        self.puzzles = puzzles
        self._max_steps = max_steps
        self.render_mode = render_mode

        # obs: board(81) + candidate_mask(729)
        self.observation_space = spaces.Box(low=0, high=9, shape=(810,), dtype=np.int32)
        # action: cell_index * 9 + (digit - 1)
        self.action_space = spaces.Discrete(729)

        self._board: np.ndarray = np.zeros(81, dtype=np.int32)
        self._puzzle: np.ndarray = np.zeros(81, dtype=np.int32)
        self._solution: np.ndarray = np.zeros(81, dtype=np.int32)
        self._step_count: int = 0
        self._solution_cells: int = 0  # cells that need to be filled

    # ─── Gymnasium API ────────────────────────────────────────────────────────

    def reset(
        self,
        *,
        seed: Optional[int] = None,
        options: Optional[dict] = None,
    ) -> tuple[np.ndarray, dict]:
        super().reset(seed=seed)
        puzzle, solution = self.puzzles[self.np_random.integers(len(self.puzzles))]
        self._puzzle = np.array(puzzle, dtype=np.int32)
        self._solution = np.array(solution, dtype=np.int32)
        self._board = self._puzzle.copy()
        self._step_count = 0
        self._solution_cells = int(np.sum(self._solution != 0))
        return self._get_obs(), {}

    def step(self, action: int) -> tuple[np.ndarray, float, bool, bool, dict]:
        cell_index = int(action) // 9
        digit = int(action) % 9 + 1
        self._step_count += 1

        reward = -0.1  # time penalty every step
        terminated = False
        truncated = self._step_count >= self._max_steps

        # Overwriting a given cell is invalid.
        if self._puzzle[cell_index] != 0:
            reward -= 0.5
        elif self._board[cell_index] != 0:
            # Cell already filled — penalise revisiting.
            reward -= 0.5
        elif self._solution[cell_index] == digit:
            # Correct placement.
            self._board[cell_index] = digit
            filled = int(np.count_nonzero(self._board))
            reward += 1.0
            if filled == self._solution_cells:
                reward += 10.0
                terminated = True
        else:
            # Wrong digit.
            reward -= 0.5

        return self._get_obs(), reward, terminated, truncated, {}

    def render(self) -> Optional[str]:
        if self.render_mode != "ansi":
            return None
        rows = []
        for r in range(9):
            row = self._board[r * 9 : r * 9 + 9]
            rows.append(" ".join(str(v) if v else "." for v in row))
        return "\n".join(rows)

    # ─── Observation Builder ──────────────────────────────────────────────────

    def _get_obs(self) -> np.ndarray:
        obs = np.zeros(810, dtype=np.int32)
        obs[:81] = self._board
        for i in range(81):
            if self._board[i] == 0:
                for d in range(1, 10):
                    if self._is_candidate(i, d):
                        obs[81 + i * 9 + (d - 1)] = 1
        return obs

    def get_action_mask(self) -> np.ndarray:
        """Return bool mask of valid actions for MaskablePPO / action-masked sampling."""
        mask = np.zeros(729, dtype=bool)
        for i in range(81):
            if self._puzzle[i] != 0 or self._board[i] != 0:
                continue  # given or already filled
            for d in range(1, 10):
                if self._is_candidate(i, d):
                    mask[i * 9 + (d - 1)] = True
        return mask

    # ─── Constraint Check ─────────────────────────────────────────────────────

    def _is_candidate(self, cell: int, digit: int) -> bool:
        row, col = cell // 9, cell % 9
        br, bc = (row // 3) * 3, (col // 3) * 3
        # Row
        if digit in self._board[row * 9 : row * 9 + 9]:
            return False
        # Column
        if digit in self._board[col::9]:
            return False
        # Box
        for r in range(br, br + 3):
            for c in range(bc, bc + 3):
                if self._board[r * 9 + c] == digit:
                    return False
        return True


# ─── Puzzle Generator ─────────────────────────────────────────────────────────

def _is_valid(board: list[int], pos: int, num: int) -> bool:
    """Check if placing num at pos is valid on the full board."""
    row, col = pos // 9, pos % 9
    if num in board[row * 9 : row * 9 + 9]:
        return False
    if num in board[col::9]:
        return False
    br, bc = (row // 3) * 3, (col // 3) * 3
    for r in range(br, br + 3):
        for c in range(bc, bc + 3):
            if board[r * 9 + c] == num:
                return False
    return True


def _solve(board: list[int]) -> bool:
    """Backtracking solver — fills board in-place; returns True if solved."""
    try:
        pos = board.index(0)
    except ValueError:
        return True  # no empty cell

    digits = list(range(1, 10))
    random.shuffle(digits)
    for d in digits:
        if _is_valid(board, pos, d):
            board[pos] = d
            if _solve(board):
                return True
            board[pos] = 0
    return False


def generate_puzzle(clues: int = 32) -> tuple[list[int], list[int]]:
    """
    Generate a random Sudoku puzzle with `clues` given cells.
    Returns (puzzle, solution) as flat 81-element lists.
    `clues` in range [25, 50] gives solvable puzzles with varying difficulty.
    """
    clues = max(17, min(clues, 80))
    board = [0] * 81
    _solve(board)
    solution = board[:]

    # Remove cells randomly to reach the target clue count.
    positions = list(range(81))
    random.shuffle(positions)
    for pos in positions[clues:]:
        board[pos] = 0

    return board, solution


def generate_puzzle_pool(n: int = 500, clues: int = 32) -> list[tuple[list[int], list[int]]]:
    """Generate a pool of n puzzles for environment training."""
    return [generate_puzzle(clues) for _ in range(n)]
