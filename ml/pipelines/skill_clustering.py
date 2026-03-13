"""
Airflow DAG: skill_clustering

Runs weekly (Sunday 2am UTC). Fetches skill features for every user
from PostgreSQL, calls ml-service /skill-cluster for each user, and
writes the cluster label back to users.skill_cluster.

After reassignment, publishes a summary to the analytics DuckDB store.

Schedule: 0 2 * * 0  (Sunday 2am UTC)
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import duckdb
import psycopg2
import requests
from airflow import DAG
from airflow.models import Variable
from airflow.operators.python import PythonOperator

# ─── Config ───────────────────────────────────────────────────────────────────

DEFAULT_ARGS = {
    "owner": "sudoku-ultra",
    "depends_on_past": False,
    "retries": 2,
    "retry_delay": timedelta(minutes=15),
    "email_on_failure": False,
}

BATCH_SIZE = 50

# ─── SQL ──────────────────────────────────────────────────────────────────────

SKILL_FEATURES_SQL = """
SELECT
    u.id                                                                AS user_id,
    -- avg solve time per difficulty (seconds, defaults for missing data)
    COALESCE(
        AVG(gs.time_elapsed_ms / 1000.0)
        FILTER (WHERE gs.difficulty IN ('super_easy', 'easy') AND gs.status = 'completed'),
        120
    )::float                                                            AS avg_solve_time_easy,
    COALESCE(
        AVG(gs.time_elapsed_ms / 1000.0)
        FILTER (WHERE gs.difficulty = 'medium' AND gs.status = 'completed'),
        300
    )::float                                                            AS avg_solve_time_medium,
    COALESCE(
        AVG(gs.time_elapsed_ms / 1000.0)
        FILTER (WHERE gs.difficulty IN ('hard', 'super_hard') AND gs.status = 'completed'),
        600
    )::float                                                            AS avg_solve_time_hard,
    -- hint rate: fraction of completed games using any hints
    COALESCE(
        COUNT(gs.id) FILTER (WHERE gs.hints_used > 0 AND gs.status = 'completed')::float
        / NULLIF(COUNT(gs.id) FILTER (WHERE gs.status = 'completed'), 0),
        0.2
    )::float                                                            AS hint_rate,
    -- error rate: fraction of completed games with errors
    COALESCE(
        COUNT(gs.id) FILTER (WHERE gs.errors_count > 0 AND gs.status = 'completed')::float
        / NULLIF(COUNT(gs.id) FILTER (WHERE gs.status = 'completed'), 0),
        0.15
    )::float                                                            AS error_rate,
    -- difficulty preference: modal difficulty (as int 0-5)
    COALESCE(
        CASE MODE() WITHIN GROUP (ORDER BY gs.difficulty)
            WHEN 'super_easy' THEN 0
            WHEN 'easy'       THEN 1
            WHEN 'medium'     THEN 2
            WHEN 'hard'       THEN 3
            WHEN 'super_hard' THEN 4
            WHEN 'extreme'    THEN 5
            ELSE 2
        END,
        2
    )::int                                                              AS difficulty_preference_mode,
    -- avg session length (minutes)
    COALESCE(
        AVG(gs.time_elapsed_ms / 60000.0) FILTER (WHERE gs.status = 'completed'),
        20
    )::float                                                            AS session_length_avg,
    -- days active in last 30 days
    COALESCE(
        COUNT(DISTINCT gs.started_at::date)
        FILTER (WHERE gs.started_at >= NOW() - INTERVAL '30 days'),
        0
    )::int                                                              AS days_active_last_30
