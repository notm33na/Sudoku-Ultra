"""
Airflow DAG: churn_risk_scorer

Runs nightly. For every user, computes engagement features from
PostgreSQL game data, calls ml-service /predict-churn, and inserts
high-risk users (churn_prob > 0.7) into re_engagement_queue.
The notification service polls this table and sends FCM pushes.

Schedule: 30 1 * * *  (1:30 AM UTC — after daily puzzle generation)
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

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
    "retry_delay": timedelta(minutes=10),
    "email_on_failure": False,
}

CHURN_THRESHOLD = 0.7  # Insert into re_engagement_queue above this probability
BATCH_SIZE = 50        # Users processed per API batch

# ─── SQL ──────────────────────────────────────────────────────────────────────

ENGAGEMENT_FEATURES_SQL = """
SELECT
    u.id                                                           AS user_id,
    COALESCE(
        EXTRACT(EPOCH FROM (NOW() - s.last_played_date)) / 86400, 999
    )::float                                                       AS days_since_last_play,
    COALESCE(
        COUNT(gs.id) FILTER (WHERE gs.started_at >= NOW() - INTERVAL '30 days')
        / 4.3, 0
    )::float                                                       AS session_frequency,
    COALESCE(AVG(gs.time_elapsed_ms) / 60000.0, 20)::float        AS avg_session_duration,
    COUNT(gs.id)::float                                            AS total_games_played,
    COALESCE(
        COUNT(gs.id) FILTER (
            WHERE gs.status = 'completed'
              AND gs.started_at >= NOW() - INTERVAL '14 days'
        )::float
        / NULLIF(COUNT(gs.id) FILTER (
            WHERE gs.started_at >= NOW() - INTERVAL '14 days'
        ), 0)
        -
        COUNT(gs.id) FILTER (
            WHERE gs.status = 'completed'
              AND gs.started_at BETWEEN NOW() - INTERVAL '28 days'
                                    AND NOW() - INTERVAL '14 days'
        )::float
        / NULLIF(COUNT(gs.id) FILTER (
            WHERE gs.started_at BETWEEN NOW() - INTERVAL '28 days'
                                    AND NOW() - INTERVAL '14 days'
        ), 0),
        0
    )::float                                                       AS win_rate_trend,
    0.0::float                                                     AS hint_usage_trend,
    COUNT(DISTINCT gs.difficulty)::float                           AS difficulty_variety,
    COALESCE(
        COUNT(gs.id) FILTER (WHERE gs.status = 'completed')::float
        / NULLIF(COUNT(gs.id), 0),
        0.7
    )::float                                                       AS completion_rate,
    0.0::float                                                     AS error_rate_trend,
    COALESCE(s.longest_streak, 0)::float                          AS longest_streak
FROM users u
LEFT JOIN streaks s ON s.user_id = u.id
LEFT JOIN game_sessions gs ON gs.user_id = u.id
GROUP BY u.id, s.last_played_date, s.longest_streak
"""

# ─── Tasks ────────────────────────────────────────────────────────────────────


def score_churn_risk(**_context) -> None:
    db_url = Variable.get("DATABASE_URL")
    ml_url = Variable.get("ML_SERVICE_URL", default_var="http://ml-service:3003")

    conn = psycopg2.connect(db_url)
    try:
        with conn.cursor() as cur:
            # Fetch engagement features for all users
            cur.execute(ENGAGEMENT_FEATURES_SQL)
            rows = cur.fetchall()
            columns = [desc[0] for desc in cur.description]
            users = [dict(zip(columns, row)) for row in rows]

        print(f"[churn_risk_scorer] Scoring {len(users)} users")
        high_risk_count = 0

        # Process in batches to avoid overwhelming ml-service
        for i in range(0, len(users), BATCH_SIZE):
            batch = users[i : i + BATCH_SIZE]
            entries_to_insert: list[tuple] = []

            for user in batch:
                try:
                    resp = requests.post(
                        f"{ml_url}/api/v1/predict-churn",
                        json={
                            "user_id": user["user_id"],
                            "days_since_last_play": max(0, int(user["days_since_last_play"])),
                            "session_frequency": float(user["session_frequency"]),
                            "avg_session_duration": float(user["avg_session_duration"]),
                            "total_games_played": int(user["total_games_played"]),
                            "win_rate_trend": float(user["win_rate_trend"]),
                            "hint_usage_trend": float(user["hint_usage_trend"]),
                            "difficulty_variety": int(user["difficulty_variety"]),
                            "completion_rate": float(user["completion_rate"]),
                            "error_rate_trend": float(user["error_rate_trend"]),
                            "longest_streak": int(user["longest_streak"]),
                        },
                        timeout=10,
                    )
                    resp.raise_for_status()
                    result = resp.json()

                    prob = result.get("probability", 0.0)
                    risk_level = result.get("risk_level", "low")

                    if prob >= CHURN_THRESHOLD:
                        entries_to_insert.append((
                            str(uuid.uuid4()),
                            user["user_id"],
                            float(prob),
                            risk_level,
                        ))
                        high_risk_count += 1

                except Exception as e:
                    print(f"  [WARN] Failed to score user {user['user_id']}: {e}")
                    continue

            if entries_to_insert:
                with conn.cursor() as cur:
                    # Skip users already queued and unnotified
                    cur.executemany(
                        """INSERT INTO re_engagement_queue
                               (id, user_id, churn_prob, risk_level, notified, created_at)
                           VALUES (%s, %s, %s, %s, false, NOW())
                           ON CONFLICT DO NOTHING""",
                        entries_to_insert,
                    )
                conn.commit()

        print(
            f"[churn_risk_scorer] Done — {high_risk_count} high-risk users "
            f"queued for re-engagement notifications"
        )
    finally:
        conn.close()


def cleanup_old_entries(**_context) -> None:
    """Remove notified entries older than 30 days to keep the table lean."""
    db_url = Variable.get("DATABASE_URL")
    conn = psycopg2.connect(db_url)
    try:
        with conn.cursor() as cur:
            cur.execute(
                """DELETE FROM re_engagement_queue
                   WHERE notified = true
                     AND notified_at < NOW() - INTERVAL '30 days'"""
            )
            deleted = cur.rowcount
        conn.commit()
        print(f"[cleanup_old_entries] Removed {deleted} old queue entries")
    finally:
        conn.close()


# ─── DAG Definition ───────────────────────────────────────────────────────────

with DAG(
    dag_id="churn_risk_scorer",
    default_args=DEFAULT_ARGS,
    description="Nightly churn risk scoring → re-engagement queue population",
    schedule_interval="30 1 * * *",
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=["churn", "ml", "notifications"],
) as dag:

    t_score = PythonOperator(
        task_id="score_churn_risk",
        python_callable=score_churn_risk,
    )

    t_cleanup = PythonOperator(
        task_id="cleanup_old_entries",
        python_callable=cleanup_old_entries,
    )

    t_score >> t_cleanup
