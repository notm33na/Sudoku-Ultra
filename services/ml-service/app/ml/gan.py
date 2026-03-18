"""
Sudoku GAN — conditional generator and discriminator.

Architecture
------------
Generator
  Input : latent vector z (LATENT_DIM) ⊕ difficulty one-hot (NUM_DIFFICULTIES)
  Layers: FC → BN → ReLU (×3) → FC → reshape (81, 9)
  Output: 81-cell logits over digits 1-9
  Training uses Gumbel-softmax for differentiable discrete sampling.
  Inference uses argmax + backtracking repair.

Discriminator (WGAN-GP, no sigmoid)
  Input : 81-cell one-hot grid (729 floats)
  Layers: FC → LeakyReLU (×3) → FC → scalar
  Output: Wasserstein critic score

Post-processing
---------------
  grid_from_logits()    — argmax + backtracking repair → valid 81-int list
  remove_cells()        — deterministic difficulty-based cell removal
  add_symmetry()        — optional 180° rotational symmetry mask
"""

from __future__ import annotations

import random
from typing import Optional

import torch
import torch.nn as nn
import torch.nn.functional as F

# ── Constants ──────────────────────────────────────────────────────────────────

LATENT_DIM = 64
NUM_DIFFICULTIES = 5          # easy, medium, hard, super_hard, extreme
BOARD_CELLS = 81
NUM_DIGITS = 9                # digits 1-9

# Clue-count ranges per difficulty (index = difficulty 0-4)
CLUE_RANGES = [
    (36, 45),   # easy
    (30, 35),   # medium
    (24, 29),   # hard
    (18, 23),   # super_hard
    (13, 17),   # extreme
]

DIFFICULTY_MAP = {
    'easy': 0, 'medium': 1, 'hard': 2, 'super_hard': 3, 'extreme': 4,
}

# ── Generator ─────────────────────────────────────────────────────────────────

class SudokuGenerator(nn.Module):
    def __init__(
        self,
        latent_dim: int = LATENT_DIM,
        num_difficulties: int = NUM_DIFFICULTIES,
    ):
        super().__init__()
        in_dim = latent_dim + num_difficulties
        self.net = nn.Sequential(
            nn.Linear(in_dim, 512),
            nn.BatchNorm1d(512),
            nn.ReLU(inplace=True),
            nn.Linear(512, 1024),
            nn.BatchNorm1d(1024),
            nn.ReLU(inplace=True),
            nn.Linear(1024, 2048),
            nn.BatchNorm1d(2048),
            nn.ReLU(inplace=True),
            nn.Linear(2048, BOARD_CELLS * NUM_DIGITS),
        )
        self.latent_dim = latent_dim
        self.num_difficulties = num_difficulties

    def forward(
        self,
        z: torch.Tensor,
        difficulty_idx: torch.Tensor,
    ) -> torch.Tensor:
        """
        Args:
            z: (batch, LATENT_DIM)
            difficulty_idx: (batch,) long tensor with difficulty indices 0-4

        Returns:
            logits: (batch, 81, 9)
        """
        diff_oh = F.one_hot(difficulty_idx, self.num_difficulties).float()
        x = torch.cat([z, diff_oh], dim=1)
        out = self.net(x)
        return out.view(-1, BOARD_CELLS, NUM_DIGITS)

    def sample_z(self, batch: int, device: torch.device = torch.device('cpu')) -> torch.Tensor:
        return torch.randn(batch, self.latent_dim, device=device)


# ── Discriminator ─────────────────────────────────────────────────────────────

