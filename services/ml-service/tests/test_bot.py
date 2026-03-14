"""
test_bot.py — pytest suite for the RL bot service and API router.

Tests are grouped:
  - Puzzle generator (sudoku_env.py)
  - SudokuEnv Gymnasium environment
  - BotService rule-based fallback (no model required)
  - FastAPI endpoint (httpx AsyncClient)
"""

from __future__ import annotations

import pytest
import numpy as np


# ─── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture()
def simple_puzzle():
    """A near-complete puzzle with only cell 0 empty; solution fills it with 1."""
    solution = list(range(1, 82))  # 1–81 (not a valid sudoku, but good for unit tests)
    # Normalise digits to 1–9 range using modulo.
    solution = [(v - 1) % 9 + 1 for v in solution]
    board = solution[:]
    board[0] = 0  # one empty cell
    return board, solution


@pytest.fixture()
def full_board():
    """A board where every cell is filled."""
    solution = [(i % 9) + 1 for i in range(81)]
    return solution[:], solution[:]


@pytest.fixture()
def real_puzzle():
    """Generate a real Sudoku puzzle for environment tests."""
    from app.ml.sudoku_env import generate_puzzle
    return generate_puzzle(clues=32)


# ─── Puzzle Generator Tests ───────────────────────────────────────────────────

class TestPuzzleGenerator:
    def test_generate_puzzle_returns_correct_lengths(self):
        from app.ml.sudoku_env import generate_puzzle
        board, solution = generate_puzzle(clues=32)
        assert len(board) == 81
        assert len(solution) == 81

    def test_generate_puzzle_solution_is_complete(self):
        from app.ml.sudoku_env import generate_puzzle
        _, solution = generate_puzzle(clues=32)
        assert all(1 <= v <= 9 for v in solution), "Solution must contain only 1–9"
        assert 0 not in solution, "Solution must have no empty cells"

    def test_generate_puzzle_given_cells_are_subset_of_solution(self):
        from app.ml.sudoku_env import generate_puzzle
        board, solution = generate_puzzle(clues=35)
        for i, v in enumerate(board):
            if v != 0:
                assert v == solution[i], f"Given cell {i} mismatch: board={v} sol={solution[i]}"

    def test_generate_puzzle_clue_count(self):
        from app.ml.sudoku_env import generate_puzzle
        board, _ = generate_puzzle(clues=40)
        given = sum(1 for v in board if v != 0)
        assert given == 40, f"Expected 40 given cells, got {given}"

    def test_generate_puzzle_pool_size(self):
        from app.ml.sudoku_env import generate_puzzle_pool
        pool = generate_puzzle_pool(n=10, clues=32)
        assert len(pool) == 10
        for board, solution in pool:
            assert len(board) == 81
            assert len(solution) == 81


# ─── SudokuEnv Tests ──────────────────────────────────────────────────────────

class TestSudokuEnv:
    def test_reset_returns_correct_observation_shape(self, real_puzzle):
        from app.ml.sudoku_env import SudokuEnv
        env = SudokuEnv([real_puzzle])
        obs, info = env.reset()
        assert obs.shape == (810,)
        assert info == {}

    def test_observation_board_portion_matches_puzzle(self, real_puzzle):
        from app.ml.sudoku_env import SudokuEnv
        board, solution = real_puzzle
        env = SudokuEnv([(board, solution)])
        obs, _ = env.reset()
        np.testing.assert_array_equal(obs[:81], board)

    def test_step_correct_placement_gives_positive_reward(self, real_puzzle):
        from app.ml.sudoku_env import SudokuEnv
        board, solution = real_puzzle
        env = SudokuEnv([(board, solution)])
        env.reset()
        # Find first empty cell and correct digit.
        for i, v in enumerate(board):
            if v == 0:
                action = i * 9 + (solution[i] - 1)
                _, reward, _, _, _ = env.step(action)
                assert reward > 0, f"Correct placement should give positive reward, got {reward}"
                return
        pytest.skip("No empty cells in puzzle")

    def test_step_wrong_placement_gives_negative_reward(self, real_puzzle):
        from app.ml.sudoku_env import SudokuEnv
        board, solution = real_puzzle
        env = SudokuEnv([(board, solution)])
        env.reset()
        for i, v in enumerate(board):
            if v == 0:
                wrong_digit = solution[i] % 9 + 1  # guaranteed different
                if wrong_digit == solution[i]:
                    wrong_digit = (solution[i] % 9) + 1 or 1
                # Only proceed if it's actually wrong.
                if wrong_digit != solution[i]:
                    action = i * 9 + (wrong_digit - 1)
                    _, reward, _, _, _ = env.step(action)
                    assert reward < 0, f"Wrong placement should give negative reward, got {reward}"
                    return
        pytest.skip("Could not find a testable wrong placement")

    def test_step_overwriting_given_cell_penalised(self, real_puzzle):
        from app.ml.sudoku_env import SudokuEnv
        board, solution = real_puzzle
        env = SudokuEnv([(board, solution)])
        env.reset()
        for i, v in enumerate(board):
            if v != 0:
                action = i * 9 + (v - 1)
                _, reward, _, _, _ = env.step(action)
                assert reward < 0
                return
        pytest.skip("No given cells in puzzle")

    def test_truncation_after_max_steps(self, real_puzzle):
        from app.ml.sudoku_env import SudokuEnv
        env = SudokuEnv([real_puzzle], max_steps=3)
        env.reset()
        truncated = False
        for _ in range(3):
            _, _, _, truncated, _ = env.step(0)
        assert truncated

    def test_action_mask_marks_empty_cells(self, real_puzzle):
        from app.ml.sudoku_env import SudokuEnv
        board, solution = real_puzzle
        env = SudokuEnv([(board, solution)])
        env.reset()
        mask = env.get_action_mask()
        assert mask.shape == (729,)
        # For every given cell, ALL 9 actions for that cell must be masked False.
        for i, v in enumerate(board):
            if v != 0:
                assert not mask[i * 9 : i * 9 + 9].any(), (
                    f"Given cell {i} should have no valid actions"
                )

    def test_render_ansi_returns_string(self, real_puzzle):
        from app.ml.sudoku_env import SudokuEnv
        env = SudokuEnv([real_puzzle], render_mode="ansi")
        env.reset()
        rendered = env.render()
        assert isinstance(rendered, str)
        assert "\n" in rendered


