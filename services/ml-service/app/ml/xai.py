"""
XAI (explainability) module — maps classifier SHAP values to per-cell importance.

Pipeline:
  board + puzzle  →  extract_features  →  DifficultyClassifier.predict  →  SHAP dict
                  →  map_shap_to_cells  →  list[float] (81 values, 0-1 normalised)

The difficulty classifier uses 10 aggregate features.  We map them back to
cells by analysing which cells contribute to each feature:

  naked_singles       → cells with exactly 1 candidate
  hidden_singles      → cells that are hidden-single targets
  naked_pairs         → cells in naked-pair groups
  pointing_pairs      → cells in pointing-pair rows/cols within boxes
  box_line_reduction  → cells eliminated by box-line reduction
  backtrack_depth     → cells with fewest candidates (proxy for forcing chains)
  avg_candidate_count → inverse of each cell's candidate count
  constraint_density  → cells in densely-filled rows/cols/boxes
  clue_count          → given (non-zero) cells in the original puzzle
  symmetry_score      → uniform weight (board-level feature, not cell-level)

Cell importance = weighted sum of per-technique scores, then min-max normalised.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np

from app.ml.dataset_generator import FEATURE_NAMES


# ── Sudoku constraint helpers ─────────────────────────────────────────────────

def _candidates(board: list[int], idx: int) -> set[int]:
    r, c = divmod(idx, 9)
    box_r, box_c = (r // 3) * 3, (c // 3) * 3
    used: set[int] = set()
    for col in range(9):
        used.add(board[r * 9 + col])
    for row in range(9):
        used.add(board[row * 9 + c])
    for dr in range(3):
        for dc in range(3):
            used.add(board[(box_r + dr) * 9 + (box_c + dc)])
    return set(range(1, 10)) - used


def _all_candidates(board: list[int]) -> list[set[int]]:
    return [_candidates(board, i) if board[i] == 0 else set() for i in range(81)]


# ── Feature extraction from a raw board ──────────────────────────────────────

def extract_features(board: list[int], puzzle: list[int]) -> dict[str, float]:
    """
    Compute the 10 classifier features from a raw Sudoku board.

    `board` is the current state (0 = empty).
    `puzzle` is the original puzzle (0 = empty clue cells).
    """
    cands = _all_candidates(board)
    empty_cells = [i for i, v in enumerate(board) if v == 0]

    # clue_count: number of given cells in original puzzle
    clue_count = sum(1 for v in puzzle if v != 0)

    # naked_singles
    naked_singles = sum(1 for i in empty_cells if len(cands[i]) == 1)

    # hidden_singles (row + col + box, count unique cells, not instances)
    hidden_single_cells: set[int] = set()
    for digit in range(1, 10):
        for row in range(9):
            positions = [row * 9 + col for col in range(9)
                         if board[row * 9 + col] == 0 and digit in cands[row * 9 + col]]
            if len(positions) == 1:
                hidden_single_cells.add(positions[0])
        for col in range(9):
            positions = [row * 9 + col for row in range(9)
                         if board[row * 9 + col] == 0 and digit in cands[row * 9 + col]]
            if len(positions) == 1:
                hidden_single_cells.add(positions[0])
        for br in range(3):
            for bc in range(3):
                positions = [
                    (br * 3 + dr) * 9 + (bc * 3 + dc)
                    for dr in range(3) for dc in range(3)
                    if board[(br * 3 + dr) * 9 + (bc * 3 + dc)] == 0
                    and digit in cands[(br * 3 + dr) * 9 + (bc * 3 + dc)]
                ]
                if len(positions) == 1:
                    hidden_single_cells.add(positions[0])
    hidden_singles = len(hidden_single_cells)

    # naked_pairs: count pairs in same row/col/box with identical 2-candidate sets
    naked_pairs = 0
    pair_cells: set[int] = set()
    _two_cand = [(i, frozenset(cands[i])) for i in empty_cells if len(cands[i]) == 2]

    def _check_group(group: list[int]) -> None:
        nonlocal naked_pairs
        group_two = [(i, cs) for i, cs in _two_cand if i in group]
        seen: dict[frozenset, list[int]] = {}
        for i, cs in group_two:
            seen.setdefault(cs, []).append(i)
        for cs, cells in seen.items():
            if len(cells) == 2:
                naked_pairs += 1
                pair_cells.update(cells)

    for row in range(9):
        _check_group([row * 9 + col for col in range(9)])
    for col in range(9):
        _check_group([row * 9 + col for row in range(9)])
    for br in range(3):
        for bc in range(3):
            _check_group([(br * 3 + dr) * 9 + (bc * 3 + dc) for dr in range(3) for dc in range(3)])

    # pointing_pairs / box-line reduction: count digit-box-row/col intersections
    pointing_pairs = 0
    box_line_reduction = 0
    for digit in range(1, 10):
        for br in range(3):
            for bc in range(3):
                box_cells = [
                    (br * 3 + dr) * 9 + (bc * 3 + dc)
                    for dr in range(3) for dc in range(3)
                ]
                box_positions = [i for i in box_cells
                                 if board[i] == 0 and digit in cands[i]]
                if not box_positions:
                    continue
                rows_used = {p // 9 for p in box_positions}
                cols_used = {p % 9 for p in box_positions}
                if len(rows_used) == 1:
                    pointing_pairs += 1
                    row = next(iter(rows_used))
                    row_non_box = [row * 9 + col for col in range(9)
                                   if col // 3 != bc and board[row * 9 + col] == 0
                                   and digit in cands[row * 9 + col]]
                    box_line_reduction += len(row_non_box)
                if len(cols_used) == 1:
                    pointing_pairs += 1
                    col = next(iter(cols_used))
                    col_non_box = [row2 * 9 + col for row2 in range(9)
                                   if row2 // 3 != br and board[row2 * 9 + col] == 0
                                   and digit in cands[row2 * 9 + col]]
                    box_line_reduction += len(col_non_box)

    # backtrack_depth: proxy — fraction of cells needing guessing
    simple_cells = hidden_single_cells | {i for i in empty_cells if len(cands[i]) == 1}
    backtrack_depth = max(0, len(empty_cells) - len(simple_cells)) // 5

    # constraint_density: average fraction of a cell's peers that are filled
    def _peer_fill(idx: int) -> float:
        r, c = divmod(idx, 9)
        br, bc = r // 3, c // 3
        peers: set[int] = set()
        peers.update(r * 9 + cc for cc in range(9) if cc != c)
        peers.update(rr * 9 + c for rr in range(9) if rr != r)
        peers.update(
            (br * 3 + dr) * 9 + (bc * 3 + dc)
            for dr in range(3) for dc in range(3)
            if (br * 3 + dr) != r or (bc * 3 + dc) != c
        )
        filled = sum(1 for p in peers if board[p] != 0)
        return filled / len(peers)

    constraint_density = (
        float(np.mean([_peer_fill(i) for i in empty_cells])) if empty_cells else 0.0
    )

    # symmetry_score: fraction of given cells whose 180° partner is also given
    symmetric = sum(
        1 for i, v in enumerate(puzzle)
        if v != 0 and puzzle[80 - i] != 0
    )
    symmetry_score = symmetric / clue_count if clue_count else 0.0

    # avg_candidate_count
    avg_candidate_count = (
        float(np.mean([len(cands[i]) for i in empty_cells])) if empty_cells else 0.0
    )

    return {
        "clue_count": float(clue_count),
        "naked_singles": float(naked_singles),
        "hidden_singles": float(hidden_singles),
        "naked_pairs": float(naked_pairs),
        "pointing_pairs": float(pointing_pairs),
        "box_line_reduction": float(box_line_reduction),
        "backtrack_depth": float(backtrack_depth),
        "constraint_density": round(constraint_density, 4),
        "symmetry_score": round(symmetry_score, 4),
        "avg_candidate_count": round(avg_candidate_count, 4),
    }


# ── Per-cell SHAP attribution ─────────────────────────────────────────────────

def map_shap_to_cells(
    board: list[int],
    puzzle: list[int],
    shap_values: dict[str, float],
) -> list[float]:
    """
    Convert aggregate SHAP values into 81 per-cell importance scores.

    Strategy per feature:
      naked_singles       → cells with 1 candidate get |shap| weight
      hidden_singles      → hidden-single target cells
      naked_pairs         → cells participating in naked pairs
      pointing_pairs /    → empty cells in constrained rows/cols
      box_line_reduction
      backtrack_depth     → cells with fewest candidates (hardest)
      avg_candidate_count → inverse of candidate count
      constraint_density  → cells with densest peer filling
      clue_count          → given cells get their own weight
      symmetry_score      → uniform (board-level), distributed evenly
    """
    cands = _all_candidates(board)
    empty_cells = [i for i, v in enumerate(board) if v == 0]
    scores = [0.0] * 81

    def _add(indices: list[int], weight: float) -> None:
        for i in indices:
            scores[i] += weight

    # naked_singles
    w = abs(shap_values.get("naked_singles", 0.0))
    if w > 0:
        ns_cells = [i for i in empty_cells if len(cands[i]) == 1]
        _add(ns_cells, w)

    # hidden_singles (recompute here for cell indices)
    w = abs(shap_values.get("hidden_singles", 0.0))
    if w > 0:
        hs_cells: set[int] = set()
        for digit in range(1, 10):
            for row in range(9):
                pos = [row * 9 + col for col in range(9)
                       if board[row * 9 + col] == 0 and digit in cands[row * 9 + col]]
                if len(pos) == 1:
                    hs_cells.add(pos[0])
            for col in range(9):
                pos = [row * 9 + col for row in range(9)
                       if board[row * 9 + col] == 0 and digit in cands[row * 9 + col]]
                if len(pos) == 1:
                    hs_cells.add(pos[0])
            for br in range(3):
                for bc in range(3):
                    pos = [
                        (br * 3 + dr) * 9 + (bc * 3 + dc)
                        for dr in range(3) for dc in range(3)
                        if board[(br * 3 + dr) * 9 + (bc * 3 + dc)] == 0
                        and digit in cands[(br * 3 + dr) * 9 + (bc * 3 + dc)]
                    ]
                    if len(pos) == 1:
                        hs_cells.add(pos[0])
        _add(list(hs_cells), w)

    # naked_pairs: cells in 2-candidate pairs
    w = abs(shap_values.get("naked_pairs", 0.0))
    if w > 0:
        pair_c: set[int] = set()
        _two_cand = [(i, frozenset(cands[i])) for i in empty_cells if len(cands[i]) == 2]
        for group in (
            [row * 9 + col for col in range(9)] for row in range(9)
        ):
            seen: dict[frozenset, list[int]] = {}
            for i, cs in [(i, cs) for i, cs in _two_cand if i in group]:
                seen.setdefault(cs, []).append(i)
            for cs, cells in seen.items():
                if len(cells) == 2:
                    pair_c.update(cells)
        _add(list(pair_c), w)

    # pointing_pairs + box_line_reduction → cells in constrained intersections
    pp_w = abs(shap_values.get("pointing_pairs", 0.0))
    bl_w = abs(shap_values.get("box_line_reduction", 0.0))
    if pp_w + bl_w > 0:
        inter_cells: set[int] = set()
        for digit in range(1, 10):
            for br in range(3):
                for bc in range(3):
                    box_cells = [
                        (br * 3 + dr) * 9 + (bc * 3 + dc)
                        for dr in range(3) for dc in range(3)
                    ]
                    bpos = [i for i in box_cells
                            if board[i] == 0 and digit in cands[i]]
                    if not bpos:
                        continue
                    rows_used = {p // 9 for p in bpos}
                    cols_used = {p % 9 for p in bpos}
                    if len(rows_used) == 1 or len(cols_used) == 1:
                        inter_cells.update(bpos)
        _add(list(inter_cells), pp_w + bl_w)

    # backtrack_depth: cells with fewest candidates
    w = abs(shap_values.get("backtrack_depth", 0.0))
    if w > 0 and empty_cells:
        min_cands = min(len(cands[i]) for i in empty_cells if cands[i])
        hard_cells = [i for i in empty_cells if len(cands[i]) <= min_cands + 1]
        _add(hard_cells, w)

    # avg_candidate_count: inverse of candidate count (fewer = more important)
    w = abs(shap_values.get("avg_candidate_count", 0.0))
    if w > 0 and empty_cells:
        for i in empty_cells:
            nc = len(cands[i])
            if nc > 0:
                scores[i] += w * (1.0 / nc)

    # constraint_density: cells with densest filled peers
    w = abs(shap_values.get("constraint_density", 0.0))
    if w > 0 and empty_cells:
        densities = []
        for i in empty_cells:
            r, c = divmod(i, 9)
            br, bc = r // 3, c // 3
            peers: set[int] = set()
            peers.update(r * 9 + cc for cc in range(9) if cc != c)
            peers.update(rr * 9 + c for rr in range(9) if rr != r)
            peers.update(
                (br * 3 + dr) * 9 + (bc * 3 + dc)
                for dr in range(3) for dc in range(3)
                if (br * 3 + dr) != r or (bc * 3 + dc) != c
            )
            densities.append(sum(1 for p in peers if board[p] != 0) / len(peers))
        max_d = max(densities) or 1.0
        for i, d in zip(empty_cells, densities):
            scores[i] += w * (d / max_d)

    # clue_count: given cells get a uniform base weight
    w = abs(shap_values.get("clue_count", 0.0))
    if w > 0:
        given_cells = [i for i in range(81) if puzzle[i] != 0]
        _add(given_cells, w / max(len(given_cells), 1))

    # symmetry_score: distribute uniformly across all cells (board-level feature)
    w = abs(shap_values.get("symmetry_score", 0.0))
    if w > 0:
        for i in range(81):
            scores[i] += w / 81.0

    # Min-max normalise to [0, 1]
    mn, mx = min(scores), max(scores)
    if mx > mn:
        scores = [(s - mn) / (mx - mn) for s in scores]
    else:
        scores = [0.0] * 81

    return [round(s, 4) for s in scores]


# ── Top cells ─────────────────────────────────────────────────────────────────

def top_cells(cell_importances: list[float], n: int = 9) -> list[int]:
    """Return indices of the n most important cells, sorted descending."""
    indexed = sorted(enumerate(cell_importances), key=lambda x: x[1], reverse=True)
    return [idx for idx, _ in indexed[:n] if cell_importances[idx] > 0]


# ── Full explain pipeline ─────────────────────────────────────────────────────

def explain_board(board: list[int], puzzle: list[int]) -> dict[str, Any]:
    """
    Full XAI pipeline: extract features → classify → SHAP → cell importance.

    Returns:
        cell_importances: list[float]  — 81 values, 0-1 normalised
        predicted_difficulty: str
        confidence: float
        shap_values: dict[str, float]
        top_cells: list[int]           — top-9 most important cell indices
        explanation: str
    """
    from app.services.classifier_service import classifier

    features = extract_features(board, puzzle)
    result = classifier.predict(features)

    importances = map_shap_to_cells(board, puzzle, result["shap_values"])
    important_cells = top_cells(importances)

    return {
        "cell_importances": importances,
        "predicted_difficulty": result["difficulty"],
        "confidence": result["confidence"],
        "shap_values": result["shap_values"],
        "top_cells": important_cells,
        "explanation": result["explanation"],
    }
