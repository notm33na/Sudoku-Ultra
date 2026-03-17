"""
Tutor agent: LLM factory, circuit breaker, MCP-style tools, ReAct agent.

LLM routing:
  quick (get_hint)   → ChatOllama(Mistral)
  deep (explain)     → HuggingFaceEndpoint(Mistral-7B-Instruct)
  fallback           → rule-based string response

Circuit breaker: after LLM_CIRCUIT_BREAKER_THRESHOLD consecutive failures
within LLM_CIRCUIT_BREAKER_WINDOW_SECS the breaker opens and all calls
fall through to the rule-based fallback until the window resets.
"""

from __future__ import annotations

import json
import time
from collections import deque
from typing import Any

from langchain.agents import AgentExecutor, create_react_agent
from langchain_core.prompts import PromptTemplate
from langchain_core.tools import tool

from app.config import settings
from app.ml.rag_pipeline import QdrantTechniqueRetriever

# ── Backtracking Sudoku solver (inline, no deps) ─────────────────────────────

def _solve(board: list[int]) -> list[int] | None:
    """Return a solved copy of a 81-cell board or None if unsolvable."""
    b = board[:]
    empty = [i for i, v in enumerate(b) if v == 0]

    def _candidates(idx: int) -> set[int]:
        r, c = divmod(idx, 9)
        box_r, box_c = (r // 3) * 3, (c // 3) * 3
        used: set[int] = set()
        for col in range(9):
            used.add(b[r * 9 + col])
        for row in range(9):
            used.add(b[row * 9 + c])
        for dr in range(3):
            for dc in range(3):
                used.add(b[(box_r + dr) * 9 + (box_c + dc)])
        return set(range(1, 10)) - used

    def _bt(pos: int) -> bool:
        if pos == len(empty):
            return True
        idx = empty[pos]
        for val in _candidates(idx):
            b[idx] = val
            if _bt(pos + 1):
                return True
            b[idx] = 0
        return False

    return b if _bt(0) else None


def _get_candidates(board: list[int], cell_idx: int) -> list[int]:
    r, c = divmod(cell_idx, 9)
    box_r, box_c = (r // 3) * 3, (c // 3) * 3
    used: set[int] = set()
    for col in range(9):
        used.add(board[r * 9 + col])
    for row in range(9):
        used.add(board[row * 9 + c])
    for dr in range(3):
        for dc in range(3):
            used.add(board[(box_r + dr) * 9 + (box_c + dc)])
    return sorted(set(range(1, 10)) - used)


# ── MCP-style LangChain tools ─────────────────────────────────────────────────

@tool
def solve_board(board_state_json: str) -> str:
    """
    Solve a Sudoku board.  Input: JSON array of 81 integers (0 = empty).
    Returns the completed board as a JSON array, or an error string.
    """
    try:
        board = json.loads(board_state_json)
        if len(board) != 81:
            return "Error: board must have exactly 81 cells."
        result = _solve(board)
        return json.dumps(result) if result else "No solution found."
    except Exception as exc:
        return f"Error: {exc}"


@tool
def get_candidates(board_state_json: str, cell_index: int) -> str:
    """
    Return the possible values for a single cell given the current board.
    Input: JSON array of 81 integers plus a cell_index (0–80).
    """
    try:
        board = json.loads(board_state_json)
        candidates = _get_candidates(board, cell_index)
        return json.dumps(candidates)
    except Exception as exc:
        return f"Error: {exc}"


@tool
def analyze_board(board_state_json: str) -> str:
    """
    Analyse the current Sudoku board and identify the easiest applicable
    technique.  Returns a short description of the next logical step.
    """
    try:
        board = json.loads(board_state_json)
        empties = [i for i, v in enumerate(board) if v == 0]
        if not empties:
            return "The board is already complete."

        # Check for naked singles
        for idx in empties:
            cands = _get_candidates(board, idx)
            if len(cands) == 1:
                r, c = divmod(idx, 9)
                return (
                    f"Naked Single at row {r+1}, column {c+1}: "
                    f"only candidate is {cands[0]}."
                )

        # Check for hidden singles in rows
        for row in range(9):
            for digit in range(1, 10):
                positions = [
                    row * 9 + col
                    for col in range(9)
                    if board[row * 9 + col] == 0
                    and digit in _get_candidates(board, row * 9 + col)
                ]
                if len(positions) == 1:
                    r, c = divmod(positions[0], 9)
                    return (
                        f"Hidden Single in row {r+1}: digit {digit} "
                        f"can only go in column {c+1}."
                    )

        # Check for hidden singles in columns
        for col in range(9):
            for digit in range(1, 10):
                positions = [
                    row * 9 + col
                    for row in range(9)
                    if board[row * 9 + col] == 0
                    and digit in _get_candidates(board, row * 9 + col)
                ]
                if len(positions) == 1:
                    r, c = divmod(positions[0], 9)
                    return (
                        f"Hidden Single in column {c+1}: digit {digit} "
                        f"can only go in row {r+1}."
                    )

        filled = 81 - len(empties)
        return (
            f"No trivial singles found ({filled}/81 filled). "
            "Consider looking for Naked/Hidden Pairs or a box-line reduction."
        )
    except Exception as exc:
        return f"Error: {exc}"


@tool
def search_techniques(query: str) -> str:
    """
    Semantic search over the Sudoku technique knowledge base.
    Returns the top 3 matching techniques with names and concepts.
    """
    try:
        retriever = QdrantTechniqueRetriever(top_k=3)
        docs = retriever.retrieve(query)
        if not docs:
            return "No techniques found."
        lines = []
        for doc in docs:
            name = doc.metadata.get("name", "Unknown")
            diff = doc.metadata.get("difficulty_level", "?")
            lines.append(f"- **{name}** (difficulty {diff}/5): {doc.page_content.splitlines()[1] if len(doc.page_content.splitlines()) > 1 else ''}")
        return "\n".join(lines)
    except Exception as exc:
        return f"Error: {exc}"


TOOLS = [solve_board, get_candidates, analyze_board, search_techniques]

# ── Circuit breaker ───────────────────────────────────────────────────────────

class _CircuitBreaker:
    def __init__(self, threshold: int, window_secs: int):
        self._threshold = threshold
        self._window = window_secs
        self._failures: deque[float] = deque()

    def record_failure(self) -> None:
        now = time.monotonic()
        self._failures.append(now)
        cutoff = now - self._window
        while self._failures and self._failures[0] < cutoff:
            self._failures.popleft()

    def is_open(self) -> bool:
        now = time.monotonic()
        cutoff = now - self._window
        while self._failures and self._failures[0] < cutoff:
            self._failures.popleft()
        return len(self._failures) >= self._threshold


_breaker = _CircuitBreaker(
    settings.LLM_CIRCUIT_BREAKER_THRESHOLD,
    settings.LLM_CIRCUIT_BREAKER_WINDOW_SECS,
)

# ── LLM factory ──────────────────────────────────────────────────────────────

def get_llm(mode: str = "quick") -> Any:
    """
    Return the appropriate LangChain LLM for the given mode.
    mode = "quick"  → ChatOllama (Mistral, local)
    mode = "deep"   → HuggingFaceEndpoint (Mistral-7B-Instruct)
    Falls back to None if the circuit breaker is open.
    """
    if _breaker.is_open():
        return None

    if mode == "quick":
        try:
            from langchain_community.chat_models import ChatOllama
            return ChatOllama(
                base_url=settings.OLLAMA_URL,
                model=settings.OLLAMA_MODEL,
                temperature=0.2,
                max_tokens=settings.TUTOR_MAX_TOKENS,
            )
        except Exception:
            _breaker.record_failure()
            return None

    # deep
    if not settings.HF_INFERENCE_API_KEY:
        return None
    try:
        from langchain_huggingface import HuggingFaceEndpoint
        return HuggingFaceEndpoint(
            repo_id=settings.HF_INFERENCE_MODEL,
            huggingfacehub_api_token=settings.HF_INFERENCE_API_KEY,
            max_new_tokens=settings.TUTOR_MAX_TOKENS,
            temperature=0.3,
        )
    except Exception:
        _breaker.record_failure()
        return None


# ── ReAct prompt ──────────────────────────────────────────────────────────────

_REACT_PROMPT = PromptTemplate.from_template(
    """You are an expert Sudoku tutor helping a student solve a puzzle.
Use the available tools to examine the board and retrieve relevant technique information.

Available tools:
{tools}

Tool names: {tool_names}

Use this format:
Thought: think about what to do
Action: tool_name
Action Input: tool_input
Observation: tool_result
... (repeat Thought/Action/Observation as needed)
Thought: I have enough information to answer
Final Answer: your complete tutoring response

Always end your Final Answer with a follow-up question to check understanding.

{agent_scratchpad}

Question: {input}
"""
)

# ── Agent factory ─────────────────────────────────────────────────────────────

def build_agent_executor(mode: str = "quick") -> AgentExecutor | None:
    """Return a configured AgentExecutor or None if LLM is unavailable."""
    llm = get_llm(mode)
    if llm is None:
        return None
    agent = create_react_agent(llm=llm, tools=TOOLS, prompt=_REACT_PROMPT)
    return AgentExecutor(
        agent=agent,
        tools=TOOLS,
        max_iterations=6,
        handle_parsing_errors=True,
        verbose=False,
    )


# ── Rule-based fallback ───────────────────────────────────────────────────────

def rule_based_hint(board: list[int]) -> str:
    """Deterministic hint when LLM is unavailable."""
    empties = [i for i, v in enumerate(board) if v == 0]
    if not empties:
        return "The board is complete — well done!"

    for idx in empties:
        cands = _get_candidates(board, idx)
        if len(cands) == 1:
            r, c = divmod(idx, 9)
            return (
                f"Look at row {r+1}, column {c+1}. "
                f"Only one value ({cands[0]}) can go there — that's a Naked Single."
            )

    # Find cell with fewest candidates
    best = min(empties, key=lambda i: len(_get_candidates(board, i)))
    r, c = divmod(best, 9)
    cands = _get_candidates(board, best)
    return (
        f"Focus on row {r+1}, column {c+1}. "
        f"It has only {len(cands)} candidates: {cands}. "
        "Try eliminating them using row, column, and box constraints."
    )
