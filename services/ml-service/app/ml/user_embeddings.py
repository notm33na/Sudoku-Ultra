"""
User preference embedding — aggregates session history into a 384-dim vector.

Text template
-------------
"Player profile: skill_level=<level>, preferred_difficulty=<diff>.
Solve times: easy <x>min, hard <y>min.  Hint usage rate: <r>.
Frequently encountered techniques: <t1>, <t2>.
Session count: <n>.  Improvement trend: <trend>."

The text captures playing style semantics that allow similarity search
(e.g. "find puzzles for a player like this one").
"""

from __future__ import annotations

from typing import Any

from app.ml.embeddings import embed_one

_DIFFICULTY_ORDER = ["super_easy", "easy", "medium", "hard", "super_hard", "extreme"]


def build_user_text(
    user_id: str,
    skill_level: str,
    preferred_difficulty: str,
    session_count: int,
    difficulty_distribution: dict[str, float] | None = None,
    avg_solve_times_ms: dict[str, float] | None = None,
    hint_usage_rate: float | None = None,
    top_techniques: list[str] | None = None,
    improvement_trend: str | None = None,
) -> str:
    """Build a natural-language descriptor for a user's preference profile."""
    parts = [
        f"Player profile: skill_level={skill_level}, preferred_difficulty={preferred_difficulty}",
        f"session_count={session_count}",
    ]

    if avg_solve_times_ms:
        times = []
        for diff in _DIFFICULTY_ORDER:
            if diff in avg_solve_times_ms:
                mins = avg_solve_times_ms[diff] / 60_000
                times.append(f"{diff} {mins:.1f}min")
        if times:
            parts.append("avg solve times: " + ", ".join(times))

    if hint_usage_rate is not None:
        parts.append(f"hint usage rate: {hint_usage_rate:.2f}")

    if top_techniques:
        parts.append("frequently encounters: " + ", ".join(top_techniques[:5]))

    if improvement_trend:
        parts.append(f"improvement trend: {improvement_trend}")

    if difficulty_distribution:
        dominant = max(difficulty_distribution, key=difficulty_distribution.get)  # type: ignore
        parts.append(f"most played: {dominant}")

    return ". ".join(parts) + "."


def embed_user(
    user_id: str,
    skill_level: str,
    preferred_difficulty: str,
    session_count: int,
    difficulty_distribution: dict[str, float] | None = None,
    avg_solve_times_ms: dict[str, float] | None = None,
    hint_usage_rate: float | None = None,
    top_techniques: list[str] | None = None,
    improvement_trend: str | None = None,
) -> list[float]:
    """Return 384-dim embedding for a user preference profile."""
    text = build_user_text(
        user_id=user_id,
        skill_level=skill_level,
        preferred_difficulty=preferred_difficulty,
        session_count=session_count,
        difficulty_distribution=difficulty_distribution,
        avg_solve_times_ms=avg_solve_times_ms,
        hint_usage_rate=hint_usage_rate,
        top_techniques=top_techniques,
        improvement_trend=improvement_trend,
    )
    return embed_one(text)


def aggregate_sessions(sessions: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Aggregate a list of session records into a user preference profile dict.

    Each session dict should have:
        difficulty      str
        time_elapsed_ms int
        hints_used      int
        status          str   (completed | abandoned)
        score           int
    """
    if not sessions:
        return {
            "skill_level": "beginner",
            "preferred_difficulty": "easy",
            "session_count": 0,
            "difficulty_distribution": {},
            "avg_solve_times_ms": {},
            "hint_usage_rate": 0.0,
            "top_techniques": [],
            "improvement_trend": "stable",
        }

    completed = [s for s in sessions if s.get("status") == "completed"]
    session_count = len(sessions)

    # Difficulty distribution
    diff_counts: dict[str, int] = {}
    for s in sessions:
        d = s.get("difficulty", "medium")
        diff_counts[d] = diff_counts.get(d, 0) + 1
    total = sum(diff_counts.values()) or 1
    diff_dist = {k: v / total for k, v in diff_counts.items()}

    preferred_difficulty = max(diff_counts, key=diff_counts.get) if diff_counts else "medium"

    # Average solve times per difficulty (completed only)
    time_sums: dict[str, list[int]] = {}
    for s in completed:
        d = s.get("difficulty", "medium")
        ms = s.get("time_elapsed_ms", 0)
        time_sums.setdefault(d, []).append(ms)
    avg_times = {d: sum(ts) / len(ts) for d, ts in time_sums.items()}

    # Hint usage rate
    total_hints = sum(s.get("hints_used", 0) for s in sessions)
    hint_rate = total_hints / session_count if session_count > 0 else 0.0

    # Skill level heuristic based on preferred difficulty + hint usage
    diff_rank = _DIFFICULTY_ORDER.index(preferred_difficulty) if preferred_difficulty in _DIFFICULTY_ORDER else 2
    if diff_rank <= 1 or hint_rate > 0.5:
        skill = "beginner"
    elif diff_rank <= 2:
        skill = "intermediate"
    elif diff_rank <= 3:
        skill = "advanced"
    else:
        skill = "expert"

    # Improvement trend: compare recent vs earlier solve times
    trend = "stable"
    if len(completed) >= 6:
        mid = len(completed) // 2
        recent_avg = sum(s.get("time_elapsed_ms", 0) for s in completed[mid:]) / (len(completed) - mid)
        early_avg = sum(s.get("time_elapsed_ms", 0) for s in completed[:mid]) / mid
        if early_avg > 0:
            improvement_pct = (early_avg - recent_avg) / early_avg
            if improvement_pct > 0.15:
                trend = "improving"
            elif improvement_pct < -0.15:
                trend = "declining"

    return {
        "skill_level": skill,
        "preferred_difficulty": preferred_difficulty,
        "session_count": session_count,
        "difficulty_distribution": diff_dist,
        "avg_solve_times_ms": avg_times,
        "hint_usage_rate": round(hint_rate, 3),
        "top_techniques": [],
        "improvement_trend": trend,
    }
