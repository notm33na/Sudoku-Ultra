#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────────────
# backup_postgres.sh — PostgreSQL dump to MinIO (S3-compatible)
#
# Usage:
#   ./infra/backup/backup_postgres.sh [--env <prod|staging>] [--dry-run]
#
# Env vars (set via Kubernetes secret / Vault):
#   PGHOST, PGPORT, PGUSER, PGPASSWORD, PGDATABASE
#   MINIO_ENDPOINT   — e.g. http://minio:9000
#   MINIO_ACCESS_KEY
#   MINIO_SECRET_KEY
#   MINIO_BUCKET     — default: sudoku-ultra-backups
#   BACKUP_RETENTION_DAYS — default: 30
#
# Prereqs: pg_dump, aws CLI (used for S3-compatible upload), gzip
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
log()  { echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] [backup-postgres] $*"; }
die()  { log "ERROR: $*" >&2; exit 1; }

# ── Validate required env vars ─────────────────────────────────────────────────
for var in PGHOST PGUSER PGPASSWORD PGDATABASE MINIO_ACCESS_KEY MINIO_SECRET_KEY; do
    [[ -n "${!var:-}" ]] || die "Required env var $var is not set"
done

PGPORT="${PGPORT:-5432}"
TIMESTAMP="$(date -u '+%Y%m%dT%H%M%SZ')"
DUMP_FILE="/tmp/postgres_${PGDATABASE}_${TIMESTAMP}.dump"
S3_KEY="postgres/${DEPLOY_ENV}/${TIMESTAMP}.dump.gz"

# ── Configure aws CLI for MinIO ────────────────────────────────────────────────
export AWS_ACCESS_KEY_ID="$MINIO_ACCESS_KEY"
export AWS_SECRET_ACCESS_KEY="$MINIO_SECRET_KEY"
export AWS_DEFAULT_REGION="us-east-1"
AWS_ENDPOINT_ARGS="--endpoint-url ${MINIO_ENDPOINT}"

log "Starting PostgreSQL backup: ${PGDATABASE} → s3://${MINIO_BUCKET}/${S3_KEY}"

if [[ "$DRY_RUN" == true ]]; then
    log "DRY RUN — skipping actual dump and upload"
    exit 0
fi

# ── Dump ───────────────────────────────────────────────────────────────────────
log "Running pg_dump..."
PGPASSWORD="$PGPASSWORD" pg_dump \
    --host="$PGHOST" \
    --port="$PGPORT" \
    --username="$PGUSER" \
    --dbname="$PGDATABASE" \
    --format=custom \
    --compress=0 \
    --no-password \
    --file="$DUMP_FILE"

DUMP_SIZE=$(du -sh "$DUMP_FILE" | cut -f1)
log "Dump complete: ${DUMP_FILE} (${DUMP_SIZE})"

# ── Compress ───────────────────────────────────────────────────────────────────
log "Compressing..."
gzip -f "$DUMP_FILE"
DUMP_GZ="${DUMP_FILE}.gz"
GZ_SIZE=$(du -sh "$DUMP_GZ" | cut -f1)
log "Compressed: ${GZ_SIZE}"

# ── Upload to MinIO ────────────────────────────────────────────────────────────
log "Uploading to s3://${MINIO_BUCKET}/${S3_KEY}..."
aws s3 cp "$DUMP_GZ" "s3://${MINIO_BUCKET}/${S3_KEY}" \
    $AWS_ENDPOINT_ARGS \
    --storage-class STANDARD \
    --metadata "env=${DEPLOY_ENV},db=${PGDATABASE},timestamp=${TIMESTAMP}"

# ── Prune old backups ──────────────────────────────────────────────────────────
CUTOFF="$(date -u -d "${RETENTION_DAYS} days ago" '+%Y-%m-%dT%H:%M:%SZ' 2>/dev/null \
          || date -u -v "-${RETENTION_DAYS}d" '+%Y-%m-%dT%H:%M:%SZ')"  # GNU / BSD compat

log "Pruning backups older than ${RETENTION_DAYS} days (before ${CUTOFF})..."
aws s3 ls "s3://${MINIO_BUCKET}/postgres/${DEPLOY_ENV}/" \
    $AWS_ENDPOINT_ARGS \
    | awk '{print $4}' \
    | while read -r key; do
        FILE_DATE="${key:0:8}"  # YYYYMMDD prefix
        CUTOFF_DATE="$(date -u -d "${CUTOFF}" '+%Y%m%d' 2>/dev/null \
                       || date -u -j -f '%Y-%m-%dT%H:%M:%SZ' "${CUTOFF}" '+%Y%m%d')"
        if [[ "$FILE_DATE" < "$CUTOFF_DATE" ]]; then
            log "Deleting old backup: ${key}"
            aws s3 rm "s3://${MINIO_BUCKET}/postgres/${DEPLOY_ENV}/${key}" \
                $AWS_ENDPOINT_ARGS
        fi
    done

# ── Cleanup ────────────────────────────────────────────────────────────────────
rm -f "$DUMP_GZ"
log "Backup complete: s3://${MINIO_BUCKET}/${S3_KEY}"
