"""
train_rl_bot.py — RL Bot training: 3 PPO tiers for the Sudoku bot opponent.

Tiers:
  easy   — 50_000 steps   — high exploration, large action delay in game (500ms–2s)
  medium — 200_000 steps  — balanced
  hard   — 500_000 steps  — most steps, fastest game delay (100–300ms)

Usage:
  python -m app.ml.train_rl_bot --tier easy
  python -m app.ml.train_rl_bot --tier medium
  python -m app.ml.train_rl_bot --tier hard
  python -m app.ml.train_rl_bot          # trains all three sequentially

Outputs:  ml/models/rl_bot_easy.zip
          ml/models/rl_bot_medium.zip
          ml/models/rl_bot_hard.zip

MLflow run logged per tier with:
  params:  tier, total_timesteps, n_envs, puzzle_pool_size, clues
  metrics: mean_reward, win_rate, steps_to_win_mean
  artifact: trained model .zip
"""

from __future__ import annotations

import argparse
import logging
import pathlib
import time
from typing import Any

import mlflow
import numpy as np

logger = logging.getLogger(__name__)

MODELS_DIR = pathlib.Path("ml/models")
MODELS_DIR.mkdir(parents=True, exist_ok=True)

# ─── Tier Configuration ───────────────────────────────────────────────────────

TIER_CONFIG: dict[str, dict[str, Any]] = {
    "easy": {
        "total_timesteps": 50_000,
        "n_envs": 4,
        "puzzle_pool_size": 200,
        "clues": 40,        # more given cells → easier puzzles for early training
        "ent_coef": 0.05,   # higher entropy → more exploration
        "game_delay_ms": [500, 2000],
    },
    "medium": {
        "total_timesteps": 200_000,
        "n_envs": 8,
        "puzzle_pool_size": 500,
        "clues": 32,
        "ent_coef": 0.01,
        "game_delay_ms": [200, 500],
    },
    "hard": {
        "total_timesteps": 500_000,
        "n_envs": 16,
        "puzzle_pool_size": 1000,
        "clues": 25,        # harder puzzles
        "ent_coef": 0.005,
        "game_delay_ms": [100, 300],
    },
}


# ─── Training ─────────────────────────────────────────────────────────────────

