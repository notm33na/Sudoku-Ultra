"""
Onboarding narration service.

Generates a short, friendly LLM tip for each onboarding step.
Falls back to curated static text when LLM is unavailable.
"""

from __future__ import annotations

from app.config import settings
from app.ml.tutor_agent import get_llm, _breaker

# ── Static fallback tips (one per step, 0-indexed) ────────────────────────────

FALLBACK_TIPS: list[str] = [
    "Sudoku is all about logic — no maths required! Every puzzle has exactly one solution.",
    "The 9×9 grid is divided into nine 3×3 boxes. Rows run left-right; columns run top-bottom.",
    "Each row, column, and 3×3 box must contain every digit from 1 to 9 exactly once. That's the only rule!",
    "Tapping a cell selects it and highlights all cells in the same row, column, and box — your constraint zone.",
    "Type a digit to fill a selected cell. Made a mistake? Tap the cell again and press delete or 0.",
    "Pencil marks let you jot possible digits in a cell before committing. Tap the pencil icon to toggle the mode.",
    "Hints reveal the technique needed for your next move without giving away the answer directly.",
    "Easy puzzles need only naked singles. Expert and Extreme puzzles may require X-Wings or forcing chains.",
    "You're all set! Remember: every puzzle is solvable by pure logic. Good luck!",
]

_SYSTEM_PROMPT = (
    "You are an enthusiastic, friendly Sudoku tutor speaking to a brand-new player. "
    "Keep your tip to 1–2 sentences. Be encouraging and clear. No markdown formatting."
)


def get_narration(step_index: int, step_title: str, step_content: str) -> str:
    """
    Return a short LLM-generated tip for the given onboarding step.
    Falls back to static text when the LLM circuit breaker is open or unavailable.
    """
    if step_index < 0 or step_index >= len(FALLBACK_TIPS):
        return "Keep going — you're doing great!"

    llm = get_llm(mode="quick")
    if llm is None:
        return FALLBACK_TIPS[step_index]

    prompt = (
        f"Onboarding step {step_index + 1}: '{step_title}'.\n"
        f"Concept: {step_content}\n\n"
        "Give me one encouraging tip for a brand-new player in 1–2 sentences."
    )

    try:
        from langchain_core.messages import HumanMessage, SystemMessage
        response = llm.invoke([
            SystemMessage(content=_SYSTEM_PROMPT),
            HumanMessage(content=prompt),
        ])
        text = response.content if hasattr(response, "content") else str(response)
        return text.strip() or FALLBACK_TIPS[step_index]
    except Exception:
        _breaker.record_failure()
        return FALLBACK_TIPS[step_index]