class SudokuDiscriminator(nn.Module):
    """WGAN-GP critic — no sigmoid, output is raw score."""

    def __init__(self):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(BOARD_CELLS * NUM_DIGITS, 1024),
            nn.LeakyReLU(0.2, inplace=True),
            nn.Linear(1024, 512),
            nn.LeakyReLU(0.2, inplace=True),
            nn.Linear(512, 256),
            nn.LeakyReLU(0.2, inplace=True),
            nn.Linear(256, 1),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        Args:
            x: (batch, 81, 9) one-hot or soft assignment
        Returns:
            score: (batch, 1)
        """
        return self.net(x.view(x.size(0), -1))


# ── Gradient penalty (WGAN-GP) ────────────────────────────────────────────────

def gradient_penalty(
    discriminator: SudokuDiscriminator,
    real: torch.Tensor,
    fake: torch.Tensor,
    device: torch.device,
) -> torch.Tensor:
    eps = torch.rand(real.size(0), 1, 1, device=device)
    interp = (eps * real + (1 - eps) * fake).requires_grad_(True)
    d_interp = discriminator(interp)
    grads = torch.autograd.grad(
        outputs=d_interp,
        inputs=interp,
        grad_outputs=torch.ones_like(d_interp),
        create_graph=True,
        retain_graph=True,
    )[0]
    grads = grads.view(grads.size(0), -1)
    return ((grads.norm(2, dim=1) - 1) ** 2).mean()


# ── Backtracking Sudoku solver (inline) ───────────────────────────────────────

def _candidates(board: list[int], idx: int) -> set[int]:
    r, c = divmod(idx, 9)
    br, bc = (r // 3) * 3, (c // 3) * 3
    used: set[int] = set()
    for j in range(9):
        used.add(board[r * 9 + j])
        used.add(board[j * 9 + c])
    for dr in range(3):
        for dc in range(3):
            used.add(board[(br + dr) * 9 + (bc + dc)])
    return set(range(1, 10)) - used


def _solve_board(board: list[int]) -> bool:
    """In-place backtracking solver. Returns True if solved."""
    try:
        idx = board.index(0)
    except ValueError:
        return True  # no empty cells
    for val in _candidates(board, idx):
        board[idx] = val
        if _solve_board(board):
            return True
        board[idx] = 0
    return False


def _generate_solution_bt() -> list[int]:
    """Generate a random valid complete Sudoku solution via backtracking."""
    board = [0] * 81

    def fill(pos: int) -> bool:
        if pos == 81:
            return True
        cands = list(_candidates(board, pos))
        random.shuffle(cands)
        for val in cands:
            board[pos] = val
            if fill(pos + 1):
                return True
            board[pos] = 0
        return False

    fill(0)
    return board


# ── Board repair: logits → valid grid ────────────────────────────────────────

def grid_from_logits(logits: torch.Tensor) -> list[int]:
    """
    Convert a (81, 9) logits tensor to a valid 81-int Sudoku solution.

    Strategy:
      1. Argmax to get initial assignment (digits 1-9).
      2. Check validity; if invalid, repair with backtracking from scratch
         seeded with the GAN's suggestions as the traversal order.
    """
    # argmax assignment
    digits = logits.argmax(dim=-1).tolist()          # list of 0-8 (digit-1)
    board = [d + 1 for d in digits]                   # 1-indexed

    if _is_valid(board):
        return board

    # Repair: use GAN digit probabilities to order candidates
    probs = torch.softmax(logits, dim=-1).tolist()    # (81, 9) float

    board = [0] * 81

    def fill_guided(pos: int) -> bool:
        if pos == 81:
            return True
        # Order candidates by GAN probability descending
        cands = sorted(
            _candidates(board, pos),
            key=lambda d: probs[pos][d - 1],
            reverse=True,
        )
        for val in cands:
            board[pos] = val
            if fill_guided(pos + 1):
                return True
            board[pos] = 0
        return False

    if fill_guided(0):
        return board

    # Last resort: pure random backtracking
    return _generate_solution_bt()


def _is_valid(board: list[int]) -> bool:
    """Check if a complete 81-cell board satisfies all Sudoku constraints."""
    if len(board) != 81 or any(v == 0 for v in board):
        return False
    for i in range(9):
        row = [board[i * 9 + c] for c in range(9)]
        col = [board[r * 9 + i] for r in range(9)]
        br, bc = (i // 3) * 3, (i % 3) * 3
        box = [board[(br + dr) * 9 + (bc + dc)] for dr in range(3) for dc in range(3)]
        if set(row) != set(range(1, 10)):
            return False
        if set(col) != set(range(1, 10)):
            return False
        if set(box) != set(range(1, 10)):
            return False
    return True


# ── Cell removal ──────────────────────────────────────────────────────────────

def remove_cells(
    solution: list[int],
    difficulty: str = 'medium',
    symmetric: bool = False,
) -> list[int]:
    """
    Remove cells from a complete solution to create a puzzle.

    Returns 81-cell list where 0 = empty (clue removed).
    Guarantees the resulting puzzle has a unique solution (basic check).
    """
    lo, hi = CLUE_RANGES[DIFFICULTY_MAP.get(difficulty, 1)]
    target_clues = random.randint(lo, hi)
    target_removes = 81 - target_clues

    puzzle = solution[:]
    indices = list(range(81))
    random.shuffle(indices)

    removed = 0
    for idx in indices:
        if removed >= target_removes:
            break
        if puzzle[idx] == 0:
            continue
        backup = puzzle[idx]
        puzzle[idx] = 0

        if symmetric:
            mirror = 80 - idx
            mirror_backup = puzzle[mirror]
            puzzle[mirror] = 0

        # Verify still uniquely solvable (quick check via solve count limit)
        if _count_solutions(puzzle[:], limit=2) == 1:
            removed += 1 if not symmetric else 2
        else:
            puzzle[idx] = backup
            if symmetric:
                puzzle[80 - idx] = mirror_backup

    return puzzle


def _count_solutions(board: list[int], limit: int = 2) -> int:
    """Count solutions up to `limit` using backtracking."""
    try:
        idx = board.index(0)
    except ValueError:
        return 1

    count = 0
    for val in _candidates(board, idx):
        board[idx] = val
        count += _count_solutions(board, limit)
        board[idx] = 0
        if count >= limit:
            break
    return count


# ── Encoding helpers for training ────────────────────────────────────────────

def board_to_onehot(board: list[int]) -> torch.Tensor:
    """Convert 81-int board to (81, 9) one-hot float tensor. 0-cells → zero vector."""
    t = torch.zeros(81, 9)
    for i, v in enumerate(board):
        if 1 <= v <= 9:
            t[i, v - 1] = 1.0
    return t


def generate_training_batch(
    batch_size: int,
    device: torch.device = torch.device('cpu'),
) -> tuple[torch.Tensor, torch.Tensor]:
    """
    Generate a batch of real Sudoku solutions as training data.

    Returns:
        real_grids:   (batch, 81, 9) one-hot
        difficulties: (batch,) long — random difficulty indices
    """
    solutions = [_generate_solution_bt() for _ in range(batch_size)]
    real_grids = torch.stack([board_to_onehot(s) for s in solutions]).to(device)
    difficulties = torch.randint(0, NUM_DIFFICULTIES, (batch_size,), device=device)
    return real_grids, difficulties
