"""
upload_training_data.py — Upload training datasets to MinIO (S3-compatible).

Scans ml/data/ for CSV and Parquet files and uploads them to the
`training-data` bucket, preserving directory structure. Also uploads
any trained model artifacts from ml/models/ to the `model-exports` bucket.

Usage
-----
  # Upload all datasets (default)
  python ml/scripts/upload_training_data.py

  # Upload from a custom data directory
  python ml/scripts/upload_training_data.py --data-dir /path/to/data

  # Upload models too
  python ml/scripts/upload_training_data.py --include-models

  # Dry-run: list what would be uploaded without uploading
  python ml/scripts/upload_training_data.py --dry-run

  # Override endpoint (e.g. production MinIO or real S3)
  python ml/scripts/upload_training_data.py --endpoint https://s3.amazonaws.com

Environment variables (override defaults)
-----------------------------------------
  MINIO_ENDPOINT_URL   — default http://localhost:9000
  AWS_ACCESS_KEY_ID    — default minioadmin
  AWS_SECRET_ACCESS_KEY — default minioadmin
  TRAINING_BUCKET      — default training-data
  MODELS_BUCKET        — default model-exports
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
log = logging.getLogger("upload_training_data")

# ── Defaults ──────────────────────────────────────────────────────────────────

DEFAULT_ENDPOINT  = os.getenv("MINIO_ENDPOINT_URL",    "http://localhost:9000")
DEFAULT_KEY       = os.getenv("AWS_ACCESS_KEY_ID",      "minioadmin")
DEFAULT_SECRET    = os.getenv("AWS_SECRET_ACCESS_KEY",  "minioadmin")
TRAINING_BUCKET   = os.getenv("TRAINING_BUCKET",        "training-data")
MODELS_BUCKET     = os.getenv("MODELS_BUCKET",          "model-exports")

DATA_EXTENSIONS   = {".csv", ".parquet", ".jsonl", ".json"}
MODEL_EXTENSIONS  = {".pkl", ".pt", ".onnx", ".tflite"}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_client(endpoint: str, key: str, secret: str):
    """Return a boto3 S3 client pointed at the MinIO endpoint."""
    try:
        import boto3
    except ImportError:
        log.error("boto3 is not installed. Run: pip install boto3")
        sys.exit(1)

    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=key,
        aws_secret_access_key=secret,
        region_name="us-east-1",   # MinIO ignores region but boto3 requires it
    )


def _ensure_bucket(s3, bucket: str) -> None:
    """Create bucket if it doesn't exist."""
    try:
        s3.head_bucket(Bucket=bucket)
    except Exception:
        s3.create_bucket(Bucket=bucket)
        log.info(f"Created bucket: {bucket}")


def _upload_dir(
    s3,
    local_dir: Path,
    bucket: str,
    extensions: set[str],
    prefix: str = "",
    dry_run: bool = False,
) -> tuple[int, int]:
    """
    Recursively upload files matching `extensions` from `local_dir` to `bucket`.

    Returns (uploaded, skipped) counts.
    """
    uploaded, skipped = 0, 0

    for path in sorted(local_dir.rglob("*")):
        if path.is_dir() or path.suffix.lower() not in extensions:
            continue

        # Build S3 key preserving relative directory structure
        rel = path.relative_to(local_dir)
        key = f"{prefix}/{rel}".lstrip("/") if prefix else str(rel)
        key = key.replace("\\", "/")   # normalise on Windows

        if dry_run:
            log.info(f"  [DRY-RUN] Would upload: {path} → s3://{bucket}/{key}")
            uploaded += 1
            continue

        try:
            s3.upload_file(str(path), bucket, key)
            log.info(f"  Uploaded: {path.name} → s3://{bucket}/{key}")
            uploaded += 1
        except Exception as exc:
            log.warning(f"  Failed to upload {path}: {exc}")
            skipped += 1

    return uploaded, skipped


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Upload Sudoku Ultra training data to MinIO."
    )
    parser.add_argument(
        "--data-dir",
        default=os.getenv("DATA_DIR", "ml/data"),
        help="Directory containing training datasets (default: ml/data)",
    )
    parser.add_argument(
        "--model-dir",
        default=os.getenv("MODEL_DIR", "ml/models"),
        help="Directory containing trained model files (default: ml/models)",
    )
    parser.add_argument(
        "--endpoint",
        default=DEFAULT_ENDPOINT,
        help=f"MinIO/S3 endpoint URL (default: {DEFAULT_ENDPOINT})",
    )
    parser.add_argument(
        "--key",
        default=DEFAULT_KEY,
        help="Access key ID",
    )
    parser.add_argument(
        "--secret",
        default=DEFAULT_SECRET,
        help="Secret access key",
    )
    parser.add_argument(
        "--include-models",
        action="store_true",
        help="Also upload model artifacts from --model-dir to the model-exports bucket",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be uploaded without transferring any files",
    )
    args = parser.parse_args()

    data_dir  = Path(args.data_dir)
    model_dir = Path(args.model_dir)

    if not data_dir.exists() and not args.include_models:
        log.warning(f"Data directory not found: {data_dir} — nothing to upload")
        return 0

    s3 = _get_client(args.endpoint, args.key, args.secret)

    log.info(f"MinIO endpoint : {args.endpoint}")
    log.info(f"Training bucket: {TRAINING_BUCKET}")
    log.info(f"Models bucket  : {MODELS_BUCKET}")
    log.info(f"Dry-run        : {args.dry_run}")
    log.info("")

    total_up, total_skip = 0, 0

    # ── Training data ────────────────────────────────────────────────────────
    if data_dir.exists():
        if not args.dry_run:
            _ensure_bucket(s3, TRAINING_BUCKET)
        log.info(f"Uploading training data from {data_dir}…")
        up, skip = _upload_dir(s3, data_dir, TRAINING_BUCKET, DATA_EXTENSIONS, dry_run=args.dry_run)
        total_up += up
        total_skip += skip
        log.info(f"  Training data: {up} uploaded, {skip} failed")
    else:
        log.warning(f"Data directory not found, skipping: {data_dir}")

    log.info("")

    # ── Model artifacts ───────────────────────────────────────────────────────
    if args.include_models:
        if not model_dir.exists():
            log.warning(f"Model directory not found, skipping: {model_dir}")
        else:
            if not args.dry_run:
                _ensure_bucket(s3, MODELS_BUCKET)
            log.info(f"Uploading model artifacts from {model_dir}…")
            up, skip = _upload_dir(
                s3, model_dir, MODELS_BUCKET, MODEL_EXTENSIONS, dry_run=args.dry_run
            )
            total_up += up
            total_skip += skip
            log.info(f"  Model artifacts: {up} uploaded, {skip} failed")
        log.info("")

    log.info(f"Done — total uploaded: {total_up}, total failed: {total_skip}")
    return 0 if total_skip == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
