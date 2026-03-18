# On-Call Runbook — Sudoku Ultra

> **Severity definitions**
> - **P0** — Complete service outage, data loss risk, or security breach. Page immediately.
> - **P1** — Partial outage or significant performance degradation affecting > 10% of users.
> - **P2** — Degraded feature, elevated error rate, non-critical service down.
> - **P3** — Informational; no user impact. Address during business hours.

---

## Escalation path

| Rotation | Contact | Scope |
|---|---|---|
| Primary on-call | PagerDuty rotation | First responder for all P0/P1 |
| Secondary on-call | PagerDuty rotation | Backup if primary unresponsive > 10 min |
| Engineering lead | Direct Slack DM | P0 only; architecture decisions |
| Database admin | `#ops-db` Slack | PostgreSQL/MongoDB P0 incidents |
| Security on-call | `#security-alerts` Slack | Any suspected breach |

**Target response times**

| Severity | Acknowledge | Mitigate | Resolve |
|---|---|---|---|
| P0 | 5 min | 30 min | 4 h (RTO) |
| P1 | 15 min | 1 h | 8 h |
| P2 | 1 h | 4 h | 24 h |
| P3 | Next business day | — | — |

---

## Grafana dashboards

| Dashboard | URL (port-forward) | Use for |
|---|---|---|
| Game Service | `http://localhost:3000/d/game-service` | API latency, error rates |
| ML Service | `http://localhost:3000/d/ml-service` | Inference latency, model load |
| Multiplayer | `http://localhost:3000/d/multiplayer` | WS connections, room count |
| Infrastructure | `http://localhost:3000/d/infrastructure` | CPU, memory, disk, network |
| SLO Overview | `http://localhost:3000/d/slo-overview` | All SLO burn rates |

```bash
# Port-forward Grafana from k8s
kubectl port-forward svc/grafana 3000:3000 -n sudoku-ultra
```

---

## Alert → Runbook mapping