FROM users u
LEFT JOIN game_sessions gs ON gs.user_id = u.id
GROUP BY u.id
"""

# ─── Tasks ────────────────────────────────────────────────────────────────────


def assign_skill_clusters(**_context) -> None:
    db_url = Variable.get("DATABASE_URL")
    ml_url = Variable.get("ML_SERVICE_URL", default_var="http://ml-service:3003")

    conn = psycopg2.connect(db_url)
    try:
        with conn.cursor() as cur:
            cur.execute(SKILL_FEATURES_SQL)
            rows = cur.fetchall()
            columns = [d[0] for d in cur.description]
            users = [dict(zip(columns, row)) for row in rows]

        print(f"[skill_clustering] Clustering {len(users)} users")
        updates: list[tuple] = []
        cluster_counts: dict[str, int] = {}

        for i in range(0, len(users), BATCH_SIZE):
            batch = users[i : i + BATCH_SIZE]
            for user in batch:
                try:
                    resp = requests.post(
                        f"{ml_url}/api/v1/skill-cluster",
                        json={
                            "user_id": user["user_id"],
                            "avg_solve_time_easy": float(user["avg_solve_time_easy"]),
                            "avg_solve_time_medium": float(user["avg_solve_time_medium"]),
                            "avg_solve_time_hard": float(user["avg_solve_time_hard"]),
                            "hint_rate": float(user["hint_rate"]),
                            "error_rate": float(user["error_rate"]),
                            "difficulty_preference_mode": int(user["difficulty_preference_mode"]),
                            "session_length_avg": float(user["session_length_avg"]),
                            "days_active_last_30": int(user["days_active_last_30"]),
                        },
                        timeout=10,
                    )
                    resp.raise_for_status()
                    result = resp.json()
                    cluster = result["cluster"]
                    updates.append((cluster, user["user_id"]))
                    cluster_counts[cluster] = cluster_counts.get(cluster, 0) + 1
                except Exception as e:
                    print(f"  [WARN] Failed to cluster user {user['user_id']}: {e}")

        # Bulk update users table
        if updates:
            with conn.cursor() as cur:
                cur.executemany(
                    """UPDATE users
                       SET skill_cluster = %s, skill_clustered_at = NOW()
                       WHERE id = %s""",
                    updates,
                )
            conn.commit()

        print(f"[skill_clustering] Done — {len(updates)} users updated")
        print(f"  Distribution: {cluster_counts}")

        # Write cluster distribution snapshot to DuckDB
        _write_cluster_snapshot(cluster_counts)

    finally:
        conn.close()


def _write_cluster_snapshot(distribution: dict[str, int]) -> None:
    """Persist cluster distribution to DuckDB for the web-admin dashboard."""
    import os

    duckdb_path = Variable.get("DUCKDB_PATH", default_var="/app/data/analytics.duckdb")
    os.makedirs(os.path.dirname(duckdb_path), exist_ok=True)

    duck = duckdb.connect(duckdb_path)
    try:
        duck.execute("""
            CREATE TABLE IF NOT EXISTS skill_cluster_snapshots (
                run_date    DATE,
                cluster     VARCHAR,
                user_count  INTEGER,
                PRIMARY KEY (run_date, cluster)
            )
        """)
        today = datetime.utcnow().date()
        for cluster, count in distribution.items():
            duck.execute("""
                INSERT OR REPLACE INTO skill_cluster_snapshots (run_date, cluster, user_count)
                VALUES (?, ?, ?)
            """, [today, cluster, count])
        duck.commit()
        print(f"[skill_clustering] Cluster snapshot written to DuckDB")
    except Exception as e:
        print(f"[skill_clustering] DuckDB write failed (non-fatal): {e}")
    finally:
        duck.close()


def validate_cluster_coverage(**_context) -> None:
    """Verify that at least 80% of users have a cluster label after reassignment."""
    db_url = Variable.get("DATABASE_URL")
    conn = psycopg2.connect(db_url)
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    COUNT(*) AS total,
                    COUNT(*) FILTER (WHERE skill_cluster IS NOT NULL) AS clustered
                FROM users
            """)
            total, clustered = cur.fetchone()

        if total == 0:
            print("[validate_cluster_coverage] No users — skipping")
            return

        coverage = clustered / total
        print(f"[validate_cluster_coverage] {clustered}/{total} users clustered ({coverage:.1%})")

        if coverage < 0.80:
            raise ValueError(
                f"Cluster coverage {coverage:.1%} is below the 80% threshold. "
                "Check ml-service availability."
            )
    finally:
        conn.close()


# ─── DAG Definition ───────────────────────────────────────────────────────────

with DAG(
    dag_id="skill_clustering",
    default_args=DEFAULT_ARGS,
    description="Weekly player skill clustering — assigns users to Beginner/Casual/Intermediate/Advanced/Expert",
    schedule_interval="0 2 * * 0",  # Sunday 2am UTC
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=["ml", "clustering", "weekly"],
) as dag:

    t_cluster = PythonOperator(
        task_id="assign_skill_clusters",
        python_callable=assign_skill_clusters,
    )

    t_validate = PythonOperator(
        task_id="validate_cluster_coverage",
        python_callable=validate_cluster_coverage,
    )

    t_cluster >> t_validate
