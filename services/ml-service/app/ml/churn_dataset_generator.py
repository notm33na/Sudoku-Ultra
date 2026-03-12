"""
Synthetic churn dataset generator for player retention prediction.

Generates user engagement profiles with behavioral features and a binary
churn label. Uses 5 player archetypes to produce realistic distributions.

Features:
  days_since_last_play, session_frequency, avg_session_duration,
  total_games_played, win_rate_trend, hint_usage_trend,
  difficulty_variety, completion_rate, error_rate_trend, longest_streak

Target: churned (0 = active, 1 = churned)
"""

import random
import csv
import os

import numpy as np


FEATURE_NAMES = [
    "days_since_last_play",
    "session_frequency",
    "avg_session_duration",
    "total_games_played",
    "win_rate_trend",
    "hint_usage_trend",
    "difficulty_variety",
    "completion_rate",
    "error_rate_trend",
    "longest_streak",
]

# Player archetypes with engagement feature ranges and churn probability
PLAYER_ARCHETYPES = {
    "loyal": {
        "days_since_last_play": (0, 3),
        "session_frequency": (4.0, 7.0),        # sessions/week
        "avg_session_duration": (15.0, 45.0),    # minutes
        "total_games_played": (200, 2000),
        "win_rate_trend": (0.0, 0.15),           # positive = improving
        "hint_usage_trend": (-0.15, 0.0),        # negative = using fewer
        "difficulty_variety": (3, 6),             # distinct difficulties played
        "completion_rate": (0.80, 0.98),
        "error_rate_trend": (-0.10, 0.0),        # negative = improving
        "longest_streak": (30, 365),
        "churn_prob": 0.05,
    },
    "declining": {
        "days_since_last_play": (7, 30),
        "session_frequency": (0.5, 2.0),
        "avg_session_duration": (5.0, 20.0),
        "total_games_played": (50, 500),
        "win_rate_trend": (-0.20, -0.02),
        "hint_usage_trend": (0.05, 0.30),
        "difficulty_variety": (1, 3),
        "completion_rate": (0.40, 0.70),
        "error_rate_trend": (0.05, 0.25),
        "longest_streak": (5, 30),
        "churn_prob": 0.75,
    },
    "sporadic": {
        "days_since_last_play": (3, 21),
        "session_frequency": (0.5, 3.0),
        "avg_session_duration": (5.0, 30.0),
        "total_games_played": (10, 200),
        "win_rate_trend": (-0.10, 0.10),
        "hint_usage_trend": (-0.05, 0.15),
        "difficulty_variety": (1, 4),
        "completion_rate": (0.50, 0.85),
        "error_rate_trend": (-0.05, 0.10),
        "longest_streak": (2, 20),
        "churn_prob": 0.45,
    },
    "new_user": {
        "days_since_last_play": (0, 7),
        "session_frequency": (2.0, 5.0),
        "avg_session_duration": (10.0, 35.0),
        "total_games_played": (1, 30),
        "win_rate_trend": (0.0, 0.25),
        "hint_usage_trend": (-0.10, 0.20),
        "difficulty_variety": (1, 3),
        "completion_rate": (0.55, 0.90),
        "error_rate_trend": (-0.15, 0.05),
        "longest_streak": (1, 14),
        "churn_prob": 0.35,
    },
    "burned_out": {
        "days_since_last_play": (14, 90),
        "session_frequency": (0.0, 0.5),
        "avg_session_duration": (2.0, 10.0),
        "total_games_played": (100, 800),
        "win_rate_trend": (-0.25, -0.05),
        "hint_usage_trend": (0.10, 0.40),
        "difficulty_variety": (1, 2),
        "completion_rate": (0.20, 0.55),
        "error_rate_trend": (0.10, 0.35),
        "longest_streak": (10, 60),
        "churn_prob": 0.90,
    },
}


def _sample(low: float, high: float, is_int: bool = False) -> float:
    """Sample from truncated normal in [low, high]."""
    mean = (low + high) / 2.0
    std = (high - low) / 4.0
    val = np.random.normal(mean, max(std, 0.01))
    val = np.clip(val, low, high)
    return int(round(val)) if is_int else round(float(val), 4)


def generate_churn_sample(archetype: str) -> dict:
    """Generate a single user engagement feature vector with churn label."""
    profile = PLAYER_ARCHETYPES[archetype]
    sample = {}

    sample["days_since_last_play"] = _sample(*profile["days_since_last_play"], is_int=True)
    sample["session_frequency"] = _sample(*profile["session_frequency"])
    sample["avg_session_duration"] = _sample(*profile["avg_session_duration"])
    sample["total_games_played"] = _sample(*profile["total_games_played"], is_int=True)
    sample["win_rate_trend"] = _sample(*profile["win_rate_trend"])
    sample["hint_usage_trend"] = _sample(*profile["hint_usage_trend"])
    sample["difficulty_variety"] = _sample(*profile["difficulty_variety"], is_int=True)
    sample["completion_rate"] = _sample(*profile["completion_rate"])
    sample["error_rate_trend"] = _sample(*profile["error_rate_trend"])
    sample["longest_streak"] = _sample(*profile["longest_streak"], is_int=True)

    # Binary churn label based on archetype probability
    sample["churned"] = int(np.random.random() < profile["churn_prob"])

    return sample


def generate_churn_dataset(
    n_samples: int = 5000,
    output_path: str | None = None,
    seed: int = 42,
) -> list[dict]:
    """
    Generate balanced churn engagement dataset.

    Args:
        n_samples: Total samples (distributed across 5 archetypes).
        output_path: CSV save path (optional).
        seed: Random seed.

    Returns:
        List of user engagement feature dicts.
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
            dataset.append(generate_churn_sample(arch))

    random.shuffle(dataset)

    if output_path:
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        fieldnames = FEATURE_NAMES + ["churned"]
        with open(output_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(dataset)

    return dataset


if __name__ == "__main__":
    output = "data/churn_features.csv"
    data = generate_churn_dataset(n_samples=5000, output_path=output)
    print(f"Generated {len(data)} engagement profiles → {output}")
    from collections import Counter
    dist = Counter(s["churned"] for s in data)
    print(f"  Churned: {dist[1]}, Active: {dist[0]}")
