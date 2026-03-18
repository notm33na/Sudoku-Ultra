"""
Puzzle embedding — converts puzzle features into a 384-dim semantic vector.

Strategy
--------
Build a natural-language description of the puzzle from its features,
then encode with all-MiniLM-L6-v2.  Using text lets the model capture
semantic relationships ("hard", "expert-level", technique names) that a
raw numeric vector would miss.

Text template
-------------
"Sudoku puzzle: difficulty=<difficulty>, clues=<n>, techniques required:
<t1>, <t2>.  Average candidates per cell: <x>.  Backtrack depth: <d>.
Constraint density: <c>.  Symmetry score: <s>."

If no technique information is supplied the description omits that clause.
"""

from __future__ import annotations

from typing import Any

from app.ml.embeddings import embed_one

# Ordered by typical appearance in solving path (easiest first)
_TECHNIQUE_ORDER = [
    "naked-singles", "hidden-singles", "naked-pairs", "hidden-pairs",
    "naked-triples", "pointing-pairs", "box-line-reduction",
    "x-wing", "swordfish", "xy-wing", "xyz-wing", "skyscraper",
    "2-string-kite", "w-wing", "jellyfish", "unique-rectangle",
    "bug-plus-1", "finned-x-wing", "aic", "forcing-chains",
]


def build_puzzle_text(
    difficulty: str,
    clue_count: int,
    techniques: list[str] | None = None,
    avg_candidate_count: float | None = None,
    backtrack_depth: int | None = None,
    constraint_density: float | None = None,
    symmetry_score: float | None = None,
    source: str = "engine",
) -> str:
    """Build a natural-language descriptor for a puzzle."""
    parts = [f"Sudoku puzzle: difficulty={difficulty}, clues={clue_count}"]

    if techniques:
        ordered = [t for t in _TECHNIQUE_ORDER if t in techniques]
        remaining = [t for t in techniques if t not in _TECHNIQUE_ORDER]
        tech_str = ", ".join(ordered + remaining)
        parts.append(f"techniques required: {tech_str}")

    stats: list[str] = []
    if avg_candidate_count is not None:
        stats.append(f"avg candidates per cell: {avg_candidate_count:.2f}")
    if backtrack_depth is not None:
        stats.append(f"backtrack depth: {backtrack_depth}")
    if constraint_density is not None:
        stats.append(f"constraint density: {constraint_density:.2f}")
    if symmetry_score is not None:
        stats.append(f"symmetry: {symmetry_score:.2f}")
    if source != "engine":
        stats.append(f"source: {source}")

    if stats:
        parts.append(". ".join(stats))

    return ". ".join(parts) + "."


def embed_puzzle(
    difficulty: str,
    clue_count: int,
    techniques: list[str] | None = None,
    avg_candidate_count: float | None = None,
    backtrack_depth: int | None = None,
    constraint_density: float | None = None,
    symmetry_score: float | None = None,
    source: str = "engine",
) -> list[float]:
    """Return 384-dim embedding for a puzzle."""
    text = build_puzzle_text(
        difficulty=difficulty,
        clue_count=clue_count,
        techniques=techniques,
        avg_candidate_count=avg_candidate_count,
        backtrack_depth=backtrack_depth,
        constraint_density=constraint_density,
        symmetry_score=symmetry_score,
        source=source,
    )
    return embed_one(text)


def embed_puzzle_from_features(features: dict[str, Any], difficulty: str, source: str = "engine") -> list[float]:
    """
    Convenience wrapper — accepts the features dict from xai.extract_features().
    """
    return embed_puzzle(
        difficulty=difficulty,
        clue_count=int(features.get("clue_count", 30)),
        avg_candidate_count=float(features.get("avg_candidate_count", 4.0)),
        backtrack_depth=int(features.get("backtrack_depth", 0)),
        constraint_density=float(features.get("constraint_density", 0.5)),
        symmetry_score=float(features.get("symmetry_score", 0.0)),
        source=source,
    )
