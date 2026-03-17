"""
seed_techniques.py — Populate Qdrant with 20 Sudoku technique documents.

Usage:
    python ml/scripts/seed_techniques.py [--qdrant-url URL] [--collection NAME] [--reset]

Requires:
    pip install qdrant-client sentence-transformers
"""

from __future__ import annotations

import argparse
import logging
import sys
import uuid
from typing import Any

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("seed_techniques")

# ── Technique corpus ──────────────────────────────────────────────────────────

TECHNIQUES: list[dict[str, Any]] = [
    {
        "id": "naked_singles",
        "name": "Naked Singles",
        "origin": (
            "One of the most fundamental Sudoku techniques, Naked Singles is the "
            "starting point taught to every beginner. It follows directly from the "
            "basic rules of Sudoku and requires no advanced logic."
        ),
        "concept": (
            "A Naked Single occurs when a cell has exactly one possible candidate — "
            "all eight other digits already appear in the cell's row, column, or box. "
            "The cell's value is therefore forced."
        ),
        "method": (
            "1. For each empty cell, list all digits 1–9. "
            "2. Remove any digit that already appears in the same row. "
            "3. Remove any digit that already appears in the same column. "
            "4. Remove any digit that already appears in the same 3×3 box. "
            "5. If only one candidate remains, enter that digit."
        ),
        "visual_description": (
            "The cell's pencil-mark area shows a single digit. All surrounding "
            "cells in the row, column, and box together account for the other 8 digits."
        ),
        "difficulty_level": 1,
        "prerequisite_techniques": [],
        "tags": ["beginner", "single", "elimination"],
    },
    {
        "id": "hidden_singles",
        "name": "Hidden Singles",
        "origin": (
            "Hidden Singles extend the logic of Naked Singles from cell-level analysis "
            "to group-level analysis. The technique was formalized as puzzles became "
            "harder and naked singles alone were insufficient."
        ),
        "concept": (
            "A Hidden Single occurs when a particular digit can only be placed in one "
            "cell within a row, column, or box — even though that cell has multiple "
            "candidates. The digit is 'hidden' among other candidates."
        ),
        "method": (
            "1. Pick a row, column, or box. "
            "2. For each digit 1–9, mark every empty cell in that group where the digit "
            "   is a valid candidate. "
            "3. If a digit appears as a candidate in exactly one cell of the group, "
            "   that cell must contain that digit. "
            "4. Place the digit and remove it as a candidate from the cell's peers."
        ),
        "visual_description": (
            "Scanning a row: digit 7 appears as a candidate in only one cell because "
            "the other empty cells are blocked by 7s in their respective columns or boxes."
        ),
        "difficulty_level": 1,
        "prerequisite_techniques": ["naked_singles"],
        "tags": ["beginner", "single", "scanning"],
    },
    {
        "id": "naked_pairs",
        "name": "Naked Pairs",
        "origin": (
            "Naked Pairs are a natural extension of Naked Singles. They appear in "
            "intermediate puzzles and are the foundation for understanding locked "
            "candidate patterns."
        ),
        "concept": (
            "Two cells in the same row, column, or box that both contain exactly the "
            "same two candidates form a Naked Pair. Those two digits must go in those "
            "two cells (in some order), so they can be safely eliminated from all other "
            "cells in the group."
        ),
        "method": (
            "1. Scan for cells that have exactly two candidates. "
            "2. Check if two such cells in the same group share the identical pair. "
            "3. If found, eliminate both pair digits from every other cell in that group. "
            "4. Update candidate lists accordingly."
        ),
        "visual_description": (
            "Two cells in a row each show pencil-marks {3,7}. Since 3 and 7 must fill "
            "those two cells, remove 3 and 7 from all other cells in the row."
        ),
        "difficulty_level": 2,
        "prerequisite_techniques": ["naked_singles", "hidden_singles"],
        "tags": ["intermediate", "pairs", "elimination"],
    },
    {
        "id": "hidden_pairs",
        "name": "Hidden Pairs",
        "origin": (
            "Hidden Pairs are the dual of Naked Pairs and are slightly harder to spot "
            "because the pair digits are obscured by extra candidates."
        ),
        "concept": (
            "Two digits that appear as candidates in exactly two cells of a row, column, "
            "or box form a Hidden Pair. Those two cells must contain those two digits, "
            "so all other candidates in those cells can be removed."
        ),
        "method": (
            "1. For each group, count how many cells each digit appears in as a candidate. "
            "2. Find two digits that each appear in exactly the same two cells. "
            "3. Those two cells form a Hidden Pair — remove all other candidates from them. "
            "4. This may expose further Naked Singles or Pairs."
        ),
        "visual_description": (
            "In a column, digits 4 and 9 are candidates in only cells R2 and R7. "
            "Even though those cells have other candidates, strip them — only {4,9} remains."
        ),
        "difficulty_level": 2,
        "prerequisite_techniques": ["naked_pairs"],
        "tags": ["intermediate", "pairs", "hidden"],
    },
    {
        "id": "naked_triples",
        "name": "Naked Triples",
        "origin": (
            "Naked Triples extend the Naked Pairs technique to three cells and are "
            "required when pairs alone leave the puzzle unsolved."
        ),
        "concept": (
            "Three cells in the same group collectively contain only three candidate "
            "digits (each cell has 2 or 3 of those same 3 digits). Those three digits "
            "must fill those three cells, eliminating them from the rest of the group."
        ),
        "method": (
            "1. Look for three cells in a group whose combined candidates use at most "
            "   three distinct digits. "
            "2. Verify: no cell in the triple has a candidate outside those three digits. "
            "3. Eliminate those three digits from all other cells in the group."
        ),
        "visual_description": (
            "Three cells in a box show {1,2}, {2,3}, {1,3}. Combined: digits 1,2,3. "
            "Remove 1, 2, and 3 from the other six cells in the box."
        ),
        "difficulty_level": 3,
        "prerequisite_techniques": ["naked_pairs"],
        "tags": ["intermediate", "triples", "elimination"],
    },
    {
        "id": "pointing_pairs",
        "name": "Pointing Pairs",
        "origin": (
            "Pointing Pairs, also called Locked Candidates Type 1, are a key bridge "
            "between beginner and intermediate techniques. They use the intersection "
            "of box constraints with row/column constraints."
        ),
        "concept": (
            "When a candidate digit in a box is restricted to a single row or column "
            "within that box, the digit must appear somewhere in that row/column inside "
            "the box. It can therefore be eliminated from the rest of that row/column "
            "outside the box."
        ),
        "method": (
            "1. For each box, find a digit whose remaining candidates all lie in a "
            "   single row or column. "
            "2. That digit is 'pointing' along that row or column. "
            "3. Eliminate it from all cells in that row or column outside the box."
        ),
        "visual_description": (
            "In box 1, digit 5 can only go in row 2 (two cells). Those two cells "
            "'point' rightward — remove 5 from all other cells in row 2."
        ),
        "difficulty_level": 2,
        "prerequisite_techniques": ["naked_singles", "hidden_singles"],
        "tags": ["intermediate", "locked-candidates", "box-line"],
    },
    {
        "id": "box_line_reduction",
        "name": "Box-Line Reduction",
        "origin": (
            "Box-Line Reduction, also called Locked Candidates Type 2, is the "
            "complement of Pointing Pairs — the logic runs in the opposite direction."
        ),
        "concept": (
            "When a candidate digit within a row or column is restricted to a single "
            "box, the digit must appear in that box's segment of the row/column. It can "
            "therefore be eliminated from the rest of that box."
        ),
        "method": (
            "1. For each row or column, find a digit whose remaining candidates all fall "
            "   within a single box. "
            "2. Eliminate that digit from all other cells in that box that lie outside "
            "   the current row or column."
        ),
        "visual_description": (
            "In row 4, digit 8 can only go in box 5 (two cells). Remove 8 from the "
            "other cells in box 5 that are not in row 4."
        ),
        "difficulty_level": 2,
        "prerequisite_techniques": ["pointing_pairs"],
        "tags": ["intermediate", "locked-candidates", "box-line"],
    },
    {
        "id": "x_wing",
        "name": "X-Wing",
        "origin": (
            "X-Wing is often considered the entry point into advanced Sudoku techniques. "
            "The name comes from the X shape formed by the four corner cells. It was "
            "popularized in the early 2000s as puzzle difficulty increased."
        ),
        "concept": (
            "When a candidate digit appears in exactly two cells in each of two rows, "
            "AND those cells are in the same two columns, the digit must occupy the "
            "cells at diagonally opposite corners. It can be eliminated from all other "
            "cells in both columns."
        ),
        "method": (
            "1. Find a digit that appears as a candidate in exactly 2 cells in row A. "
            "2. Find another row B where the same digit also appears in exactly 2 cells "
            "   in the same columns as row A. "
            "3. The four cells form an X. Eliminate that digit from all other cells "
            "   in the two columns."
        ),
        "visual_description": (
            "Rows 2 and 7 both have digit 4 as a candidate in only columns 3 and 8. "
            "Draw an X connecting these four cells. Remove 4 from columns 3 and 8 elsewhere."
        ),
        "difficulty_level": 3,
        "prerequisite_techniques": ["naked_pairs"],
        "tags": ["advanced", "fish", "columns", "rows"],
    },
    {
        "id": "swordfish",
        "name": "Swordfish",
        "origin": (
            "Swordfish extends X-Wing from a 2×2 grid pattern to a 3×3 pattern. "
            "It is named for its resemblance to the three-pointed swordfish shape "
            "when drawn on the grid."
        ),
        "concept": (
            "When a candidate digit appears in at most 2–3 cells in each of three rows, "
            "and all those cells fall within the same three columns, the digit must occupy "
            "the pattern and can be eliminated from all other cells in those three columns."
        ),
        "method": (
            "1. Find a digit restricted to 2–3 cells in row A, row B, and row C. "
            "2. The candidate cells collectively span exactly 3 columns. "
            "3. Eliminate the digit from all other cells in those 3 columns."
        ),
        "visual_description": (
            "Three rows have digit 6 in 2–3 cells each. Mark all candidate cells — they "
            "fall in columns 1, 5, and 9 only. Eliminate 6 from rest of those 3 columns."
        ),
        "difficulty_level": 4,
        "prerequisite_techniques": ["x_wing"],
        "tags": ["advanced", "fish", "3x3"],
    },
    {
        "id": "xy_wing",
        "name": "XY-Wing",
        "origin": (
            "XY-Wing, introduced in the late 1990s, is one of the most elegant advanced "
            "techniques. It uses a three-cell chain to produce an elimination through "
            "a chain of forced implications."
        ),
        "concept": (
            "Three bivalue cells: a pivot {AB} and two wings {AC} and {BC}, where "
            "the pivot sees both wings. If the pivot is A, wing 1 must be C; if the "
            "pivot is B, wing 2 must be C. Either way, C is placed in one wing. "
            "Any cell that sees both wings cannot be C."
        ),
        "method": (
            "1. Find a bivalue cell (pivot) with candidates {A,B}. "
            "2. Find a peer of the pivot (wing 1) with candidates {A,C}. "
            "3. Find another peer of the pivot (wing 2) with candidates {B,C}. "
            "4. Eliminate C from any cell that sees both wing 1 and wing 2."
        ),
        "visual_description": (
            "Pivot at R4C5 = {2,7}. Wing1 at R4C9 = {2,3}. Wing2 at R1C5 = {7,3}. "
            "Digit 3 eliminated from R1C9 which sees both wings."
        ),
        "difficulty_level": 3,
        "prerequisite_techniques": ["naked_pairs"],
        "tags": ["advanced", "wing", "chain"],
    },
    {
        "id": "xyz_wing",
        "name": "XYZ-Wing",
        "origin": (
            "XYZ-Wing extends XY-Wing by allowing the pivot to hold three candidates "
            "instead of two, increasing the pattern's power at the cost of complexity."
        ),
        "concept": (
            "A trivalue pivot {ABC} with two wings: {AB} and {AC}. The eliminating "
            "digit is C. Any cell that can see the pivot AND both wings cannot be C, "
            "because C must appear in one of the three cells."
        ),
        "method": (
            "1. Find a trivalue cell (pivot) {A,B,C}. "
            "2. Find a peer wing 1 = {A,C}. "
            "3. Find another peer wing 2 = {B,C}. "
            "4. Eliminate C from cells that see all three of pivot, wing1, wing2."
        ),
        "visual_description": (
            "Since the pivot itself contains C, eliminations are only valid from cells "
            "that see all three cells — typically only cells in the pivot's box."
        ),
        "difficulty_level": 4,
        "prerequisite_techniques": ["xy_wing"],
        "tags": ["advanced", "wing", "chain"],
    },
    {
        "id": "skyscraper",
        "name": "Skyscraper",
        "origin": (
            "The Skyscraper is a single-digit technique related to X-Wing. It is "
            "simpler than chains but more powerful than fish, filling an important "
            "gap in the technique hierarchy."
        ),
        "concept": (
            "A digit appears in exactly 2 cells in two different rows, forming two "
            "conjugate pairs. One pair shares a column (the 'base'), creating an "
            "asymmetric X-Wing variant. The cell at the top of each 'tower' cannot "
            "be the digit if it sees both towers."
        ),
        "method": (
            "1. Find a digit with exactly 2 candidates in row A (columns C1 and C2). "
            "2. Find a digit with exactly 2 candidates in row B (columns C1 and C3). "
            "3. C1 is the shared column — the 'base'. "
            "4. Eliminate the digit from any cell that sees both R_A_C2 and R_B_C3 "
            "   (the tops of the two towers)."
        ),
        "visual_description": (
            "Two rows each with 2 candidate cells, sharing one column. The unshared "
            "cells (the tops) stand like two skyscrapers — anything that sees both tops "
            "is eliminated."
        ),
        "difficulty_level": 3,
        "prerequisite_techniques": ["x_wing"],
        "tags": ["advanced", "single-digit", "column-row"],
    },
    {
        "id": "two_string_kite",
        "name": "2-String Kite",
        "origin": (
            "The 2-String Kite is another single-digit technique, similar to the "
            "Skyscraper but using a row conjugate pair and a column conjugate pair "
            "that meet in a shared box."
        ),
        "concept": (
            "A digit has exactly 2 candidates in a row and 2 candidates in a column. "
            "They share a common box. The string connects: row end → box intersection "
            "→ column end → elimination. Any cell seeing both non-intersecting ends "
            "cannot be the digit."
        ),
        "method": (
            "1. Find a digit with exactly 2 candidates in a row — call them R1 and R2. "
            "2. Find the same digit with exactly 2 candidates in a column — call them C1 and C2. "
            "3. One of {R1,R2} and one of {C1,C2} share a box. "
            "4. The other two endpoints form the kite tips. Eliminate from cells seeing both tips."
        ),
        "visual_description": (
            "A kite shape: one string along a row, another along a column, joined in a box. "
            "The two free ends fly out — cells seeing both free ends cannot hold the digit."
        ),
        "difficulty_level": 3,
        "prerequisite_techniques": ["x_wing"],
        "tags": ["advanced", "single-digit", "kite"],
    },
    {
        "id": "w_wing",
        "name": "W-Wing",
        "origin": (
            "The W-Wing is a two-digit technique that uses a strong link as a bridge "
            "between two bivalue cells. It is named for its W-shaped logical structure."
        ),
        "concept": (
            "Two cells with the same two candidates {A,B} are connected by a strong "
            "link on digit A (meaning A appears in exactly two cells in some group "
            "connecting them). Because A must be placed in one of those two bridge cells, "
            "B must be in the other. Cells seeing both {A,B} cells cannot be B."
        ),
        "method": (
            "1. Find two bivalue cells P1 and P2 both containing {A,B}. "
            "2. Find a strong link on A: a row/column/box where A appears only in the "
            "   two cells connecting P1 and P2. "
            "3. Eliminate B from cells that can see both P1 and P2."
        ),
        "visual_description": (
            "P1={3,7} and P2={3,7}. A strong link on 3 bridges them. Digit 7 can be "
            "eliminated from cells in the intersection zone of P1 and P2's peer sets."
        ),
        "difficulty_level": 4,
        "prerequisite_techniques": ["xy_wing"],
        "tags": ["advanced", "wing", "strong-link"],
    },
    {
        "id": "jellyfish",
        "name": "Jellyfish",
        "origin": (
            "Jellyfish is the 4×4 generalization of the fish family (X-Wing=2×2, "
            "Swordfish=3×3, Jellyfish=4×4). It rarely appears in published puzzles "
            "but is important for completeness and solver implementations."
        ),
        "concept": (
            "A digit appears in at most 4 cells in each of 4 rows, and all those cells "
            "fall within 4 columns. The digit must occupy the 4×4 grid pattern and can "
            "be eliminated from all other cells in those 4 columns."
        ),
        "method": (
            "1. Find a digit restricted to ≤4 cells in each of 4 rows, "
            "   with all candidates within the same 4 columns. "
            "2. Eliminate the digit from all other cells in those 4 columns."
        ),
        "visual_description": (
            "Four rows each contribute 2–4 candidate cells to a 4-column grid. "
            "The Jellyfish body covers these 16 positions — eliminations clear "
            "everything outside the body in those columns."
        ),
        "difficulty_level": 4,
        "prerequisite_techniques": ["swordfish"],
        "tags": ["advanced", "fish", "4x4"],
    },
    {
        "id": "unique_rectangle",
        "name": "Unique Rectangle",
        "origin": (
            "The Unique Rectangle technique leverages a constraint specific to "
            "competition-style Sudoku: every valid puzzle must have exactly one "
            "solution. This non-deductive constraint becomes a powerful tool."
        ),
        "concept": (
            "Four cells forming a rectangle spanning exactly 2 boxes, where each cell "
            "can contain the same two digits {A,B}, would create two solutions (the "
            "digits can swap). Since a valid puzzle has one solution, the pattern is "
            "avoided — this gives eliminations in the extra candidate cells."
        ),
        "method": (
            "1. Find four cells in a 2×2 rectangle (two rows, two columns, two boxes). "
            "2. Two cells (the floor) already contain only {A,B}. "
            "3. The other two (the roof) have {A,B} plus extra candidates. "
            "4. Eliminate A and B from the roof cells' extra candidates as appropriate "
            "   to prevent a deadly pattern (the specific elimination depends on UR type)."
        ),
        "visual_description": (
            "Four corners of a rectangle: R2C3, R2C7, R6C3, R6C7. Two corners have "
            "only {4,6}. The uniqueness constraint prevents the deadly swap — use this "
            "to eliminate 4 or 6 from the other corners."
        ),
        "difficulty_level": 3,
        "prerequisite_techniques": ["naked_pairs"],
        "tags": ["advanced", "uniqueness", "rectangle"],
    },
    {
        "id": "bug_plus_1",
        "name": "BUG+1",
        "origin": (
            "BUG stands for Bivalue Universal Grave. The technique uses the uniqueness "
            "constraint to resolve a near-complete state where almost every cell is bivalue."
        ),
        "concept": (
            "If all unsolved cells were bivalue except one (the BUG+1 cell which has "
            "three candidates), the puzzle would have multiple solutions unless the "
            "extra digit in the trivalue cell is placed there. The extra digit that "
            "appears three times (instead of twice) in a group is the forced value."
        ),
        "method": (
            "1. Verify all unsolved cells are bivalue except exactly one cell with three candidates. "
            "2. For the trivalue cell, identify the extra digit: the one that would "
            "   make its group's digit count odd (appearing 3× instead of 2×). "
            "3. Place that extra digit in the trivalue cell."
        ),
        "visual_description": (
            "Near-end-game: all cells show two pencil-marks except one cell showing three. "
            "Count occurrences of each candidate in each group — the odd-count digit "
            "must go in the trivalue cell."
        ),
        "difficulty_level": 4,
        "prerequisite_techniques": ["unique_rectangle"],
        "tags": ["advanced", "uniqueness", "endgame"],
    },
    {
        "id": "finned_x_wing",
        "name": "Finned X-Wing",
        "origin": (
            "Finned Fish extend the basic fish patterns (X-Wing, Swordfish, Jellyfish) "
            "by allowing extra 'fin' cells in one of the base rows. The fin restricts "
            "eliminations to cells that also see the fin."
        ),
        "concept": (
            "An X-Wing pattern where one row has extra candidate cells (fins) beyond "
            "the two base columns. The fin cells are in the same box as one of the "
            "X-Wing corners. Eliminations are only valid for cells that see both the "
            "normal X-Wing elimination zone AND the fin cells."
        ),
        "method": (
            "1. Identify an X-Wing where one row has extra candidates beyond columns C1, C2. "
            "2. The extra cells (fins) must all be in the same box as one X-Wing corner. "
            "3. Eliminate the digit only from cells in that box's column intersection "
            "   that also see the fin cells."
        ),
        "visual_description": (
            "Normal X-Wing in rows 3 and 7, columns 2 and 8. Row 3 has an extra "
            "candidate in column 4 (fin) — it shares box 2 with R3C2. Eliminate "
            "the digit only from R7C2's box peers that also see the fin."
        ),
        "difficulty_level": 4,
        "prerequisite_techniques": ["x_wing"],
        "tags": ["advanced", "fish", "finned"],
    },
    {
        "id": "aic",
        "name": "AIC (Alternating Inference Chain)",
        "origin": (
            "Alternating Inference Chains unify many advanced techniques (X-Wing, "
            "Skyscraper, XY-Wing) under a single chain framework developed by "
            "Sudoku researchers in the 2000s."
        ),
        "concept": (
            "A chain alternating between strong links (exactly one end is true) and "
            "weak links (at most one end is true). If both ends of the chain are the "
            "same candidate, it creates a continuous loop or a discontinuous chain "
            "that eliminates cells seeing both chain ends."
        ),
        "method": (
            "1. Build a chain: start from a candidate, follow strong links (grouped "
            "   pairs where one must be true) alternating with weak links. "
            "2. A discontinuous AIC: chain ends at the same candidate in different "
            "   cells → eliminate from cells seeing both ends. "
            "3. A continuous AIC (loop): each strong link becomes a locked set, "
            "   yielding multiple eliminations around the loop."
        ),
        "visual_description": (
            "Chain: [R1C1=5] -strong- [R1C9=5] -weak- [R1C9=3] -strong- [R7C9=3] "
            "-weak- [R7C9=5] -strong- [R7C1=5]. Both ends are 5 seeing R1C1 and R7C1 "
            "— eliminate 5 from cells seeing both."
        ),
        "difficulty_level": 5,
        "prerequisite_techniques": ["xy_wing", "skyscraper"],
        "tags": ["expert", "chain", "strong-link", "weak-link"],
    },
    {
        "id": "forcing_chains",
        "name": "Forcing Chains",
        "origin": (
            "Forcing Chains, also called bifurcation in computer science, are a "
            "brute-force-adjacent technique that tests assumptions and follows their "
            "consequences. Purists debate whether they constitute 'real' logic, but "
            "they reliably solve any uniquely-determined puzzle."
        ),
        "concept": (
            "Assume a candidate A is true (or false) in a cell. Follow the chain of "
            "forced consequences through the puzzle. If both branches (A=true and A=false) "
            "lead to the same conclusion for another cell B, then that conclusion holds "
            "regardless of A's value."
        ),
        "method": (
            "1. Pick a candidate digit in a bivalue cell. "
            "2. Branch 1: assume the digit IS in that cell — propagate consequences. "
            "3. Branch 2: assume the digit is NOT in that cell — propagate consequences. "
            "4. Any cell that reaches the same state in both branches can be resolved. "
            "5. If a branch leads to a contradiction, the other branch is the solution."
        ),
        "visual_description": (
            "A decision tree: root is an assumption, branches are forced by naked singles "
            "and hidden singles. Where both branches agree on a cell value, that value "
            "is certain. Contradictions eliminate the assumption."
        ),
        "difficulty_level": 5,
        "prerequisite_techniques": ["aic"],
        "tags": ["expert", "chain", "bifurcation", "contradiction"],
    },
]

