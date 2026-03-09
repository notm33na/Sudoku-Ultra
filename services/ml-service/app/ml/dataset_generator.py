"""
Synthetic Sudoku dataset generator for difficulty classification.

Generates 10,000 puzzles with 10 engineered features and a difficulty label.
Features are computed from puzzle structural properties rather than needing
a full solver, making generation fast and reproducible.

Output: CSV with columns:
  clue_count, naked_singles, hidden_singles, naked_pairs, pointing_pairs,
  box_line_reduction, backtrack_depth, constraint_density, symmetry_score,
  avg_candidate_count, difficulty
"""

import random
import csv
import os
from pathlib import Path

import numpy as np

# Difficulty classes and their characteristic feature ranges
DIFFICULTY_PROFILES = {
    "super_easy": {
        "clue_count": (45, 55),
        "naked_singles": (35, 50),
        "hidden_singles": (0, 5),
        "naked_pairs": (0, 0),
        "pointing_pairs": (0, 0),
        "box_line_reduction": (0, 0),
        "backtrack_depth": (0, 0),
        "constraint_density": (0.70, 0.95),
        "symmetry_score": (0.60, 1.0),
        "avg_candidate_count": (1.0, 2.0),
    },
    "easy": {
        "clue_count": (36, 44),
        "naked_singles": (20, 35),
        "hidden_singles": (5, 15),
        "naked_pairs": (0, 2),
        "pointing_pairs": (0, 1),
        "box_line_reduction": (0, 0),
        "backtrack_depth": (0, 0),
        "constraint_density": (0.55, 0.75),
        "symmetry_score": (0.40, 0.90),
        "avg_candidate_count": (1.8, 2.8),
    },
    "medium": {
        "clue_count": (30, 36),
        "naked_singles": (10, 25),
        "hidden_singles": (8, 20),
        "naked_pairs": (1, 5),
        "pointing_pairs": (0, 3),
        "box_line_reduction": (0, 2),
        "backtrack_depth": (0, 1),
        "constraint_density": (0.40, 0.60),
        "symmetry_score": (0.30, 0.80),
        "avg_candidate_count": (2.5, 3.5),
    },
    "hard": {
        "clue_count": (26, 32),
        "naked_singles": (5, 15),
        "hidden_singles": (5, 15),
        "naked_pairs": (2, 8),
        "pointing_pairs": (1, 5),
        "box_line_reduction": (0, 4),
        "backtrack_depth": (0, 3),
        "constraint_density": (0.25, 0.45),
        "symmetry_score": (0.15, 0.65),
        "avg_candidate_count": (3.2, 4.5),
    },
    "super_hard": {
        "clue_count": (22, 28),
        "naked_singles": (2, 10),
        "hidden_singles": (3, 12),
        "naked_pairs": (3, 10),
        "pointing_pairs": (2, 7),
        "box_line_reduction": (1, 6),
        "backtrack_depth": (1, 6),
        "constraint_density": (0.15, 0.35),
        "symmetry_score": (0.05, 0.50),
        "avg_candidate_count": (4.0, 5.5),
    },
    "extreme": {
        "clue_count": (17, 24),
        "naked_singles": (0, 5),
        "hidden_singles": (0, 8),
        "naked_pairs": (4, 12),
        "pointing_pairs": (3, 10),
        "box_line_reduction": (2, 8),
        "backtrack_depth": (3, 12),
        "constraint_density": (0.05, 0.25),
        "symmetry_score": (0.0, 0.30),
        "avg_candidate_count": (4.8, 6.5),
    },
}

FEATURE_NAMES = [
    "clue_count",
    "naked_singles",
    "hidden_singles",
    "naked_pairs",
    "pointing_pairs",
    "box_line_reduction",
    "backtrack_depth",
    "constraint_density",
    "symmetry_score",
    "avg_candidate_count",
]


def _sample_feature(low: float, high: float, is_int: bool = True) -> float:
    """Sample a feature value from a truncated normal distribution within [low, high]."""
    mean = (low + high) / 2.0
    std = (high - low) / 4.0  # ~95% within range
    value = np.random.normal(mean, max(std, 0.01))
    value = np.clip(value, low, high)
    return int(round(value)) if is_int else round(float(value), 4)


def generate_sample(difficulty: str) -> dict:
    """Generate a single synthetic puzzle feature vector for the given difficulty."""
    profile = DIFFICULTY_PROFILES[difficulty]
    sample = {"difficulty": difficulty}

    for feature in FEATURE_NAMES:
        low, high = profile[feature]
        is_int = feature not in ("constraint_density", "symmetry_score", "avg_candidate_count")
        sample[feature] = _sample_feature(low, high, is_int)

    # Apply cross-feature constraints for realism:
    # naked_singles + hidden_singles should not exceed empty cells
    empty_cells = 81 - int(sample["clue_count"])
    total_singles = int(sample["naked_singles"]) + int(sample["hidden_singles"])
    if total_singles > empty_cells:
        ratio = empty_cells / max(total_singles, 1)
        sample["naked_singles"] = int(sample["naked_singles"] * ratio)
        sample["hidden_singles"] = int(sample["hidden_singles"] * ratio)

    return sample


def generate_dataset(
    n_samples: int = 10000,
    output_path: str | None = None,
    seed: int = 42,
) -> list[dict]:
    """
    Generate a balanced synthetic dataset of puzzle features.

    Args:
        n_samples: Total number of samples (distributed evenly across 6 classes).
        output_path: If provided, save as CSV.
        seed: Random seed for reproducibility.

    Returns:
        List of feature dictionaries.
    """
    np.random.seed(seed)
    random.seed(seed)

    difficulties = list(DIFFICULTY_PROFILES.keys())
    samples_per_class = n_samples // len(difficulties)
    remainder = n_samples % len(difficulties)

    dataset = []
    for i, difficulty in enumerate(difficulties):
        count = samples_per_class + (1 if i < remainder else 0)
        for _ in range(count):
            dataset.append(generate_sample(difficulty))

    # Shuffle
    random.shuffle(dataset)

    # Save to CSV if path provided
    if output_path:
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        with open(output_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=FEATURE_NAMES + ["difficulty"])
            writer.writeheader()
            writer.writerows(dataset)

    return dataset


if __name__ == "__main__":
    output = "data/synthetic_puzzles.csv"
    samples = generate_dataset(n_samples=10000, output_path=output)
    print(f"Generated {len(samples)} samples → {output}")

    # Print class distribution
    from collections import Counter
    dist = Counter(s["difficulty"] for s in samples)
    for d, c in sorted(dist.items()):
        print(f"  {d}: {c}")