# ─── BotService Rule-Based Tests ──────────────────────────────────────────────

class TestBotServiceRuleBased:
    """These tests use the rule-based fallback only — no trained model required."""

    def test_get_move_returns_correct_digit(self, simple_puzzle):
        from app.services.bot_service import BotService
        board, solution = simple_puzzle
        svc = BotService()
        # Patch _get_model to always return None (force rule-based).
        svc._get_model = lambda tier: None
        result = svc.get_move(board, solution, tier="medium")
        assert result["digit"] == solution[result["cell_index"]]

    def test_get_move_targets_empty_cell(self, simple_puzzle):
        from app.services.bot_service import BotService
        board, solution = simple_puzzle
        svc = BotService()
        svc._get_model = lambda tier: None
        result = svc.get_move(board, solution, tier="easy")
        assert board[result["cell_index"]] == 0, "Must target an empty cell"

    def test_get_move_easy_uses_fallback_source(self, simple_puzzle):
        from app.services.bot_service import BotService
        board, solution = simple_puzzle
        svc = BotService()
        svc._get_model = lambda tier: None
        result = svc.get_move(board, solution, tier="easy")
        assert result["source"] == "fallback"

    def test_get_move_invalid_board_length_raises(self):
        from app.services.bot_service import BotService
        svc = BotService()
        with pytest.raises(ValueError, match="81"):
            svc.get_move([0] * 80, [1] * 81, "medium")

    def test_get_move_invalid_solution_length_raises(self):
        from app.services.bot_service import BotService
        svc = BotService()
        with pytest.raises(ValueError, match="81"):
            svc.get_move([0] * 81, [1] * 80, "medium")

    def test_get_move_all_tiers_return_valid_structure(self, simple_puzzle):
        from app.services.bot_service import BotService
        board, solution = simple_puzzle
        svc = BotService()
        svc._get_model = lambda tier: None
        for tier in ("easy", "medium", "hard"):
            result = svc.get_move(board, solution, tier=tier)
            assert "cell_index" in result
            assert "digit" in result
            assert "confidence" in result
            assert "source" in result
            assert 0 <= result["cell_index"] <= 80
            assert 1 <= result["digit"] <= 9

    def test_get_move_hard_uses_mrv(self):
        """Hard tier should prefer the most-constrained cell (MRV)."""
        from app.services.bot_service import BotService
        from app.ml.sudoku_env import generate_puzzle

        board, solution = generate_puzzle(clues=45)
        svc = BotService()
        svc._get_model = lambda tier: None

        # Call multiple times — hard should be deterministic (MRV + cell index tiebreak).
        results = [svc.get_move(board[:], solution, tier="hard") for _ in range(3)]
        assert all(r["cell_index"] == results[0]["cell_index"] for r in results), (
            "Hard tier rule-based must be deterministic"
        )


# ─── FastAPI Endpoint Tests ───────────────────────────────────────────────────

class TestBotEndpoint:
    """Integration tests via httpx AsyncClient — no model loaded, uses rule-based."""

    @pytest.fixture()
    def client(self):
        from httpx import Client
        from app.main import create_app
        app = create_app()
        with Client(app=app, base_url="http://test") as c:
            yield c

    def test_post_bot_move_returns_200(self, client, simple_puzzle):
        board, solution = simple_puzzle
        resp = client.post("/api/v1/bot/move", json={
            "board": board,
            "solution": solution,
            "tier": "medium",
        })
        assert resp.status_code == 200
        body = resp.json()
        assert "cell_index" in body
        assert "digit" in body
        assert "confidence" in body
        assert "source" in body

    def test_post_bot_move_cell_is_correct(self, client, simple_puzzle):
        board, solution = simple_puzzle
        resp = client.post("/api/v1/bot/move", json={
            "board": board,
            "solution": solution,
            "tier": "easy",
        })
        body = resp.json()
        assert solution[body["cell_index"]] == body["digit"]

    def test_post_bot_move_all_filled_returns_400(self, client, full_board):
        board, solution = full_board
        resp = client.post("/api/v1/bot/move", json={
            "board": board,
            "solution": solution,
            "tier": "easy",
        })
        assert resp.status_code == 400

    def test_post_bot_move_invalid_tier_returns_422(self, client, simple_puzzle):
        board, solution = simple_puzzle
        resp = client.post("/api/v1/bot/move", json={
            "board": board,
            "solution": solution,
            "tier": "grandmaster",
        })
        assert resp.status_code == 422

    def test_post_bot_move_wrong_board_length_returns_422(self, client):
        resp = client.post("/api/v1/bot/move", json={
            "board": [0] * 80,
            "solution": [1] * 81,
            "tier": "easy",
        })
        assert resp.status_code == 422

    def test_post_bot_move_default_tier_is_medium(self, client, simple_puzzle):
        board, solution = simple_puzzle
        resp = client.post("/api/v1/bot/move", json={
            "board": board,
            "solution": solution,
            # tier omitted — should default to "medium"
        })
        assert resp.status_code == 200
