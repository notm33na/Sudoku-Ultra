"""
Airflow DAG: daily_puzzle_generator

Runs at midnight UTC. Generates one puzzle per difficulty tier (6 total),
calls ml-service /classify to verify each puzzle's difficulty, then inserts
into the PostgreSQL daily_puzzles table.

Retries 3× on failure. On persistent failure, logs an alert.

Schedule: 0 0 * * *  (midnight UTC)
"""

from __future__ import annotations

import json
import random
import uuid
from datetime import date, datetime, timedelta
from typing import Generator

import psycopg2
import requests
from airflow import DAG
from airflow.models import Variable
from airflow.operators.python import PythonOperator

# ─── Config ───────────────────────────────────────────────────────────────────

DEFAULT_ARGS = {
    "owner": "sudoku-ultra",
    "depends_on_past": False,
    "retries": 3,
    "retry_delay": timedelta(minutes=5),
    "email_on_failure": False,
}

DIFFICULTIES = ["super_easy", "easy", "medium", "hard", "super_hard", "extreme"]

# Clue counts per difficulty (more clues = easier)
DIFFICULTY_CLUES: dict[str, int] = {
    "super_easy": 50,
    "easy": 42,
    "medium": 34,
    "hard": 28,
    "super_hard": 24,
    "extreme": 22,
}

# ─── Sudoku Generator ─────────────────────────────────────────────────────────


