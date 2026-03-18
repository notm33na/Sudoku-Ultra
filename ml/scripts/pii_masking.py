"""
pii_masking.py — PII pseudonymisation utilities for the data warehouse.

All user-identifying values (user_id, session_id, match_id) are replaced
with a deterministic SHA-256 HMAC so that:
  1. Analysts cannot reverse-engineer raw IDs from the warehouse.
  2. The same raw ID always maps to the same hash (join-safe).
  3. Knowing the hash does not reveal the original ID without the secret.

The HMAC secret is read from the environment variable PII_HMAC_SECRET.
If not set, a static dev-only secret is used (NOT safe for production).

Usage (standalone)
------------------
  python ml/scripts/pii_masking.py --ids user-uuid-1 user-uuid-2

Usage (as a module)
-------------------
  from ml.scripts.pii_masking import pseudonymise, mask_row

  safe_id = pseudonymise("raw-user-uuid")
  masked  = mask_row({"user_id": "raw-uuid", "score": 42}, pii_fields={"user_id"})
  # {"user_id": "a3f9...", "score": 42}
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import logging
import os
import sys
from typing import Any

log = logging.getLogger("pii_masking")

# ── Secret ────────────────────────────────────────────────────────────────────

_DEV_SECRET = b"sudoku-ultra-dev-pii-secret-do-not-use-in-production"


def _secret() -> bytes:
    raw = os.getenv("PII_HMAC_SECRET")
    if not raw:
        log.warning(
            "PII_HMAC_SECRET not set — using insecure dev secret. "
            "Set this environment variable in production."
        )
        return _DEV_SECRET
    return raw.encode("utf-8")


# ── Core functions ────────────────────────────────────────────────────────────

def pseudonymise(value: str) -> str:
    """
    Return a deterministic 64-char hex HMAC-SHA256 of ``value``.

    The result is consistent across processes as long as PII_HMAC_SECRET
    does not change. Collision probability is negligible for UUID inputs.
    """
    return hmac.new(_secret(), value.encode("utf-8"), hashlib.sha256).hexdigest()


def mask_row(
    row: dict[str, Any],
    pii_fields: set[str],
) -> dict[str, Any]:
    """
    Return a copy of ``row`` with all ``pii_fields`` pseudonymised.

    Non-PII fields are passed through unchanged. Fields not present in
    ``row`` are silently skipped.
    """
    out = dict(row)
    for field in pii_fields:
        if field in out and out[field] is not None:
            out[field] = pseudonymise(str(out[field]))
    return out


def mask_dataframe(df, pii_columns: list[str]):
    """
    Return a copy of a pandas/duckdb DataFrame with PII columns pseudonymised.

    Works with any object that supports column-level assignment.
    """
    df = df.copy()
    for col in pii_columns:
        if col in df.columns:
            df[col] = df[col].apply(
                lambda v: pseudonymise(str(v)) if v is not None else None
            )
    return df


# ── Validation ────────────────────────────────────────────────────────────────

# Fields that must NEVER appear in the warehouse in plaintext
WAREHOUSE_PII_FIELDS: set[str] = {
    "user_id",
    "session_id",
    "match_id",
    "winner_id",
    "loser_id",
    "email",
    "username",
    "display_name",
    "ip_address",
    "device_id",
}


def validate_no_pii(row: dict[str, Any]) -> list[str]:
    """
    Return a list of PII field names found in ``row`` (should be empty for warehouse rows).
    """
    return [f for f in WAREHOUSE_PII_FIELDS if f in row and row[f] is not None]


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Pseudonymise IDs for warehouse loading."
    )
    parser.add_argument(
        "--ids", nargs="+", required=True,
        help="Raw IDs to pseudonymise (e.g. user UUIDs)"
    )
    args = parser.parse_args()

    for raw in args.ids:
        hashed = pseudonymise(raw)
        print(f"{raw}  →  {hashed}")

    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
    sys.exit(main())
