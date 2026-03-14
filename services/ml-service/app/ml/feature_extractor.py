"""
feature_extractor.py — Session behaviour feature extraction for anti-cheat.

Converts raw game-session statistics into a 10-dimensional normalised
feature vector suitable for the sparse autoencoder.

Feature index map:
  0  time_mean_norm      mean inter-fill time normalised to [0, 1]   (fast → low)
  1  time_std_norm       std-dev of inter-fill times, normalised
  2  time_min_norm       minimum inter-fill time, normalised
  3  time_p10_norm       10th-percentile fill time, normalised        (speed burst)
  4  error_rate          wrong fills / total fill attempts
  5  hint_rate           hints used / cells_to_fill
  6  fill_rate_norm      cells-per-second, normalised
  7  duration_ratio      actual_ms / difficulty_baseline_ms, capped at 1
  8  completion_ratio    cells_filled / cells_to_fill, capped at 1
  9  consistency_score   1 - (time_std / max(1, time_mean))          (uniform → high)
"""

from __future__ import annotations

import math
from typing import Optional

import numpy as np

# ── Difficulty baselines ────────────────────────────────────────────────────────

# Expected solve durations (ms) for an average human player.
DIFFICULTY_BASELINE_MS: dict[str, int] = {
    "super_easy": 90_000,
    "beginner": 120_000,
    "easy": 180_000,
    "medium": 300_000,
    "hard": 480_000,
    "expert": 720_000,
    "evil": 1_200_000,
}

# Expected cells to fill by difficulty (clue count subtracted from 81).
DIFFICULTY_CELLS_TO_FILL: dict[str, int] = {
    "super_easy": 30,
    "beginner": 35,
    "easy": 40,
    "medium": 45,
    "hard": 50,
    "expert": 55,
    "evil": 60,
}

# Normalisation caps for timing features.
MAX_FILL_TIME_MS = 10_000   # anything above 10 s/cell → saturated at 1
MAX_FILL_RATE = 2.0          # cells/second cap for normalisation

FEATURE_DIM = 10


def extract_features(
    *,
    time_elapsed_ms: int,
    cells_filled: int,
    errors_count: int,
    hints_used: int,
    difficulty: str,
    cells_to_fill: Optional[int] = None,
    cell_fill_times_ms: Optional[list[int]] = None,
) -> np.ndarray:
    """
    Compute the 10-dimensional normalised feature vector from session data.

    Parameters
    ----------
    time_elapsed_ms    Total elapsed session time in milliseconds.
    cells_filled       Number of cells the player filled (correct only).
    errors_count       Number of incorrect cell entries.
    hints_used         Number of hints requested.
    difficulty         Puzzle difficulty string.
    cells_to_fill      Expected cells to fill; inferred from difficulty if None.
    cell_fill_times_ms Optional list of individual inter-fill times in ms.

    Returns
    -------
    np.ndarray of shape (10,), dtype float32, all values in [0, 1].
    """
    ctf = cells_to_fill or DIFFICULTY_CELLS_TO_FILL.get(difficulty, 45)
    ctf = max(1, ctf)

    baseline_ms = DIFFICULTY_BASELINE_MS.get(difficulty, 300_000)
    total_attempts = max(1, cells_filled + errors_count)

    # ── Timing features ────────────────────────────────────────────────────────
    if cell_fill_times_ms and len(cell_fill_times_ms) >= 2:
        arr = np.array(cell_fill_times_ms, dtype=float)
        t_mean = float(np.mean(arr))
        t_std = float(np.std(arr))
        t_min = float(np.min(arr))
        t_p10 = float(np.percentile(arr, 10))
    else:
        # Approximate from session totals when per-cell times are unavailable.
        mean_approx = time_elapsed_ms / max(1, cells_filled)
        t_mean = mean_approx
        t_std = mean_approx * 0.4  # typical human variance ~40%
        t_min = max(50.0, mean_approx * 0.2)
        t_p10 = max(50.0, mean_approx * 0.3)

    f0 = min(1.0, t_mean / MAX_FILL_TIME_MS)
    f1 = min(1.0, t_std / MAX_FILL_TIME_MS)
    f2 = min(1.0, t_min / MAX_FILL_TIME_MS)
    f3 = min(1.0, t_p10 / MAX_FILL_TIME_MS)

    # ── Rate features ──────────────────────────────────────────────────────────
    f4 = min(1.0, errors_count / total_attempts)          # error_rate
    f5 = min(1.0, hints_used / ctf)                       # hint_rate

    fill_rate = cells_filled / max(1, time_elapsed_ms / 1_000)
    f6 = min(1.0, fill_rate / MAX_FILL_RATE)              # fill_rate_norm

    # ── Session-level features ─────────────────────────────────────────────────
    f7 = min(1.0, time_elapsed_ms / baseline_ms)          # duration_ratio
    f8 = min(1.0, cells_filled / ctf)                     # completion_ratio

    # Timing consistency: 0 = perfectly uniform (suspicious), 1 = natural variance
    consistency = t_std / max(1.0, t_mean)
    f9 = min(1.0, consistency)                            # consistency_score

    return np.array([f0, f1, f2, f3, f4, f5, f6, f7, f8, f9], dtype=np.float32)


