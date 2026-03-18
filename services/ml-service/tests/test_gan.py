"""
Tests for D5 — GAN Puzzle Generation.

Coverage:
- GAN architecture forward pass shapes
- grid_from_logits produces valid board
- _is_valid recognises valid and invalid boards
- remove_cells clue-count range per difficulty
- remove_cells unique solution guarantee
- board_to_onehot encoding
- GANService.generate all three modes (backtracking fallback)
- GANService.generate validation errors
- FastAPI endpoints: /generate, /batch, /status
"""

from __future__ import annotations

import pytest
import torch
from fastapi.testclient import TestClient


# ── Fixtures ──────────────────────────────────────────────────────────────────

SOLVED_BOARD = [
    1, 2, 3, 4, 5, 6, 7, 8, 9,
    4, 5, 6, 7, 8, 9, 1, 2, 3,
    7, 8, 9, 1, 2, 3, 4, 5, 6,
    2, 1, 4, 3, 6, 5, 8, 9, 7,
    3, 6, 5, 8, 9, 7, 2, 1, 4,
    8, 9, 7, 2, 1, 4, 3, 6, 5,
    5, 3, 1, 6, 4, 2, 9, 7, 8,
    6, 4, 2, 9, 7, 8, 5, 3, 1,
    9, 7, 8, 5, 3, 1, 6, 4, 2,
]

INVALID_BOARD = [1] * 81  # all 1s — clearly invalid


# ── GAN architecture tests ────────────────────────────────────────────────────

def test_generator_output_shape():
    from app.ml.gan import SudokuGenerator, LATENT_DIM, NUM_DIFFICULTIES
    gen = SudokuGenerator(LATENT_DIM, NUM_DIFFICULTIES)
    z = gen.sample_z(4)
    diff = torch.zeros(4, dtype=torch.long)
    logits = gen(z, diff)
    assert logits.shape == (4, 81, 9)


def test_discriminator_output_shape():
    from app.ml.gan import SudokuDiscriminator
    disc = SudokuDiscriminator()
    x = torch.randn(4, 81, 9)
    out = disc(x)
    assert out.shape == (4, 1)


def test_generator_different_difficulties():
    from app.ml.gan import SudokuGenerator, LATENT_DIM, NUM_DIFFICULTIES
    gen = SudokuGenerator(LATENT_DIM, NUM_DIFFICULTIES)
    batch = 5
    z = gen.sample_z(batch)
    diff = torch.arange(batch, dtype=torch.long) % NUM_DIFFICULTIES
    logits = gen(z, diff)
    assert logits.shape == (batch, 81, 9)


def test_gradient_penalty_shape():
    from app.ml.gan import SudokuDiscriminator, gradient_penalty
    disc = SudokuDiscriminator()
    real = torch.randn(4, 81, 9)
    fake = torch.randn(4, 81, 9)
    gp = gradient_penalty(disc, real, fake, torch.device("cpu"))
    assert gp.shape == ()  # scalar tensor


# ── Validity checker tests ────────────────────────────────────────────────────

def test_is_valid_correct_board():
    from app.ml.gan import _is_valid
    assert _is_valid(SOLVED_BOARD) is True


def test_is_valid_invalid_board():
    from app.ml.gan import _is_valid
    assert _is_valid(INVALID_BOARD) is False


def test_is_valid_incomplete_board():
    from app.ml.gan import _is_valid
    board = SOLVED_BOARD[:]
    board[0] = 0
    assert _is_valid(board) is False


# ── Grid-from-logits tests ────────────────────────────────────────────────────

def test_grid_from_logits_length():
    from app.ml.gan import grid_from_logits
    logits = torch.randn(81, 9)
    board = grid_from_logits(logits)
    assert len(board) == 81


def test_grid_from_logits_digit_range():
    from app.ml.gan import grid_from_logits
    logits = torch.randn(81, 9)
    board = grid_from_logits(logits)
    assert all(1 <= v <= 9 for v in board)


