"""
Synthetic skill dataset generator for player skill clustering.

Generates user skill profiles with gameplay performance features
used for K-Means clustering into 5 skill tiers.

Features:
  avg_solve_time_easy, avg_solve_time_medium, avg_solve_time_hard,
  hint_rate, error_rate, difficulty_preference_mode,
  session_length_avg, days_active_last_30
"""

import random
import csv
import os

import numpy as np

FEATURE_NAMES = [
    "avg_solve_time_easy",
    "avg_solve_time_medium",
    "avg_solve_time_hard",
    "hint_rate",
    "error_rate",
    "difficulty_preference_mode",
    "session_length_avg",
    "days_active_last_30",
]

CLUSTER_LABELS = ["Beginner", "Casual", "Intermediate", "Advanced", "Expert"]

# Skill archetypes defining feature distributions
SKILL_ARCHETYPES = {
    "beginner": {
        "avg_solve_time_easy": (150, 360),
        "avg_solve_time_medium": (400, 900),
        "avg_solve_time_hard": (800, 1800),
        "hint_rate": (0.35, 0.80),
        "error_rate": (0.30, 0.65),
        "difficulty_preference_mode": (0, 1),
        "session_length_avg": (5, 15),
        "days_active_last_30": (1, 8),
    },
    "casual": {
        "avg_solve_time_easy": (80, 200),
        "avg_solve_time_medium": (200, 450),
        "avg_solve_time_hard": (450, 900),
        "hint_rate": (0.10, 0.40),
        "error_rate": (0.15, 0.35),
        "difficulty_preference_mode": (1, 2),
        "session_length_avg": (10, 25),
        "days_active_last_30": (5, 15),
    },
    "intermediate": {
        "avg_solve_time_easy": (40, 100),
        "avg_solve_time_medium": (100, 280),
        "avg_solve_time_hard": (280, 600),
        "hint_rate": (0.03, 0.18),
        "error_rate": (0.05, 0.20),
        "difficulty_preference_mode": (2, 3),
        "session_length_avg": (15, 35),
        "days_active_last_30": (10, 22),
    },
    "advanced": {
        "avg_solve_time_easy": (20, 60),
        "avg_solve_time_medium": (60, 170),
        "avg_solve_time_hard": (170, 400),
        "hint_rate": (0.01, 0.08),
        "error_rate": (0.02, 0.12),
        "difficulty_preference_mode": (3, 4),
        "session_length_avg": (20, 45),
        "days_active_last_30": (15, 27),
    },
    "expert": {
        "avg_solve_time_easy": (10, 40),
        "avg_solve_time_medium": (30, 100),
        "avg_solve_time_hard": (80, 250),
        "hint_rate": (0.0, 0.03),
        "error_rate": (0.0, 0.06),
        "difficulty_preference_mode": (4, 5),
        "session_length_avg": (25, 60),
        "days_active_last_30": (20, 30),
    },
}


def _sample(low: float, high: float, is_int: bool = False) -> float:
    mean = (low + high) / 2.0
    std = (high - low) / 4.0
    val = np.random.normal(mean, max(std, 0.01))
    val = np.clip(val, low, high)
    return int(round(val)) if is_int else round(float(val), 4)


def generate_skill_sample(archetype: str) -> dict:
    """Generate a single user skill feature vector."""
    profile = SKILL_ARCHETYPES[archetype]
    sample = {}
    for feat in FEATURE_NAMES:
        is_int = feat in ("difficulty_preference_mode", "days_active_last_30")
        sample[feat] = _sample(*profile[feat], is_int=is_int)
    return sample


def generate_skill_dataset(
    n_samples: int = 2500,
    output_path: str | None = None,
    seed: int = 42,
) -> list[dict]:
    """Generate balanced skill feature dataset."""
    np.random.seed(seed)
    random.seed(seed)

    archetypes = list(SKILL_ARCHETYPES.keys())
    per = n_samples // len(archetypes)
    rem = n_samples % len(archetypes)

    dataset = []
    for i, arch in enumerate(archetypes):
        count = per + (1 if i < rem else 0)
        for _ in range(count):
            dataset.append(generate_skill_sample(arch))

    random.shuffle(dataset)

    if output_path:
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        with open(output_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=FEATURE_NAMES)
            writer.writeheader()
            writer.writerows(dataset)

    return dataset


if __name__ == "__main__":
    data = generate_skill_dataset(n_samples=2500, output_path="data/skill_features.csv")
    print(f"Generated {len(data)} skill profiles → data/skill_features.csv")