# ── Seeder ────────────────────────────────────────────────────────────────────


def build_embedding_text(doc: dict[str, Any]) -> str:
    """Combine fields into a single string optimised for embedding."""
    return (
        f"{doc['name']}. "
        f"{doc['concept']} "
        f"Method: {doc['method']} "
        f"Tags: {' '.join(doc['tags'])}."
    )


def seed(qdrant_url: str, collection: str, reset: bool) -> None:
    try:
        from qdrant_client import QdrantClient
        from qdrant_client.models import Distance, VectorParams, PointStruct
        from sentence_transformers import SentenceTransformer
    except ImportError as e:
        logger.error("Missing dependency: %s — run: pip install qdrant-client sentence-transformers", e)
        sys.exit(1)

    logger.info("Connecting to Qdrant at %s", qdrant_url)
    client = QdrantClient(url=qdrant_url, timeout=30)

    # Optionally drop and recreate
    existing = {c.name for c in client.get_collections().collections}
    if reset and collection in existing:
        logger.info("Dropping existing collection '%s'", collection)
        client.delete_collection(collection)
        existing.discard(collection)

    if collection not in existing:
        logger.info("Creating collection '%s' (dim=384, cosine)", collection)
        client.create_collection(
            collection_name=collection,
            vectors_config=VectorParams(size=384, distance=Distance.COSINE),
        )

    # Load embedding model
    logger.info("Loading sentence-transformers model all-MiniLM-L6-v2 …")
    model = SentenceTransformer("all-MiniLM-L6-v2")

    # Build texts and embed
    texts = [build_embedding_text(doc) for doc in TECHNIQUES]
    logger.info("Embedding %d technique documents …", len(texts))
    vectors = model.encode(texts, normalize_embeddings=True, show_progress_bar=True)

    # Build points — use deterministic UUIDs from technique id
    points = []
    for idx, (doc, vector) in enumerate(zip(TECHNIQUES, vectors)):
        payload = {k: v for k, v in doc.items()}
        payload["embedding_text"] = texts[idx]
        points.append(
            PointStruct(
                id=str(uuid.uuid5(uuid.NAMESPACE_DNS, f"sudoku-technique.{doc['id']}")),
                vector=vector.tolist(),
                payload=payload,
            )
        )

    client.upsert(collection_name=collection, points=points, wait=True)
    logger.info("Upserted %d points into '%s'.", len(points), collection)

    # Verify
    count = client.count(collection_name=collection).count
    logger.info("Collection '%s' now contains %d documents.", collection, count)


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed Qdrant with Sudoku technique documents.")
    parser.add_argument("--qdrant-url", default="http://localhost:6333")
    parser.add_argument("--collection", default="techniques")
    parser.add_argument("--reset", action="store_true", help="Drop collection before seeding")
    args = parser.parse_args()
    seed(args.qdrant_url, args.collection, args.reset)