def test_grid_from_logits_valid_when_high_confidence():
    """With very high-confidence logits matching a known solution, output should be valid."""
    from app.ml.gan import grid_from_logits, board_to_onehot, _is_valid
    # Use solved board's one-hot as logits (effectively forces argmax = solution)
    one_hot = board_to_onehot(SOLVED_BOARD) * 100.0  # scale up for high confidence
    board = grid_from_logits(one_hot)
    assert _is_valid(board)


# ── Backtracking solver test ──────────────────────────────────────────────────

def test_generate_solution_bt_valid():
    from app.ml.gan import _generate_solution_bt, _is_valid
    board = _generate_solution_bt()
    assert len(board) == 81
    assert _is_valid(board)


def test_generate_solution_bt_randomness():
    """Two successive calls should produce different solutions."""
    from app.ml.gan import _generate_solution_bt
    b1 = _generate_solution_bt()
    b2 = _generate_solution_bt()
    assert b1 != b2


# ── Cell removal tests ────────────────────────────────────────────────────────

@pytest.mark.parametrize("difficulty,expected_lo,expected_hi", [
    ("easy",       36, 45),
    ("medium",     30, 35),
    ("hard",       24, 29),
    ("super_hard", 18, 23),
    ("extreme",    13, 17),
])
def test_remove_cells_clue_range(difficulty, expected_lo, expected_hi):
    from app.ml.gan import remove_cells
    puzzle = remove_cells(SOLVED_BOARD[:], difficulty=difficulty)
    clues = sum(1 for v in puzzle if v != 0)
    assert expected_lo <= clues <= expected_hi, (
        f"Difficulty {difficulty}: expected [{expected_lo},{expected_hi}], got {clues}"
    )


def test_remove_cells_length():
    from app.ml.gan import remove_cells
    puzzle = remove_cells(SOLVED_BOARD[:])
    assert len(puzzle) == 81


def test_remove_cells_unique_solution():
    """Removing cells should preserve unique solvability."""
    from app.ml.gan import remove_cells, _count_solutions
    puzzle = remove_cells(SOLVED_BOARD[:], difficulty="easy")
    assert _count_solutions(puzzle[:], limit=2) == 1


def test_remove_cells_symmetric():
    from app.ml.gan import remove_cells
    puzzle = remove_cells(SOLVED_BOARD[:], difficulty="medium", symmetric=True)
    # For each removed cell, its 180° mirror should also be removed
    empties = [i for i, v in enumerate(puzzle) if v == 0]
    for idx in empties:
        assert puzzle[80 - idx] == 0, f"Cell {idx} removed but mirror {80-idx} is not"


# ── Board encoding tests ──────────────────────────────────────────────────────

def test_board_to_onehot_shape():
    from app.ml.gan import board_to_onehot
    t = board_to_onehot(SOLVED_BOARD)
    assert t.shape == (81, 9)


def test_board_to_onehot_values():
    from app.ml.gan import board_to_onehot
    t = board_to_onehot(SOLVED_BOARD)
    # Row sums should be 1.0 for all non-zero cells
    assert (t.sum(dim=1) == 1.0).all()


def test_board_to_onehot_empty_cells():
    from app.ml.gan import board_to_onehot
    board = SOLVED_BOARD[:]
    board[0] = 0
    t = board_to_onehot(board)
    assert t[0].sum().item() == 0.0


def test_training_batch_shapes():
    from app.ml.gan import generate_training_batch
    grids, diffs = generate_training_batch(8)
    assert grids.shape == (8, 81, 9)
    assert diffs.shape == (8,)
    assert all(0 <= d.item() <= 4 for d in diffs)


# ── GANService tests (backtracking fallback) ──────────────────────────────────

def test_gan_service_generate_puzzle_mode():
    from app.services.gan_service import GANPuzzleService
    svc = GANPuzzleService()  # fresh instance, no model loaded
    results = svc.generate(mode="puzzle", difficulty="easy", count=1)
    assert len(results) == 1
    r = results[0]
    assert r["source"] == "backtracking"
    assert r["puzzle"] is not None
    assert len(r["puzzle"]) == 81
    assert len(r["solution"]) == 81
    assert r["valid"] is True