def train_and_save(tier: str) -> dict[str, Any]:
    """
    Train a PPO model for the given tier, save it, register with MLflow.
    Returns a metrics dict with mean_reward, win_rate, etc.
    """
    try:
        from sb3_contrib import MaskablePPO
        from sb3_contrib.common.wrappers import ActionMasker
        from stable_baselines3.common.env_util import make_vec_env
        from stable_baselines3.common.vec_env import SubprocVecEnv
    except ImportError as e:
        raise RuntimeError(
            "stable-baselines3 and sb3-contrib are required for RL bot training. "
            "pip install stable-baselines3 sb3-contrib gymnasium"
        ) from e

    from app.ml.sudoku_env import SudokuEnv, generate_puzzle_pool

    if tier not in TIER_CONFIG:
        raise ValueError(f"Unknown tier '{tier}'. Choose from: {list(TIER_CONFIG)}")

    cfg = TIER_CONFIG[tier]
    logger.info(f"Training RL bot tier={tier!r} for {cfg['total_timesteps']:,} steps")

    # ── Generate puzzle pool ──────────────────────────────────────────────────
    pool = generate_puzzle_pool(n=cfg["puzzle_pool_size"], clues=cfg["clues"])
    logger.info(f"Puzzle pool: {len(pool)} puzzles with {cfg['clues']} clues each")

    # ── Build vectorised environment ──────────────────────────────────────────
    def make_env():
        def _mask_fn(env: SudokuEnv) -> np.ndarray:
            return env.get_action_mask()

        env = SudokuEnv(pool, max_steps=400)
        env = ActionMasker(env, _mask_fn)
        return env

    vec_env = make_vec_env(
        make_env,
        n_envs=cfg["n_envs"],
        vec_env_cls=SubprocVecEnv,
    )

    # ── Instantiate MaskablePPO ───────────────────────────────────────────────
    model = MaskablePPO(
        "MlpPolicy",
        vec_env,
        n_steps=2048,
        batch_size=512,
        n_epochs=10,
        gamma=0.99,
        gae_lambda=0.95,
        clip_range=0.2,
        ent_coef=cfg["ent_coef"],
        learning_rate=3e-4,
        verbose=0,
        device="auto",
    )

    # ── Train ─────────────────────────────────────────────────────────────────
    t0 = time.time()
    with mlflow.start_run(run_name=f"rl_bot_{tier}") as run:
        mlflow.log_params({
            "tier": tier,
            "total_timesteps": cfg["total_timesteps"],
            "n_envs": cfg["n_envs"],
            "puzzle_pool_size": cfg["puzzle_pool_size"],
            "clues": cfg["clues"],
            "ent_coef": cfg["ent_coef"],
            "algorithm": "MaskablePPO",
        })

        model.learn(total_timesteps=cfg["total_timesteps"], progress_bar=False)

        elapsed = time.time() - t0
        logger.info(f"Training complete in {elapsed:.1f}s")

        # ── Evaluate ──────────────────────────────────────────────────────────
        eval_metrics = _evaluate(model, pool, n_episodes=50)

        mlflow.log_metrics({
            "mean_reward":       eval_metrics["mean_reward"],
            "win_rate":          eval_metrics["win_rate"],
            "steps_to_win_mean": eval_metrics["steps_to_win_mean"],
            "training_seconds":  elapsed,
        })

        # ── Save model ────────────────────────────────────────────────────────
        model_path = MODELS_DIR / f"rl_bot_{tier}.zip"
        model.save(str(model_path))
        mlflow.log_artifact(str(model_path))

        logger.info(
            f"Tier={tier!r} | win_rate={eval_metrics['win_rate']:.2%} "
            f"| mean_reward={eval_metrics['mean_reward']:.2f} "
            f"| saved → {model_path}"
        )

    vec_env.close()
    return {**eval_metrics, "model_path": str(model_path), "tier": tier}


def _evaluate(model, pool: list, n_episodes: int = 50) -> dict[str, float]:
    """Evaluate the trained model on fresh episodes; return summary metrics."""
    from sb3_contrib import MaskablePPO
    from sb3_contrib.common.wrappers import ActionMasker
    from app.ml.sudoku_env import SudokuEnv

    def _mask_fn(env: SudokuEnv) -> np.ndarray:
        return env.get_action_mask()

    eval_env = ActionMasker(SudokuEnv(pool, max_steps=400), _mask_fn)

    rewards, steps_to_win = [], []
    wins = 0

    for _ in range(n_episodes):
        obs, _ = eval_env.reset()
        ep_reward = 0.0
        for step in range(400):
            action_masks = eval_env.action_masks()
            action, _ = model.predict(obs, action_masks=action_masks, deterministic=True)
            obs, reward, terminated, truncated, _ = eval_env.step(int(action))
            ep_reward += float(reward)
            if terminated:
                wins += 1
                steps_to_win.append(step + 1)
                break
            if truncated:
                break
        rewards.append(ep_reward)

    return {
        "mean_reward":       float(np.mean(rewards)),
        "win_rate":          wins / n_episodes,
        "steps_to_win_mean": float(np.mean(steps_to_win)) if steps_to_win else 0.0,
    }


# ─── CLI Entry Point ──────────────────────────────────────────────────────────

def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
    parser = argparse.ArgumentParser(description="Train RL Sudoku bot")
    parser.add_argument(
        "--tier",
        choices=["easy", "medium", "hard"],
        default=None,
        help="Bot tier to train (omit to train all three)",
    )
    args = parser.parse_args()
    tiers = [args.tier] if args.tier else ["easy", "medium", "hard"]
    for tier in tiers:
        train_and_save(tier)


if __name__ == "__main__":
    main()
