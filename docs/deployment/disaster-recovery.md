# Disaster Recovery — Sudoku Ultra

> **RTO target:** 4 hours (production) / 1 hour (staging)
> **RPO target:** 24 hours (daily backups) / 1 hour (with WAL streaming, future)
> **Last reviewed:** 2026-03-19

---

## Table of Contents

1. [Backup Overview](#1-backup-overview)
2. [Restore PostgreSQL](#2-restore-postgresql)
3. [Restore MongoDB](#3-restore-mongodb)
4. [Restore Kubernetes Cluster State](#4-restore-kubernetes-cluster-state)
5. [Restore MinIO / ML Artifacts](#5-restore-minio--ml-artifacts)
6. [Full Environment Rebuild](#6-full-environment-rebuild)
7. [Runbooks by Failure Scenario](#7-runbooks-by-failure-scenario)
8. [Testing the DR Plan](#8-testing-the-dr-plan)
9. [Contact & Escalation](#9-contact--escalation)

---

## 1. Backup Overview

| Asset | Tool | Destination | Schedule | Retention |
|---|---|---|---|---|
| PostgreSQL (`sudoku_ultra`) | `pg_dump` (custom format) | MinIO `sudoku-ultra-backups/postgres/` | 02:00 UTC daily | 30 days |
| MongoDB (`sudoku_events`) | `mongodump` + tar.gz | MinIO `sudoku-ultra-backups/mongodb/` | 02:00 UTC daily | 30 days |
| ML models & artifacts | MLflow → MinIO `mlflow-artifacts/` | MinIO (same cluster) | On every training run | 90 days |
| Helm values overrides | Git (`main` branch) | GitHub | On every commit | Indefinite |
| ArgoCD application CRDs | Git (`infra/argocd/`) | GitHub | On every commit | Indefinite |

Backups are executed by the `backup_dag` Airflow DAG (`ml/pipelines/backup_dag.py`).
Scripts: `infra/backup/backup_postgres.sh`, `infra/backup/backup_mongodb.sh`.

### Verify last backup

```bash
# List today's PostgreSQL backups in MinIO
aws s3 ls s3://sudoku-ultra-backups/postgres/production/ \
  --endpoint-url http://minio:9000 \
  | grep "$(date -u '+%Y%m%d')"

# List today's MongoDB backups
aws s3 ls s3://sudoku-ultra-backups/mongodb/production/ \
  --endpoint-url http://minio:9000 \
  | grep "$(date -u '+%Y%m%d')"
```

---

## 2. Restore PostgreSQL

### 2a. Identify the target backup

```bash
aws s3 ls s3://sudoku-ultra-backups/postgres/production/ \
  --endpoint-url http://minio:9000 \
  | sort -k1,2 | tail -20
```

### 2b. Download and decompress

```bash
BACKUP_KEY="postgres/production/20260319T020000Z.dump.gz"
aws s3 cp "s3://sudoku-ultra-backups/${BACKUP_KEY}" /tmp/pg_restore.dump.gz \
  --endpoint-url http://minio:9000

gunzip /tmp/pg_restore.dump.gz
```

### 2c. Create a fresh database (if restoring to a new host)

```bash
psql -h $PGHOST -U postgres -c "CREATE DATABASE sudoku_ultra_restore;"
```

### 2d. Restore

```bash
pg_restore \
  --host=$PGHOST \
  --port=$PGPORT \
  --username=$PGUSER \
  --dbname=sudoku_ultra_restore \
  --format=custom \
  --no-owner \
  --no-privileges \
  --verbose \
  /tmp/pg_restore.dump
```

### 2e. Validate row counts

```sql
-- Connect to sudoku_ultra_restore
SELECT relname, n_live_tup
FROM pg_stat_user_tables
ORDER BY n_live_tup DESC
LIMIT 20;
```

### 2f. Cut over (blue/green swap)

```bash
# Update Helm values to point to new DB
helm upgrade sudoku-ultra ./infra/helm/sudoku-ultra \
  --set global.postgresUrl="postgresql://sudoku:$PGPASSWORD@$NEW_PGHOST:5432/sudoku_ultra_restore" \
  --reuse-values -n sudoku-ultra
```

---

## 3. Restore MongoDB

### 3a. Download and extract

```bash
BACKUP_KEY="mongodb/production/20260319T020000Z.tar.gz"
aws s3 cp "s3://sudoku-ultra-backups/${BACKUP_KEY}" /tmp/mongo_restore.tar.gz \
  --endpoint-url http://minio:9000

mkdir -p /tmp/mongorestore_work
tar -xzf /tmp/mongo_restore.tar.gz -C /tmp/mongorestore_work
```

### 3b. Restore

```bash
mongorestore \
  --uri="$MONGO_URI_NEW" \
  --db=sudoku_events \
  --gzip \
  --drop \
  /tmp/mongorestore_work/mongodump_sudoku_events_*/sudoku_events/
```

### 3c. Verify

```bash
mongosh "$MONGO_URI_NEW/sudoku_events" --eval "db.stats()"
```

---

## 4. Restore Kubernetes Cluster State

The cluster state is **GitOps-managed** via ArgoCD. No separate backup of Kubernetes objects is needed provided:
- All Helm chart changes are committed to `main`.
- `infra/argocd/` CRDs are committed.

### 4a. Fresh cluster bootstrap

```bash
# 1. Install ArgoCD
kubectl create namespace argocd
kubectl apply -n argocd \
  -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml

# 2. Apply ArgoCD project + application
kubectl apply -f infra/argocd/project.yaml -n argocd
kubectl apply -f infra/argocd/application.yaml -n argocd

# 3. ArgoCD auto-syncs from Git → cluster reaches desired state
argocd app wait sudoku-ultra --health --timeout 600
```

### 4b. Restore Vault secrets (must precede service startup)

```bash
# Re-populate Vault KV paths from a secure secrets export
vault kv put secret/sudoku-ultra/game-service \
  jwt_secret="$JWT_SECRET" \
  database_url="$DATABASE_URL" \
  sentry_dsn="$SENTRY_DSN"

vault kv put secret/sudoku-ultra/ml-service \
  database_url="$DATABASE_URL" \
  qdrant_api_key="$QDRANT_API_KEY" \
  sentry_dsn="$SENTRY_DSN" \
  pii_hmac_secret="$PII_HMAC_SECRET"

vault kv put secret/sudoku-ultra/multiplayer \
  jwt_secret="$JWT_SECRET" \
  database_url="$DATABASE_URL" \
  redis_url="$REDIS_URL" \
  sentry_dsn="$SENTRY_DSN"
```

---

## 5. Restore MinIO / ML Artifacts

MinIO data (MLflow artifacts, model exports, training data) lives on a PVC.
If the PVC is lost, models must be retrained or restored from a secondary MinIO replica.

### 5a. Re-bootstrap MinIO buckets

MinIO Helm chart `initContainers` recreate buckets on pod startup automatically.

### 5b. Restore model artifacts (from a secondary backup)

```bash
# If you maintain a secondary MinIO or S3 bucket as a mirror:
aws s3 sync s3://sudoku-ultra-backups-secondary/mlflow-artifacts/ \
  s3://mlflow-artifacts/ \
  --endpoint-url http://minio:9000
```

### 5c. Re-trigger model training (if no artifact backup)

```bash
# Trigger all retraining DAGs via Airflow CLI
for dag in retrain_classifier retrain_clustering retrain_regression \
           retrain_churn retrain_scanner retrain_gan; do
  airflow dags trigger $dag
done
```

---

## 6. Full Environment Rebuild

Use this runbook when the entire production environment is lost (region failure, catastrophic misconfiguration).

**Estimated time to recovery: ~4 hours**

| Step | Time | Owner |
|---|---|---|
| Provision new Kubernetes cluster | 30 min | Platform |
| Install cert-manager, ingress-nginx, ArgoCD | 20 min | Platform |
| Restore Vault and populate secrets | 30 min | Security |
| ArgoCD sync (all services) | 20 min | Platform |
| Restore PostgreSQL from MinIO backup | 45 min | Backend |
| Restore MongoDB from MinIO backup | 20 min | Backend |
| Verify all health checks green | 15 min | Platform |
| Run smoke tests | 20 min | QA |
| DNS cutover | 5 min | Platform |
| Monitor error rates for 30 min | 30 min | On-call |

---

## 7. Runbooks by Failure Scenario

### PostgreSQL pod OOMKilled / CrashLoopBackOff

```bash
kubectl describe pod -l app.kubernetes.io/component=postgresql -n sudoku-ultra
kubectl logs -l app.kubernetes.io/component=postgresql -n sudoku-ultra --previous
# Increase memory limit:
helm upgrade sudoku-ultra ./infra/helm/sudoku-ultra \
  --set postgresql.primary.resources.limits.memory=4Gi --reuse-values
```

### game-service returns 503 (Readiness probe failing)

```bash
kubectl get pods -l app.kubernetes.io/component=game-service -n sudoku-ultra
kubectl logs -l app.kubernetes.io/component=game-service -n sudoku-ultra --tail=100
# Check DB connectivity from pod:
kubectl exec -it deploy/sudoku-ultra-game-service -n sudoku-ultra -- \
  node -e "const p=require('@prisma/client');const c=new p.PrismaClient();c.\$connect().then(()=>console.log('ok'))"
```

### ML model accuracy alert fires

```bash
# Check recent training runs
kubectl exec -it deploy/sudoku-ultra-airflow -n sudoku-ultra -- \
  airflow dags list-runs -d retrain_classifier --limit 5
# Force retrain
airflow dags trigger retrain_classifier
```

### ArgoCD sync stuck / OutOfSync

```bash
argocd app sync sudoku-ultra --force
argocd app wait sudoku-ultra --health --timeout 300
# If self-heal is blocked by resource lock:
argocd app terminate-op sudoku-ultra
argocd app sync sudoku-ultra
```

### Vault unavailable (services falling back to env vars)

Services degrade gracefully — env vars from Kubernetes Secrets are used as fallback.
The `vault.enabled=false` path in Helm ensures services start without Vault.

1. Investigate Vault pod: `kubectl logs -n vault vault-0`
2. Unseal if sealed: `vault operator unseal`
3. Verify K8s auth: `vault auth list`

---

## 8. Testing the DR Plan

**Quarterly drill checklist:**

- [ ] Trigger `backup_dag` manually and verify MinIO objects exist
- [ ] Restore PostgreSQL to a `sudoku_ultra_dr_test` database; run row count checks
- [ ] Deploy a staging cluster from scratch using ArgoCD bootstrap
- [ ] Confirm all health endpoints return 200 after ArgoCD sync
- [ ] Verify Vault secret injection in the new cluster
- [ ] Document actual RTO achieved vs. 4-hour target
- [ ] Update this document with any lessons learned

Run the restore test:

```bash
# Non-destructive: restores to a separate DB on the same host
PGDATABASE=sudoku_ultra_dr_test \
  PGHOST=postgres-staging \
  ./infra/backup/backup_postgres.sh --env staging --dry-run
```

---

## 9. Contact & Escalation

| Role | Contact | Pager |
|---|---|---|
| Platform on-call | `#devops-alerts` Slack | PagerDuty — Platform |
| Database admin | `#backend` Slack | PagerDuty — Database |
| Security (Vault) | `#security` Slack | PagerDuty — Security |

Runbook links embedded in all Prometheus alert annotations point to `#` in this doc:
`https://github.com/your-org/sudoku-ultra/blob/main/docs/deployment/disaster-recovery.md`