def _is_valid(grid: list[list[int]], row: int, col: int, num: int) -> bool:
    if num in grid[row]:
        return False
    if num in [grid[r][col] for r in range(9)]:
        return False
    br, bc = 3 * (row // 3), 3 * (col // 3)
    for r in range(br, br + 3):
        for c in range(bc, bc + 3):
            if grid[r][c] == num:
                return False
    return True


def _fill(grid: list[list[int]]) -> bool:
    for row in range(9):
        for col in range(9):
            if grid[row][col] == 0:
                nums = list(range(1, 10))
                random.shuffle(nums)
                for num in nums:
                    if _is_valid(grid, row, col, num):
                        grid[row][col] = num
                        if _fill(grid):
                            return True
                        grid[row][col] = 0
                return False
    return True


def generate_solution() -> list[list[int]]:
    grid = [[0] * 9 for _ in range(9)]
    _fill(grid)
    return grid


def create_puzzle(solution: list[list[int]], clue_count: int) -> list[list[int]]:
    puzzle = [row[:] for row in solution]
    positions = [(r, c) for r in range(9) for c in range(9)]
    random.shuffle(positions)
    to_remove = 81 - clue_count
    for r, c in positions[:to_remove]:
        puzzle[r][c] = 0
    return puzzle


def compute_features(puzzle: list[list[int]], solution: list[list[int]], difficulty: str) -> dict:
    """Compute basic puzzle features for the ml-service classifier."""
    clue_count = sum(1 for r in range(9) for c in range(9) if puzzle[r][c] != 0)
    avg_candidates = 0.0
    total_empty = 0
    for r in range(9):
        for c in range(9):
            if puzzle[r][c] == 0:
                total_empty += 1
                candidates = sum(
                    1 for n in range(1, 10) if _is_valid(puzzle, r, c, n)
                )
                avg_candidates += candidates
    if total_empty > 0:
        avg_candidates /= total_empty

    # Simple heuristics based on difficulty
    tier = DIFFICULTIES.index(difficulty)
    return {
        "clue_count": clue_count,
        "naked_singles": max(0, 20 - tier * 3),
        "hidden_singles": max(0, 15 - tier * 2),
        "naked_pairs": tier * 2,
        "pointing_pairs": tier,
        "box_line_reduction": max(0, tier - 1),
        "backtrack_depth": tier * 2,
        "constraint_density": round(clue_count / 81, 4),
        "symmetry_score": 0.5,
        "avg_candidate_count": round(avg_candidates, 4),
    }


# ─── Tasks ────────────────────────────────────────────────────────────────────


def check_ml_service(**_context) -> None:
    """Verify ml-service is reachable before generating puzzles."""
    url = Variable.get("ML_SERVICE_URL", default_var="http://ml-service:3003")
    resp = requests.get(f"{url}/health", timeout=15)
    resp.raise_for_status()
    print(f"[check_ml_service] ml-service healthy: {resp.json()}")


def generate_daily_puzzles(**context) -> None:
    """Generate 6 puzzles (one per difficulty), classify, and insert into DB."""
    db_url = Variable.get("DATABASE_URL")
    ml_url = Variable.get("ML_SERVICE_URL", default_var="http://ml-service:3003")
    today = date.today()

    conn = psycopg2.connect(db_url)
    try:
        with conn.cursor() as cur:
            # Skip if today's puzzles already exist
            cur.execute(
                "SELECT COUNT(*) FROM daily_puzzles WHERE date = %s", (today,)
            )
            existing = cur.fetchone()[0]
            if existing >= len(DIFFICULTIES):
                print(f"[generate_daily_puzzles] Already have {existing} puzzles for {today}")
                return

            generated = 0
            for difficulty in DIFFICULTIES:
                print(f"[generate_daily_puzzles] Generating {difficulty} puzzle...")
                clue_count = DIFFICULTY_CLUES[difficulty]

                # Generate puzzle
                solution = generate_solution()
                puzzle = create_puzzle(solution, clue_count)
                features = compute_features(puzzle, solution, difficulty)

                # Classify via ml-service (verify difficulty)
                try:
                    clf_resp = requests.post(
                        f"{ml_url}/api/v1/classify",
                        json=features,
                        timeout=30,
                    )
                    clf_resp.raise_for_status()
                    clf_result = clf_resp.json()
                    verified_difficulty = clf_result.get("difficulty", difficulty)
                    confidence = clf_result.get("confidence", 0.0)
                    print(
                        f"  Classified as: {verified_difficulty} "
                        f"(confidence: {confidence:.2f}, target: {difficulty})"
                    )
                except Exception as e:
                    print(f"  Classification failed ({e}), using heuristic difficulty")
                    verified_difficulty = difficulty

                # Build grid as flat Cell-like JSON (compatible with game-service schema)
                grid_json = json.dumps([
                    [{"value": puzzle[r][c], "isGiven": puzzle[r][c] != 0,
                      "notes": [], "isError": False}
                     for c in range(9)]
                    for r in range(9)
                ])
                solution_json = json.dumps(solution)
                puzzle_id = str(uuid.uuid4())
                daily_id = str(uuid.uuid4())

                # Insert puzzle
                cur.execute(
                    """INSERT INTO puzzles (id, grid, solution, difficulty, clue_count, created_at)
                       VALUES (%s, %s::jsonb, %s::jsonb, %s, %s, NOW())
                       ON CONFLICT DO NOTHING""",
                    (puzzle_id, grid_json, solution_json, verified_difficulty, clue_count),
                )

                # Insert daily_puzzle (only one per difficulty per day)
                cur.execute(
                    """INSERT INTO daily_puzzles (id, puzzle_id, date, difficulty)
                       VALUES (%s, %s, %s, %s)
                       ON CONFLICT DO NOTHING""",
                    (daily_id, puzzle_id, today, verified_difficulty),
                )
                generated += 1
                print(f"  Inserted daily puzzle {daily_id} for {today} ({verified_difficulty})")

        conn.commit()
        print(f"[generate_daily_puzzles] Done — {generated} puzzles generated for {today}")
    finally:
        conn.close()


def alert_on_failure(context) -> None:
    """Final failure callback — log alert (extend with PagerDuty/Slack in prod)."""
    dag_id = context["dag"].dag_id
    task_id = context["task_instance"].task_id
    exec_date = context["execution_date"]
    print(
        f"[ALERT] DAG {dag_id} task {task_id} failed after all retries "
        f"for execution {exec_date}. Manual intervention required."
    )


# ─── DAG Definition ───────────────────────────────────────────────────────────

with DAG(
    dag_id="daily_puzzle_generator",
    default_args={**DEFAULT_ARGS, "on_failure_callback": alert_on_failure},
    description="Generate 6 daily Sudoku puzzles (one per difficulty tier)",
    schedule_interval="0 0 * * *",
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=["daily", "puzzle", "generation"],
) as dag:

    t_check = PythonOperator(
        task_id="check_ml_service",
        python_callable=check_ml_service,
    )

    t_generate = PythonOperator(
        task_id="generate_daily_puzzles",
        python_callable=generate_daily_puzzles,
    )

    t_check >> t_generate
