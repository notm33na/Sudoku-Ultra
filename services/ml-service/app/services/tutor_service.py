"""
Tutor service — session store + high-level operations.

Sessions are held in memory with a TTL; expired sessions are evicted lazily
on next access.  The service layer keeps the router thin.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from langchain.memory import ConversationBufferWindowMemory

from app.config import settings
from app.ml.rag_pipeline import QdrantTechniqueRetriever, build_explain_chain
from app.ml.tutor_agent import (
    TOOLS,
    build_agent_executor,
    rule_based_hint,
)


# ── Session model ─────────────────────────────────────────────────────────────

@dataclass
class TutorSession:
    session_id: str
    user_id: str
    board: list[int]
    puzzle: list[int]
    created_at: float = field(default_factory=time.monotonic)
    last_accessed: float = field(default_factory=time.monotonic)
    memory: ConversationBufferWindowMemory = field(
        default_factory=lambda: ConversationBufferWindowMemory(
            k=settings.TUTOR_MEMORY_WINDOW,
            memory_key="chat_history",
            return_messages=True,
        )
    )
    exchange_count: int = 0

    def touch(self) -> None:
        self.last_accessed = time.monotonic()

    def is_expired(self) -> bool:
        return (time.monotonic() - self.last_accessed) > settings.TUTOR_SESSION_TTL_SECS


# ── In-memory session store ───────────────────────────────────────────────────

_sessions: dict[str, TutorSession] = {}


def _evict_expired() -> None:
    expired = [sid for sid, s in _sessions.items() if s.is_expired()]
    for sid in expired:
        del _sessions[sid]


def get_or_create_session(
    user_id: str,
    board: list[int],
    puzzle: list[int],
    session_id: str | None = None,
) -> TutorSession:
    _evict_expired()
    if session_id and session_id in _sessions:
        session = _sessions[session_id]
        session.board = board  # board may have changed
        session.touch()
        return session

    new_id = session_id or str(uuid.uuid4())
    session = TutorSession(
        session_id=new_id,
        user_id=user_id,
        board=board,
        puzzle=puzzle,
    )
    _sessions[new_id] = session
    return session


def _board_context(session: TutorSession) -> str:
    return json.dumps(session.board)


# ── Core operations ───────────────────────────────────────────────────────────

def get_hint(session: TutorSession) -> dict[str, Any]:
    """
    Return the next logical hint for the current board state.

    Structured output:
        technique       str  — technique name
        explanation     str  — tutoring text
        highlight_cells list[int] — 0-based cell indices to highlight
        follow_up       str  — follow-up question
    """
    board_json = _board_context(session)

    executor = build_agent_executor(mode="quick")
    if executor is None:
        hint_text = rule_based_hint(session.board)
        session.memory.save_context(
            {"input": "Give me a hint."},
            {"output": hint_text},
        )
        session.exchange_count += 1
        session.touch()
        return {
            "technique": "Rule-based",
            "explanation": hint_text,
            "highlight_cells": [],
            "follow_up": "Does that make sense? Try applying it now.",
        }

    prompt = (
        f"The student needs a hint. Current board (81-cell JSON): {board_json}. "
        "1) Use analyze_board to find the easiest next step. "
        "2) Use search_techniques to find the matching technique. "
        "3) Explain the technique clearly in 2–3 sentences. "
        "4) End with a follow-up question."
    )

    try:
        result = executor.invoke({"input": prompt})
        output: str = result.get("output", "")
    except Exception:
        output = rule_based_hint(session.board)

    # Parse structured fields from output (best-effort)
    parsed = _parse_hint_output(output)
    session.memory.save_context({"input": "Give me a hint."}, {"output": output})
    session.exchange_count += 1
    session.touch()
    return parsed


def explain_technique(session: TutorSession, technique_name: str) -> dict[str, Any]:
    """
    Deep explanation of a named technique using the RAG explain chain.
    Uses the 'deep' LLM (HuggingFace) when available.
    """
    from app.ml.tutor_agent import get_llm

    llm = get_llm(mode="deep") or get_llm(mode="quick")

    if llm is None:
        # Fallback: retrieve from Qdrant and format statically
        retriever = QdrantTechniqueRetriever(top_k=1)
        docs = retriever.retrieve(technique_name)
        if docs:
            explanation = docs[0].page_content
            name = docs[0].metadata.get("name", technique_name)
        else:
            explanation = f"No details found for '{technique_name}'."
            name = technique_name
        session.touch()
        return {
            "technique": name,
            "explanation": explanation,
            "highlight_cells": [],
            "follow_up": "Can you identify where to apply this on your board?",
        }

    chain = build_explain_chain(llm)
    try:
        explanation = chain.invoke({"question": f"Explain the {technique_name} technique."})
    except Exception:
        explanation = f"Could not retrieve explanation for {technique_name} right now."

    session.memory.save_context(
        {"input": f"Explain {technique_name}"},
        {"output": explanation},
    )
    session.exchange_count += 1
    session.touch()
    return {
        "technique": technique_name,
        "explanation": explanation,
        "highlight_cells": [],
        "follow_up": "Can you spot where to apply this on your board?",
    }


def process_followup(session: TutorSession, message: str) -> dict[str, Any]:
    """
    Continue the tutoring conversation with a student follow-up message.
    Includes conversation history from session memory.
    """
    board_json = _board_context(session)
    history = session.memory.load_memory_variables({}).get("chat_history", [])

    executor = build_agent_executor(mode="quick")
    if executor is None:
        response = (
            "I'm not able to process your question right now. "
            "Try refreshing and I'll do my best to help!"
        )
        session.memory.save_context({"input": message}, {"output": response})
        session.touch()
        return {
            "technique": "",
            "explanation": response,
            "highlight_cells": [],
            "follow_up": "",
        }

    # Build a context-aware prompt
    history_text = "\n".join(
        f"{msg.type.upper()}: {msg.content}" for msg in history[-6:]
    ) if history else "(no prior exchanges)"

    prompt = (
        f"Conversation so far:\n{history_text}\n\n"
        f"Current board: {board_json}\n\n"
        f"Student says: {message}\n\n"
        "Respond helpfully. Use tools if you need to check the board. "
        "End with a follow-up question."
    )

    try:
        result = executor.invoke({"input": prompt})
        output: str = result.get("output", "")
    except Exception:
        output = "I couldn't process that. Could you rephrase your question?"

    session.memory.save_context({"input": message}, {"output": output})
    session.exchange_count += 1
    session.touch()
    return _parse_hint_output(output)


# ── Output parser ─────────────────────────────────────────────────────────────

def _parse_hint_output(text: str) -> dict[str, Any]:
    """
    Best-effort parse of the agent's free-text output into structured fields.
    Falls back to putting everything in 'explanation'.
    """
    lines = text.strip().splitlines()
    follow_up = ""
    # Last sentence ending with '?' is the follow-up
    for line in reversed(lines):
        if line.strip().endswith("?"):
            follow_up = line.strip()
            break

    # Try to extract technique name (first bolded phrase **...**)
    import re
    technique = ""
    m = re.search(r"\*\*(.+?)\*\*", text)
    if m:
        technique = m.group(1)

    return {
        "technique": technique,
        "explanation": text,
        "highlight_cells": [],
        "follow_up": follow_up,
    }
