#!/usr/bin/env python3
"""
Batch index existing puzzles from the game-service PostgreSQL database
into the Qdrant 'puzzles' collection.

Reads puzzle rows, extracts features using the XAI module, and upserts
embeddings via the semantic search service.

Usage:
    python ml/scripts/index_puzzles.py \
        --db-url postgresql://sudoku:sudoku_dev_password@localhost:5432/sudoku_ultra \
        --qdrant-url http://localhost:6333 \
        --batch-size 50 \
        --limit 0          # 0 = all

Requirements (in addition to ml-service deps):
    psycopg2-binary
"""

import argparse
import json
import os
import sys
from pathlib import Path

# Allow running from repo root
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "services" / "ml-service"))

import psycopg2
import psycopg2.extras

from app.ml.xai import extract_features
from app.ml.puzzle_embeddings import embed_puzzle_from_features
from app.config import settings


def _cell_grid_to_flat(grid_json) -> list[int]:
    """Convert Cell[][] (JSON from DB) to flat 81-int list."""
    if isinstance(grid_json, str):
        grid = json.loads(grid_json)
    else:
        grid = grid_json
    flat = []
    for row in grid:
        for cell in row:
            if isinstance(cell, dict):
                flat.append(cell.get("value") or 0)
            else:
                flat.append(int(cell) if cell else 0)
    return flat


def run(
    db_url: str,
    qdrant_url: str,
    batch_size: int,
    limit: int,
    reset: bool,
) -> None:
    # Override Qdrant URL for this script
    os.environ["QDRANT_URL"] = qdrant_url

    from qdrant_client import QdrantClient
    from qdrant_client.http.models import VectorParams, Distance
    from app.services.semantic_search_service import (
        PUZZLE_COLLECTION, VECTOR_SIZE, index_puzzle, ensure_collections,
    )

    print(f"Connecting to DB: {db_url[:40]}...")
    conn = psycopg2.connect(db_url)
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    if reset:
        client = QdrantClient(url=qdrant_url)
        try:
            client.delete_collection(PUZZLE_COLLECTION)
            print(f"Deleted collection '{PUZZLE_COLLECTION}'")
        except Exception:
            pass

    ensure_collections()

    query = "SELECT id, grid, solution, difficulty, clue_count FROM puzzles ORDER BY created_at"
    if limit > 0:
        query += f" LIMIT {limit}"
    cur.execute(query)

    total = 0
    errors = 0
    batch = cur.fetchmany(batch_size)

    while batch:
        for row in batch:
            try:
                puzzle_id = str(row["id"])
                flat_grid = _cell_grid_to_flat(row["grid"])
                flat_solution = _cell_grid_to_flat(row["solution"])
                difficulty = row["difficulty"]
                clue_count = row["clue_count"]

                features = extract_features(flat_grid, flat_grid)

                index_puzzle(
                    puzzle_id=puzzle_id,
                    difficulty=difficulty,
                    clue_count=clue_count,
                    avg_candidate_count=features.get("avg_candidate_count"),
                    backtrack_depth=int(features.get("backtrack_depth", 0)),
                    constraint_density=features.get("constraint_density"),
                    symmetry_score=features.get("symmetry_score"),
                )
                total += 1
                if total % 100 == 0:
                    print(f"  Indexed {total} puzzles...")
            except Exception as exc:
                errors += 1
                print(f"  Error on puzzle {row.get('id')}: {exc}")

        batch = cur.fetchmany(batch_size)

    cur.close()
    conn.close()
    print(f"\nDone. Indexed {total} puzzles. Errors: {errors}.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Batch index puzzles into Qdrant")
    parser.add_argument("--db-url", default=settings.DATABASE_URL)
    parser.add_argument("--qdrant-url", default=settings.QDRANT_URL)
    parser.add_argument("--batch-size", type=int, default=50)
    parser.add_argument("--limit", type=int, default=0, help="0 = all puzzles")
    parser.add_argument("--reset", action="store_true", help="Delete and recreate collection")
    args = parser.parse_args()
    run(args.db_url, args.qdrant_url, args.batch_size, args.limit, args.reset)


if __name__ == "__main__":
    main()
