"""
Synthetic user gameplay feature dataset for adaptive difficulty regression.

Generates user profiles with gameplay history features and an optimal
difficulty score target (0–5 mapped to 6 difficulty classes).

Features:
  avg_solve_time_easy, avg_solve_time_medium, avg_solve_time_hard,
  hint_rate, error_rate, current_streak, session_count,
  last_played_difficulty, win_rate

Target: optimal_difficulty_score (0.0–5.0 continuous)
"""

import random
import csv
import os

import numpy as np


DIFFICULTY_MAP = {
    "super_easy": 0,
    "easy": 1,
    "medium": 2,
    "hard": 3,
    "super_hard": 4,
    "extreme": 5,
}

DIFFICULTY_NAMES = list(DIFFICULTY_MAP.keys())

FEATURE_NAMES = [
    "avg_solve_time_easy",
    "avg_solve_time_medium",
    "avg_solve_time_hard",
    "hint_rate",
    "error_rate",
    "current_streak",
    "session_count",
    "last_played_difficulty",
    "win_rate",
]

# Player archetypes used to generate realistic user profiles
PLAYER_ARCHETYPES = {
    "beginner": {
        "avg_solve_time_easy": (120, 300),
        "avg_solve_time_medium": (300, 600),
        "avg_solve_time_hard": (600, 1200),
        "hint_rate": (0.3, 0.8),
        "error_rate": (0.3, 0.7),
        "current_streak": (0, 3),
        "session_count": (1, 20),
        "last_played_difficulty": (0, 1),
        "win_rate": (0.3, 0.6),
        "optimal_score": (0.0, 1.0),
    },
    "casual": {
        "avg_solve_time_easy": (60, 180),
        "avg_solve_time_medium": (180, 400),
        "avg_solve_time_hard": (400, 900),
        "hint_rate": (0.1, 0.4),
        "error_rate": (0.15, 0.4),
        "current_streak": (1, 10),
        "session_count": (10, 60),
        "last_played_difficulty": (1, 2),
        "win_rate": (0.5, 0.75),
        "optimal_score": (1.0, 2.5),
    },
    "intermediate": {
        "avg_solve_time_easy": (30, 90),
        "avg_solve_time_medium": (90, 250),
        "avg_solve_time_hard": (250, 600),
        "hint_rate": (0.02, 0.2),
        "error_rate": (0.05, 0.25),
        "current_streak": (5, 30),
        "session_count": (40, 150),
        "last_played_difficulty": (2, 3),
        "win_rate": (0.65, 0.85),
        "optimal_score": (2.0, 3.5),
    },
    "advanced": {
        "avg_solve_time_easy": (15, 60),
        "avg_solve_time_medium": (60, 150),
        "avg_solve_time_hard": (150, 400),
        "hint_rate": (0.0, 0.1),
        "error_rate": (0.02, 0.15),
        "current_streak": (10, 60),
        "session_count": (100, 400),
        "last_played_difficulty": (3, 4),
        "win_rate": (0.75, 0.92),
        "optimal_score": (3.0, 4.5),
    },
    "expert": {
        "avg_solve_time_easy": (10, 40),
        "avg_solve_time_medium": (30, 100),
        "avg_solve_time_hard": (80, 250),
        "hint_rate": (0.0, 0.03),
        "error_rate": (0.0, 0.08),
        "current_streak": (20, 100),
        "session_count": (200, 1000),
        "last_played_difficulty": (4, 5),
        "win_rate": (0.85, 0.98),
        "optimal_score": (4.0, 5.0),
    },
}


def _sample(low: float, high: float, is_int: bool = False) -> float:
    """Sample from truncated normal in [low, high]."""
    mean = (low + high) / 2.0
    std = (high - low) / 4.0
    val = np.random.normal(mean, max(std, 0.01))
    val = np.clip(val, low, high)
    return int(round(val)) if is_int else round(float(val), 4)


def generate_user_sample(archetype: str) -> dict:
    """Generate a single user feature vector."""
    profile = PLAYER_ARCHETYPES[archetype]
    sample = {}

    sample["avg_solve_time_easy"] = _sample(*profile["avg_solve_time_easy"])
    sample["avg_solve_time_medium"] = _sample(*profile["avg_solve_time_medium"])
    sample["avg_solve_time_hard"] = _sample(*profile["avg_solve_time_hard"])
    sample["hint_rate"] = _sample(*profile["hint_rate"])
    sample["error_rate"] = _sample(*profile["error_rate"])
    sample["current_streak"] = _sample(*profile["current_streak"], is_int=True)
    sample["session_count"] = _sample(*profile["session_count"], is_int=True)
    sample["last_played_difficulty"] = _sample(*profile["last_played_difficulty"], is_int=True)
    sample["win_rate"] = _sample(*profile["win_rate"])

    # Target: optimal difficulty score (continuous 0–5)
    sample["optimal_difficulty_score"] = _sample(*profile["optimal_score"])

    return sample


def generate_user_dataset(
    n_samples: int = 5000,
    output_path: str | None = None,
    seed: int = 42,
) -> list[dict]:
    """
    Generate balanced user gameplay feature dataset.

    Args:
        n_samples: Total samples (distributed across 5 archetypes).
        output_path: CSV save path (optional).
        seed: Random seed.

    Returns:
        List of user feature dicts.
    """
    np.random.seed(seed)
    random.seed(seed)

    archetypes = list(PLAYER_ARCHETYPES.keys())
    per_archetype = n_samples // len(archetypes)
    remainder = n_samples % len(archetypes)

    dataset = []
    for i, arch in enumerate(archetypes):
        count = per_archetype + (1 if i < remainder else 0)
        for _ in range(count):
            dataset.append(generate_user_sample(arch))

    random.shuffle(dataset)

    if output_path:
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        fieldnames = FEATURE_NAMES + ["optimal_difficulty_score"]
        with open(output_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(dataset)

    return dataset


if __name__ == "__main__":
    output = "data/user_features.csv"
    data = generate_user_dataset(n_samples=5000, output_path=output)
    print(f"Generated {len(data)} user profiles → {output}")