def test_gan_service_generate_solution_mode():
    from app.services.gan_service import GANPuzzleService
    svc = GANPuzzleService()
    results = svc.generate(mode="solution", difficulty="medium", count=1)
    r = results[0]
    assert r["puzzle"] is None
    assert r["clue_count"] == 81


def test_gan_service_generate_constrained_mode():
    from app.services.gan_service import GANPuzzleService
    from app.ml.gan import _count_solutions
    svc = GANPuzzleService()
    results = svc.generate(mode="constrained", difficulty="easy", count=1)
    r = results[0]
    assert r["puzzle"] is not None
    # Symmetric: mirror pairs should both be empty
    puzzle = r["puzzle"]
    empties = [i for i, v in enumerate(puzzle) if v == 0]
    for idx in empties:
        assert puzzle[80 - idx] == 0


def test_gan_service_generate_batch():
    from app.services.gan_service import GANPuzzleService
    svc = GANPuzzleService()
    results = svc.generate(mode="puzzle", difficulty="medium", count=3)
    assert len(results) == 3


def test_gan_service_invalid_mode():
    from app.services.gan_service import GANPuzzleService
    svc = GANPuzzleService()
    with pytest.raises(ValueError, match="mode"):
        svc.generate(mode="invalid_mode", difficulty="easy", count=1)


def test_gan_service_invalid_difficulty():
    from app.services.gan_service import GANPuzzleService
    svc = GANPuzzleService()
    with pytest.raises(ValueError, match="difficulty"):
        svc.generate(mode="puzzle", difficulty="godlike", count=1)


def test_gan_service_count_limit():
    from app.services.gan_service import GANPuzzleService
    svc = GANPuzzleService()
    with pytest.raises(ValueError, match="count"):
        svc.generate(mode="puzzle", difficulty="easy", count=11)


def test_gan_service_status_no_model():
    from app.services.gan_service import GANPuzzleService
    svc = GANPuzzleService()
    status = svc.status()
    assert status["loaded"] is False
    assert status["fallback"] == "backtracking"


# ── FastAPI endpoint tests ─────────────────────────────────────────────────────

@pytest.fixture
def client():
    from app.main import create_app
    return TestClient(create_app())


def test_generate_endpoint_200(client):
    resp = client.post(
        "/api/v1/gan/generate",
        json={"mode": "puzzle", "difficulty": "easy"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "puzzle" in data
    assert len(data["puzzle"]["solution"]) == 81
    assert len(data["puzzle"]["puzzle"]) == 81
    assert data["puzzle"]["valid"] is True


def test_generate_endpoint_solution_mode(client):
    resp = client.post(
        "/api/v1/gan/generate",
        json={"mode": "solution", "difficulty": "hard"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["puzzle"]["puzzle"] is None
    assert data["puzzle"]["clue_count"] == 81


def test_generate_endpoint_constrained_mode(client):
    resp = client.post(
        "/api/v1/gan/generate",
        json={"mode": "constrained", "difficulty": "medium", "symmetric": True},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["puzzle"]["puzzle"] is not None


def test_batch_endpoint_count(client):
    resp = client.post(
        "/api/v1/gan/batch",
        json={"mode": "puzzle", "difficulty": "medium", "count": 3},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 3
    assert len(data["puzzles"]) == 3


def test_batch_endpoint_count_limit(client):
    resp = client.post(
        "/api/v1/gan/batch",
        json={"mode": "puzzle", "difficulty": "easy", "count": 11},
    )
    assert resp.status_code == 422


def test_status_endpoint(client):
    resp = client.get("/api/v1/gan/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "loaded" in data
    assert "model_path" in data


def test_generate_endpoint_all_difficulties(client):
    for diff in ["easy", "medium", "hard", "super_hard", "extreme"]:
        resp = client.post(
            "/api/v1/gan/generate",
            json={"mode": "puzzle", "difficulty": diff},
        )
        assert resp.status_code == 200, f"Failed for difficulty={diff}"
        assert resp.json()["puzzle"]["difficulty"] == diff
