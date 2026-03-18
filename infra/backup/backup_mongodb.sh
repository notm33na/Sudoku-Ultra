#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────────────
# backup_mongodb.sh — MongoDB dump to MinIO (S3-compatible)
#
# Usage:
#   ./infra/backup/backup_mongodb.sh [--env <prod|staging>] [--dry-run]
#
# Env vars (set via Kubernetes secret / Vault):
#   MONGO_URI        — full connection string (e.g. mongodb://user:pass@host:27017/db)
#   MONGO_DB         — database name to back up
#   MINIO_ENDPOINT   — e.g. http://minio:9000
#   MINIO_ACCESS_KEY
#   MINIO_SECRET_KEY
#   MINIO_BUCKET     — default: sudoku-ultra-backups
#   BACKUP_RETENTION_DAYS — default: 30
#
# Prereqs: mongodump, aws CLI, gzip, tar
# ──────────────────────────────────────────────────────────────────────────────
set -euo pipefail

# ── Defaults ──────────────────────────────────────────────────────────────────
DEPLOY_ENV="${DEPLOY_ENV:-production}"
MINIO_ENDPOINT="${MINIO_ENDPOINT:-http://minio:9000}"
MINIO_BUCKET="${MINIO_BUCKET:-sudoku-ultra-backups}"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-30}"
DRY_RUN=false

# ── Argument parsing ───────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
    case "$1" in
        --env)       DEPLOY_ENV="$2"; shift 2 ;;
        --dry-run)   DRY_RUN=true; shift ;;
        *)           echo "Unknown argument: $1" >&2; exit 1 ;;
    esac
done

# ── Helpers ────────────────────────────────────────────────────────────────────
log()  { echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] [backup-mongodb] $*"; }
die()  { log "ERROR: $*" >&2; exit 1; }

# ── Validate ───────────────────────────────────────────────────────────────────
for var in MONGO_URI MONGO_DB MINIO_ACCESS_KEY MINIO_SECRET_KEY; do
    [[ -n "${!var:-}" ]] || die "Required env var $var is not set"
done

TIMESTAMP="$(date -u '+%Y%m%dT%H%M%SZ')"
DUMP_DIR="/tmp/mongodump_${MONGO_DB}_${TIMESTAMP}"
ARCHIVE="/tmp/mongodb_${MONGO_DB}_${TIMESTAMP}.tar.gz"
S3_KEY="mongodb/${DEPLOY_ENV}/${TIMESTAMP}.tar.gz"

# ── Configure aws CLI for MinIO ────────────────────────────────────────────────
export AWS_ACCESS_KEY_ID="$MINIO_ACCESS_KEY"
export AWS_SECRET_ACCESS_KEY="$MINIO_SECRET_KEY"
export AWS_DEFAULT_REGION="us-east-1"
AWS_ENDPOINT_ARGS="--endpoint-url ${MINIO_ENDPOINT}"

log "Starting MongoDB backup: ${MONGO_DB} → s3://${MINIO_BUCKET}/${S3_KEY}"

if [[ "$DRY_RUN" == true ]]; then
    log "DRY RUN — skipping actual dump and upload"
    exit 0
fi

# ── Dump ───────────────────────────────────────────────────────────────────────
log "Running mongodump..."
mongodump \
    --uri="$MONGO_URI" \
    --db="$MONGO_DB" \
    --out="$DUMP_DIR" \
    --gzip

log "Dump complete: ${DUMP_DIR}"

# ── Archive ────────────────────────────────────────────────────────────────────
log "Archiving..."
tar -czf "$ARCHIVE" -C "$(dirname "$DUMP_DIR")" "$(basename "$DUMP_DIR")"
ARCHIVE_SIZE=$(du -sh "$ARCHIVE" | cut -f1)
log "Archive: ${ARCHIVE} (${ARCHIVE_SIZE})"

# ── Upload to MinIO ────────────────────────────────────────────────────────────
log "Uploading to s3://${MINIO_BUCKET}/${S3_KEY}..."
aws s3 cp "$ARCHIVE" "s3://${MINIO_BUCKET}/${S3_KEY}" \
    $AWS_ENDPOINT_ARGS \
    --metadata "env=${DEPLOY_ENV},db=${MONGO_DB},timestamp=${TIMESTAMP}"

# ── Prune old backups ──────────────────────────────────────────────────────────
CUTOFF="$(date -u -d "${RETENTION_DAYS} days ago" '+%Y-%m-%dT%H:%M:%SZ' 2>/dev/null \
          || date -u -v "-${RETENTION_DAYS}d" '+%Y-%m-%dT%H:%M:%SZ')"

log "Pruning backups older than ${RETENTION_DAYS} days (before ${CUTOFF})..."
aws s3 ls "s3://${MINIO_BUCKET}/mongodb/${DEPLOY_ENV}/" \
    $AWS_ENDPOINT_ARGS \
    | awk '{print $4}' \
    | while read -r key; do
        FILE_DATE="${key:0:8}"
        CUTOFF_DATE="$(date -u -d "${CUTOFF}" '+%Y%m%d' 2>/dev/null \
                       || date -u -j -f '%Y-%m-%dT%H:%M:%SZ' "${CUTOFF}" '+%Y%m%d')"
        if [[ "$FILE_DATE" < "$CUTOFF_DATE" ]]; then
            log "Deleting old backup: ${key}"
            aws s3 rm "s3://${MINIO_BUCKET}/mongodb/${DEPLOY_ENV}/${key}" \
                $AWS_ENDPOINT_ARGS
        fi
    done

# ── Cleanup ────────────────────────────────────────────────────────────────────
rm -rf "$DUMP_DIR" "$ARCHIVE"
log "Backup complete: s3://${MINIO_BUCKET}/${S3_KEY}"