def generate_normal_features(n: int = 1_000, rng: Optional[np.random.Generator] = None) -> np.ndarray:
    """
    Generate synthetic 'normal' (human-like) feature vectors for autoencoder training.

    Returns shape (n, 10) float32.
    """
    if rng is None:
        rng = np.random.default_rng(42)

    # Mean inter-fill time: human players take 1–5 s/cell on average.
    t_mean_ms = rng.normal(2_500, 800, size=n).clip(500, 9_000)
    t_std_ms = (t_mean_ms * rng.uniform(0.25, 0.65, size=n)).clip(200, 5_000)
    t_min_ms = (t_mean_ms * rng.uniform(0.15, 0.40, size=n)).clip(100, 3_000)
    t_p10_ms = (t_mean_ms * rng.uniform(0.20, 0.45, size=n)).clip(150, 4_000)

    f0 = (t_mean_ms / MAX_FILL_TIME_MS).clip(0, 1)
    f1 = (t_std_ms / MAX_FILL_TIME_MS).clip(0, 1)
    f2 = (t_min_ms / MAX_FILL_TIME_MS).clip(0, 1)
    f3 = (t_p10_ms / MAX_FILL_TIME_MS).clip(0, 1)

    # Error rate: beta(2, 8) centres around ~0.2 (humans make mistakes).
    f4 = rng.beta(2, 8, size=n).clip(0, 1)
    # Hint rate: beta(1, 6) — occasional hints.
    f5 = rng.beta(1, 6, size=n).clip(0, 1)
    # Fill rate: 0.1–0.5 cells/s is normal human pace.
    f6 = rng.uniform(0.05, 0.35, size=n).clip(0, 1)
    # Duration ratio: humans often take 0.5–1.5× the baseline.
    f7 = rng.normal(0.85, 0.25, size=n).clip(0.2, 1.0)
    # Completion ratio: sessions we train on are completed.
    f8 = rng.uniform(0.9, 1.0, size=n).clip(0, 1)
    # Consistency score: humans have 30–70% natural variance.
    f9 = rng.uniform(0.30, 0.70, size=n).clip(0, 1)

    return np.column_stack([f0, f1, f2, f3, f4, f5, f6, f7, f8, f9]).astype(np.float32)


def generate_anomalous_features(n: int = 200, rng: Optional[np.random.Generator] = None) -> np.ndarray:
    """
    Generate synthetic 'anomalous' (bot/cheat-like) feature vectors for evaluation.

    Characteristics:
    - Extremely fast fill times (< 200 ms/cell)
    - Near-zero error rate
    - No hints
    - Highly consistent timing (bot-like regularity)

    Returns shape (n, 10) float32.
    """
    if rng is None:
        rng = np.random.default_rng(99)

    t_mean_ms = rng.uniform(80, 250, size=n)
    t_std_ms = (t_mean_ms * rng.uniform(0.02, 0.08, size=n)).clip(5, 30)
    t_min_ms = (t_mean_ms * rng.uniform(0.80, 0.95, size=n)).clip(5, 200)
    t_p10_ms = (t_mean_ms * rng.uniform(0.85, 0.97, size=n)).clip(5, 220)

    f0 = (t_mean_ms / MAX_FILL_TIME_MS).clip(0, 1)
    f1 = (t_std_ms / MAX_FILL_TIME_MS).clip(0, 1)
    f2 = (t_min_ms / MAX_FILL_TIME_MS).clip(0, 1)
    f3 = (t_p10_ms / MAX_FILL_TIME_MS).clip(0, 1)
    f4 = rng.uniform(0.0, 0.02, size=n)    # near-zero error rate
    f5 = rng.uniform(0.0, 0.01, size=n)    # no hints
    f6 = rng.uniform(0.70, 1.00, size=n)   # very high fill rate
    f7 = rng.uniform(0.05, 0.20, size=n)   # solves far faster than baseline
    f8 = rng.uniform(0.98, 1.00, size=n)   # always completes
    f9 = rng.uniform(0.01, 0.08, size=n)   # uniform timing = low consistency score

    return np.column_stack([f0, f1, f2, f3, f4, f5, f6, f7, f8, f9]).astype(np.float32)