| Alert name | Severity | Section |
|---|---|---|
| `HighAPIErrorRate` | P1 | [Game service 5xx spike](#1-game-service-5xx-spike) |
| `HighAPILatency` | P1 | [Game service latency](#2-game-service-high-latency) |
| `WebSocketConnectionSpike` | P1 | [Multiplayer overload](#3-multiplayer-service-overload) |
| `MLModelAccuracyBreach` | P2 | [ML model degraded](#4-ml-service-model-degraded) |
| `PostgresSlowQueries` | P1 | [PostgreSQL slow queries](#5-postgresql-slow-queries) |
| `PodOOMKilled` | P1 | [OOM killed pod](#6-pod-oom-killed) |
| `[Nightly] k6 threshold regression` | P2 | [Performance regression](#7-nightly-performance-regression) |
| `[Nightly] Model drift detected` | P2 | [Model drift](#8-model-drift) |
| Vault auth failure | P0 | [Vault unavailable](#9-vault-unavailable) |
| ArgoCD sync failed | P1 | [ArgoCD sync failure](#10-argocd-sync-failure) |

---

## Incident response playbook

### Standard procedure for any incident

```
1. Acknowledge the alert in PagerDuty within SLA
2. Open incident channel: /incident create in Slack (or use #incidents)
3. Post initial update: "Investigating <alert name>, started <time>"
4. Follow the relevant runbook section below
5. Post updates every 15 min (P0) or 30 min (P1)
6. When resolved: post resolution summary + timeline
7. Open post-mortem issue (P0 and P1) within 48 h
```

---

## Runbooks

### 1. Game service 5xx spike

**Alert:** `HighAPIErrorRate` — 5xx rate > 5% for 5 min

**Step 1 — Confirm scope**
```bash
kubectl get pods -n sudoku-ultra -l app=game-service
kubectl logs -n sudoku-ultra -l app=game-service --since=10m | grep -E 'ERROR|5[0-9]{2}'
```

**Step 2 — Check recent deployments**
```bash
kubectl rollout history deployment/game-service -n sudoku-ultra
# If recent rollout is suspect:
kubectl rollout undo deployment/game-service -n sudoku-ultra
```

**Step 3 — Check database connectivity**
```bash
kubectl exec -n sudoku-ultra deploy/game-service -- \
  node -e "const { PrismaClient } = require('@prisma/client'); \
  const p = new PrismaClient(); p.\$queryRaw\`SELECT 1\`.then(() => console.log('DB OK')).catch(console.error)"
```

**Step 4 — Check Vault**
```bash
kubectl logs -n sudoku-ultra -l app=game-service --since=5m | grep -i vault
# If Vault auth is failing, see runbook #9
```

**Step 5 — Scale if resource-starved**
```bash
kubectl scale deployment/game-service -n sudoku-ultra --replicas=4
```

**Escalate to P0** if error rate exceeds 50% for > 5 min or if root cause is data corruption.

---

### 2. Game service high latency

**Alert:** `HighAPILatency` — p99 > 2 s for 5 min

**Step 1 — Identify slow endpoints**
```bash
# Grafana: Game Service dashboard → Endpoint Latency panel → sort by p99
# Or query Prometheus directly:
kubectl port-forward svc/prometheus 9090:9090 -n sudoku-ultra &
curl -s 'http://localhost:9090/api/v1/query?query=histogram_quantile(0.99,rate(http_request_duration_seconds_bucket[5m]))' | jq .
```

**Step 2 — Check database queries**
```bash
# PostgreSQL slow query log
kubectl exec -n sudoku-ultra deploy/postgresql -- \
  psql -U postgres -c "SELECT query, mean_exec_time, calls FROM pg_stat_statements ORDER BY mean_exec_time DESC LIMIT 10;"
```

**Step 3 — Check Redis**
```bash
kubectl exec -n sudoku-ultra deploy/game-service -- \
  node -e "const r = require('ioredis'); const c = new r(process.env.REDIS_URL); c.ping().then(console.log)"
```

**Step 4 — Check HPA / CPU throttling**
```bash
kubectl top pods -n sudoku-ultra -l app=game-service
kubectl get hpa -n sudoku-ultra
```

**Step 5 — Enable query explain logging (temporary)**
```bash
# Set in postgres: log_min_duration_statement = 500 (log queries > 500ms)
kubectl exec -n sudoku-ultra deploy/postgresql -- \
  psql -U postgres -c "ALTER SYSTEM SET log_min_duration_statement = 500; SELECT pg_reload_conf();"
```

Remember to revert after investigation: set `log_min_duration_statement = -1`.

---

### 3. Multiplayer service overload

**Alert:** `WebSocketConnectionSpike` — WS connections > 4000

**Step 1 — Assess current connection count**
```bash
kubectl exec -n sudoku-ultra deploy/multiplayer -- \
  wget -qO- http://localhost:8080/metrics | grep ws_active_connections
```

**Step 2 — Check room leak (rooms not cleaned up)**
```bash
kubectl logs -n sudoku-ultra -l app=multiplayer --since=30m | grep -E 'room|connection' | tail -50
```

**Step 3 — Scale multiplayer**
```bash
kubectl scale deployment/multiplayer -n sudoku-ultra --replicas=4
```

**Step 4 — If connections are legitimate (traffic spike)**
- Verify Redis pub/sub is not lagging: check `redis_connected_clients` in Grafana
- Verify Nginx `limit_conn` is not blocking valid connections (check 503 rate in Nginx logs)

**Step 5 — If connections are not draining (bug)**
```bash
# Rolling restart to flush stale connections
kubectl rollout restart deployment/multiplayer -n sudoku-ultra
```

---

### 4. ML service model degraded

**Alert:** `MLModelAccuracyBreach` — accuracy/AUC below registered threshold

**Step 1 — Check drift endpoint**
```bash
curl -sf -H "Authorization: Bearer $STAGING_AUTH_TOKEN" \
  "$STAGING_ML_URL/api/v1/analytics/drift-summary" | python3 -m json.tool
```

**Step 2 — Check MLflow for recent model versions**
```bash
kubectl port-forward svc/mlflow 5000:5000 -n mlops &
# Open http://localhost:5000 → Experiments → difficulty-classifier → compare runs
```

**Step 3 — Roll back model**
```bash
# Identify last known good version
mlflow models list-versions -n difficulty-classifier
# Set staging version back to Production
mlflow models transition-model-version-stage \
  --name difficulty-classifier \
  --version <LAST_GOOD_VERSION> \
  --stage Production
# Restart ml-service to reload
kubectl rollout restart deployment/ml-service -n sudoku-ultra
```

**Step 4 — If accuracy breach is not drift-related** (data issue)
- Check Airflow ETL DAG for recent failures in the `#mlops-alerts` Slack channel
- See [Model Runbook](../mlops/model-runbook.md) for full retraining procedure

---

### 5. PostgreSQL slow queries

**Alert:** `PostgresSlowQueries` — average query time > 0.5 s for 5 min

**Step 1 — Identify offending queries**
```bash
kubectl exec -n sudoku-ultra deploy/postgresql -- psql -U postgres sudoku_ultra -c "
  SELECT query, calls, mean_exec_time, total_exec_time
  FROM pg_stat_statements
  WHERE mean_exec_time > 500
  ORDER BY total_exec_time DESC
  LIMIT 10;"
```

**Step 2 — Check for lock waits**
```bash
kubectl exec -n sudoku-ultra deploy/postgresql -- psql -U postgres sudoku_ultra -c "
  SELECT pid, wait_event_type, wait_event, state, query
  FROM pg_stat_activity
  WHERE wait_event IS NOT NULL;"
```

**Step 3 — Check table bloat / missing indexes**
```bash
kubectl exec -n sudoku-ultra deploy/postgresql -- psql -U postgres sudoku_ultra -c "
  SELECT schemaname, tablename, pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size
  FROM pg_tables
  ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC
  LIMIT 10;"
```

**Step 4 — Terminate blocking long-running queries** (with caution)
```bash
# Identify PID first; only cancel queries blocking for > 30s
kubectl exec -n sudoku-ultra deploy/postgresql -- psql -U postgres -c "
  SELECT pg_cancel_backend(<PID>);"
```

**Step 5 — Run VACUUM if table bloat is high**
```bash
kubectl exec -n sudoku-ultra deploy/postgresql -- psql -U postgres sudoku_ultra -c "VACUUM ANALYZE;"
```

---

### 6. Pod OOM Killed

**Alert:** `PodOOMKilled` — any pod OOM count > 0

**Step 1 — Identify which pod was killed**
```bash
kubectl get events -n sudoku-ultra --field-selector reason=OOMKilling --sort-by='.lastTimestamp'
kubectl describe pod <POD_NAME> -n sudoku-ultra | grep -A 5 OOMKilled
```

**Step 2 — Check current memory usage**
```bash
kubectl top pods -n sudoku-ultra
```

**Step 3 — Increase memory limit (short-term fix)**
```bash
# Edit values.yaml and helm upgrade, or patch directly for immediate relief:
kubectl patch deployment <SERVICE_NAME> -n sudoku-ultra \
  --type=json \
  -p='[{"op":"replace","path":"/spec/template/spec/containers/0/resources/limits/memory","value":"1Gi"}]'
```

**Step 4 — Identify memory leak (if recurring)**
```bash
# Enable heap dump on next OOM (Node.js):
kubectl set env deployment/game-service -n sudoku-ultra NODE_OPTIONS="--heapsnapshot-signal=SIGUSR2"
# For Go/Python: attach pprof or py-spy to running pod
```

**Step 5 — Long-term fix**
File an issue with the heap/pprof dump attached. Update resource limits in `values.yaml` and commit via PR.

---

### 7. Nightly performance regression

**Alert:** GitHub issue `[Nightly] k6 threshold regression`

**Step 1 — Review the issue**
The auto-created issue links to the workflow run. Download the `nightly-k6-results` artifact.

**Step 2 — Identify the regressed script and metric**
```bash
# The issue body will contain lines like:
# FAIL game/http_req_duration_p95: 650ms > 600ms (baseline 500ms + 20%)
```

**Step 3 — Compare with recent deployments**
```bash
git log --oneline --since="2 days ago" -- services/
```

**Step 4 — If regression is intentional** (planned architecture change)
Follow the baseline update procedure in [Performance Budget](performance-budget.md#how-to-update-baselines).

**Step 5 — If regression is a bug**
- Profile the service locally: `k6 run k6/scripts/game.js --env BASE_URL=http://localhost:3001`
- Check for N+1 queries, missing cache hits, or new middleware overhead

---

### 8. Model drift

**Alert:** GitHub issue `[Nightly] Model drift detected` — PSI > 0.2

**Step 1 — Review drift summary**
```bash
# Download nightly-drift-summary artifact from the failing workflow run
# Or call the endpoint directly:
curl -sf -H "Authorization: Bearer $AUTH_TOKEN" \
  "$ML_URL/api/v1/analytics/drift-summary" | python3 -m json.tool
```
PSI > 0.2 = significant drift. PSI 0.1–0.2 = moderate (warning only).

**Step 2 — Assess impact**
- Check model accuracy metrics in MLflow
- Check `MLModelAccuracyBreach` alert — if also firing, this is P1

**Step 3 — Trigger retraining**
```bash
# Manual Airflow trigger:
kubectl port-forward svc/airflow-webserver 8080:8080 -n mlops &
# Open http://localhost:8080 → DAGs → retrain_on_drift → Trigger DAG
# Or via CLI:
airflow dags trigger retrain_on_drift --conf '{"model": "difficulty-classifier"}'
```

**Step 4 — Monitor retraining run in MLflow**
Wait for new model version; promote if metrics meet threshold. See [Model Runbook](../mlops/model-runbook.md).

---

### 9. Vault unavailable

**Severity: P0**

If Vault is unavailable, services fall back to environment variables (set during pod startup from last-known-good values). This is safe for < 24 h but secrets cannot be rotated until Vault is restored.

**Step 1 — Check Vault pod status**
```bash
kubectl get pods -n vault
kubectl logs -n vault -l app=vault --since=10m
```

**Step 2 — Check Vault seal status**
```bash
kubectl exec -n vault vault-0 -- vault status
# If sealed: unseal with 3 of 5 unseal keys (stored in AWS Secrets Manager)
kubectl exec -n vault vault-0 -- vault operator unseal <KEY_1>
kubectl exec -n vault vault-0 -- vault operator unseal <KEY_2>
kubectl exec -n vault vault-0 -- vault operator unseal <KEY_3>
```

**Step 3 — Check K8s auth backend**
```bash
kubectl exec -n vault vault-0 -- vault auth list
# Verify kubernetes/ auth method is enabled and configured
```

**Step 4 — Restart affected services** (to pick up fresh Vault tokens)
```bash
kubectl rollout restart deployment/game-service deployment/ml-service deployment/multiplayer -n sudoku-ultra
```

**Step 5 — Escalate** to security on-call immediately if Vault was unreachable due to suspected breach.

---

### 10. ArgoCD sync failure

**Alert:** ArgoCD Slack notification `sync-failed`

**Step 1 — Check sync status**
```bash
argocd app get sudoku-ultra
argocd app sync-status sudoku-ultra
```

**Step 2 — View sync errors**
```bash
argocd app logs sudoku-ultra
# Or in ArgoCD UI: Application → Sync → Events tab
```

**Step 3 — Common causes and fixes**

| Symptom | Fix |
|---|---|
| Helm template render error | Check `values.yaml` syntax; run `helm template infra/helm/sudoku-ultra` locally |
| Image pull error | Check GHCR credentials; verify `imagePullSecret` in namespace |
| Resource conflict (already exists) | `argocd app sync sudoku-ultra --force` (use with caution) |
| CRD version mismatch | Update CRDs manually before syncing: `kubectl apply -f infra/crds/` |
| Timeout during rollout | Check pod readiness; look for OOM or failed liveness probes |

**Step 4 — Manual sync with prune**
```bash
argocd app sync sudoku-ultra --prune
```

**Step 5 — Last resort: roll back ArgoCD app**
```bash
argocd app history sudoku-ultra
argocd app rollback sudoku-ultra <REVISION>
```

---

## Post-incident checklist

After resolving any P0 or P1:

- [ ] Confirm all alerts are resolved in PagerDuty
- [ ] Post resolution summary in incident Slack channel
- [ ] Close incident bridge
- [ ] Open post-mortem GitHub issue within 48 h (template: `docs/operations/postmortem-template.md`)
- [ ] Identify action items (prevent recurrence, improve detection, reduce MTTR)
- [ ] Assign owners + due dates to all action items
- [ ] Schedule blameless post-mortem meeting within 5 business days (P0 only)

---

## Quick reference

### Restart a service
```bash
kubectl rollout restart deployment/<service> -n sudoku-ultra
kubectl rollout status deployment/<service> -n sudoku-ultra
```

### Roll back a deployment
```bash
kubectl rollout undo deployment/<service> -n sudoku-ultra
```

### Scale up for traffic spike
```bash
kubectl scale deployment/<service> -n sudoku-ultra --replicas=<N>
```

### Get recent error logs
```bash
kubectl logs -n sudoku-ultra -l app=<service> --since=15m | grep -iE 'error|fatal|panic'
```

### Check resource usage
```bash
kubectl top pods -n sudoku-ultra
kubectl top nodes
```

### Port-forward observability stack
```bash
kubectl port-forward svc/grafana 3000:3000 -n sudoku-ultra &
kubectl port-forward svc/prometheus 9090:9090 -n sudoku-ultra &
kubectl port-forward svc/jaeger-query 16686:16686 -n sudoku-ultra &
```

### Check HPA status
```bash
kubectl get hpa -n sudoku-ultra
kubectl describe hpa <service>-hpa -n sudoku-ultra
```

### Inspect Vault secret (read-only)
```bash
kubectl exec -n vault vault-0 -- vault kv get secret/sudoku-ultra/game-service
```
