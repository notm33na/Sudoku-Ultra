# Phase 5 Architecture — Platform Maturity

## Overview

Phase 5 hardened Sudoku Ultra from a feature-complete platform into a production-ready system.
Ten deliverables focused on security, reliability, observability, and operational excellence.

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  Mobile App (React Native + Expo)                                            │
│  ErrorBoundary · AnalyticsService · DeepLinks · EAS builds                  │
│  Edge AI: SkillClassifier · PuzzleClusterer · Scanner (ONNX/TFLite)         │
└──────────────────────────────┬───────────────────────────────────────────────┘
                               │ HTTPS / WSS
                     ┌─────────▼─────────┐
                     │       Nginx       │  Security headers (CSP, HSTS, CORP,
                     │   API Gateway     │  COOP, X-Frame-Options, Permissions)
                     │   rate-limiting   │  limit_req_zone: auth/api/ws
                     └────────┬──────────┘
          ┌───────────────────┼───────────────────────┐
          │                   │                       │
  ┌───────▼──────┐   ┌────────▼────────┐   ┌─────────▼────────┐
  │ game-service │   │   ml-service    │   │   multiplayer    │
  │ Node/Express │   │   FastAPI       │   │   Go + WebSocket │
  │ port 3001    │   │   port 3003     │   │   port 3002      │
  │ authLimiter  │   │   Vault client  │   │   Vault client   │
  │ apiLimiter   │   │   (httpx async) │   │   (sync.Mutex)   │
  │ adminLimiter │   │                 │   │                  │
  │ Vault client │   │                 │   │                  │
  └───────┬──────┘   └────────┬────────┘   └─────────┬────────┘
          │                   │                       │
          └──────────────────┬┘                       │
                             │  OTel OTLP             │
                   ┌─────────▼─────────┐              │
                   │  OTel Collector   │◄─────────────┘
                   │  port 4317/4318   │
                   └──────┬──────┬─────┘
                          │      │
               ┌──────────▼──┐  ┌▼──────────────┐
               │  Prometheus │  │    Jaeger      │
               │  + Alertmgr │  │   (tracing)    │
               └──────┬──────┘  └───────────────┘
                      │
               ┌──────▼──────┐
               │   Grafana   │◄── Loki (logs)
               │  dashboards │
               └─────────────┘
```

---

## D1 — CI/CD Hardening

### What was added

- **Branch protection** — required status checks, 1-reviewer PR requirement, no force-push on `main`
- **Multi-environment workflow** — `ci.yml` gates: lint → unit tests → integration tests → build → push → deploy (staging) → smoke test → deploy (prod)
- **Security scanning** — Trivy image scan + CodeQL SAST in `security.yml`
- **Nightly pipeline** — `nightly.yml`: dependency audit (npm/pip/govulncheck/Trivy), k6 load tests, model drift, Lighthouse, Edge AI benchmarks
- **Release workflow** — `release.yml`: semver tagging, GitHub Releases, GHCR image promotion, EAS OTA update

### Key files

| File | Purpose |
|---|---|
| `.github/workflows/ci.yml` | Main CI pipeline |
| `.github/workflows/security.yml` | SAST + container scanning |
| `.github/workflows/nightly.yml` | Nightly audits + load tests |
| `.github/workflows/release.yml` | Release promotion |
| `docs/deployment/branch-protection.md` | Branch protection setup guide |

---

## D2 — MLOps Maturity

### What was added

- **Evidently drift monitoring** — PSI-based feature drift detection; nightly check via `/api/v1/analytics/drift-summary`
- **A/B experiment tracking** — MLflow Experiments with champion/challenger model comparison
- **Automated retraining triggers** — Airflow DAG polls drift endpoint; triggers retraining when PSI > 0.2
- **Model registry lifecycle** — Staging → Production promotion gates with accuracy thresholds

### Key files

| File | Purpose |
|---|---|
| `ml/pipelines/retrain_dag.py` | Airflow retraining DAG |
| `services/ml-service/app/services/drift_monitor.py` | Evidently PSI calculation |
| `docs/mlops/model-runbook.md` | Model update runbook |
| `docs/mlops/sla.md` | ML SLA commitments |

---

## D3 — Edge AI Maturity

### What was added

- **ONNX Skill Classifier** — on-device difficulty prediction; fallback to server API
- **ONNX Puzzle Clusterer** — on-device similar-puzzle grouping
- **TFLite Scanner** — on-device CV puzzle scanning with `expo-camera`
- **Benchmark harness** — `edgeAI.benchmark.ts`; warm-up 3 + measure 5 runs, reports p95 median
- **CI enforcement** — `edge-benchmarks` job in `nightly.yml`; p95 < 200 ms on Android emulator (Pixel 4 API 33)

### Performance targets

| Model | High-end | Mid-range | Low-end |
|---|---|---|---|
| Skill Classifier (ONNX) | p95 < 50 ms | p95 < 100 ms | p95 < 200 ms |
| Puzzle Clusterer (ONNX) | p95 < 50 ms | p95 < 100 ms | p95 < 200 ms |
| Scanner (TFLite) | p95 < 50 ms | p95 < 100 ms | p95 < 200 ms |

---

## D4 — Data Warehouse Maturity

### What was added

- **DuckDB analytical layer** — in-process analytics queries over Parquet snapshots
- **Warehouse summary endpoint** — `GET /api/v1/analytics/warehouse-summary`
- **ETL pipeline** — Airflow DAG exports PostgreSQL → Parquet → DuckDB
- **Grafana dashboards** — warehouse utilisation + query performance panels

---

## D5 — Full Observability Stack

### What was added

- **OpenTelemetry Collector** — central telemetry pipeline; receives OTLP from all services; exports to Prometheus (metrics), Loki (logs), Jaeger (traces)
- **Prometheus** — scrapes all services + k8s nodes/pods; alert rules (HighAPIErrorRate, HighAPILatency, MLModelAccuracyBreach, WebSocketConnectionSpike, PostgresSlowQueries, PodOOMKilled)
- **Grafana** — 5 dashboards: Game Service, ML Service, Multiplayer, Infrastructure, SLO Overview
- **Loki** — structured log aggregation; TraceID derived field links logs to Jaeger traces
- **Sentry** — exception capture across all three services + mobile ErrorBoundary

### Ports reference

| Component | Port | Protocol |
|---|---|---|
| OTel Collector (OTLP gRPC) | 4317 | gRPC |
| OTel Collector (OTLP HTTP) | 4318 | HTTP |
| OTel Collector (health) | 13133 | HTTP |
| OTel Collector (Prometheus exporter) | 8889 | HTTP |
| Prometheus | 9090 | HTTP |
| Grafana | 3000 | HTTP |
| Loki | 3100 | HTTP |
| Jaeger UI | 16686 | HTTP |
| Jaeger OTLP gRPC | 4317 | gRPC |

---

## D6 — Infrastructure as Code Complete

### Helm chart — `infra/helm/sudoku-ultra/`

All production services are defined as Helm templates with full values.yaml parameterisation.

| Template | Resource types |
|---|---|
| `game-service-deployment.yaml` | Deployment + Service + HPA |
| `ml-service-deployment.yaml` | Deployment + Service + HPA |
| `multiplayer-deployment.yaml` | Deployment + Service + HPA |
| `minio.yaml` | StatefulSet + Service + initContainers (bucket creation) |
| `prometheus.yaml` | Deployment + PVC + scrape ConfigMap + alert rules ConfigMap + Service |
| `grafana.yaml` | Deployment + PVC + datasources ConfigMap + dashboard-provider ConfigMap + Service |
| `otel-collector.yaml` | Deployment + ConfigMap (embedded config) + Service |
| `nginx-configmap.yaml` | ConfigMap (security headers, rate-limit zones) |
| `network-policies.yaml` | Default-deny + 8 allow NetworkPolicies |
| `rbac.yaml` | Role + RoleBinding + Prometheus ClusterRole/ClusterRoleBinding |

### Vault secret injection

All three services use HashiCorp Vault for secret management:

```
┌─────────────────────────────────────────────────────┐
│  Kubernetes Pod                                      │
│  ┌──────────────────┐  ┌─────────────────────────┐  │
│  │  App Container   │  │  Vault Agent Sidecar     │  │
│  │  reads env vars  │◄─│  K8s auth → Vault token  │  │
│  │  from mounted    │  │  renders secrets to      │  │
│  │  secret file     │  │  /vault/secrets/config   │  │
│  └──────────────────┘  └─────────────────────────┘  │
└─────────────────────────────────────────────────────┘
```

Secret paths: `secret/data/sudoku-ultra/{game-service,ml-service,multiplayer}`

### Terraform — `infra/terraform/`

| Module / file | Resources |
|---|---|
| `main.tf` | VPC, EKS cluster, RDS (PostgreSQL 16), ElastiCache, S3, ECR |
| `monitoring.tf` | Grafana Cloud: service accounts, folders, dashboards, datasources (Prometheus/Loki/Tempo), Slack contact points, notification policy |
| `vault.tf` | Vault cluster, K8s auth backend, policies, roles |

### ArgoCD GitOps

- `infra/argocd/app.yaml` — Application CR pointing to `infra/helm/sudoku-ultra/`
- `infra/argocd/notifications.yaml` — Slack notifications for sync-failed, sync-succeeded, health-degraded

### Backup strategy

| Database | Tool | Destination | Schedule | Retention |
|---|---|---|---|---|
| PostgreSQL | pg_dump (custom format) | MinIO s3://sudoku-ultra-backups | 02:00 UTC daily | 30 days |
| MongoDB | mongodump (gzip) | MinIO s3://sudoku-ultra-backups | 02:00 UTC daily | 30 days |

Airflow DAG `backup_dag.py` orchestrates both jobs and verifies object counts via boto3.

See [Disaster Recovery Runbook](disaster-recovery.md) for restore procedures.

---

## D7 — Security Hardening

### Defence-in-depth layers

```
Internet
   │
   ▼
[Nginx]  ── security headers (CSP, HSTS, X-Frame-Options, CORP, COOP,
             Permissions-Policy, Referrer-Policy, X-Content-Type-Options)
          ── server_tokens off
          ── rate-limit zones: auth 10r/m | api 100r/m | ws 30r/m
          ── limit_conn 20 per IP
   │
   ▼
[Express Middleware]
   ── helmet (mirrors CSP + HSTS in app layer)
   ── trust proxy 1 (correct client IP from nginx)
   ── authLimiter  (10 req / 15 min, skipSuccessfulRequests)
   ── apiLimiter   (300 req / min)
   ── adminLimiter (30 req / min)
   │
   ▼
[Kubernetes NetworkPolicy]
   ── default-deny-ingress (all pods)
   ── explicit allow: game-service ← nginx, multiplayer, prometheus
   ── explicit allow: ml-service ← game-service, multiplayer, kafka-consumer, prometheus
   ── explicit allow: postgresql ← game-service, ml-service
   ── explicit allow: redis ← game-service, multiplayer
   │
   ▼
[Pod Security]
   ── runAsNonRoot: true
   ── runAsUser: 1000
   ── allowPrivilegeEscalation: false
   ── capabilities.drop: [ALL]
   ── RBAC: least-privilege Role (get/list/watch only)
```

### SAST / SCA pipeline

| Scanner | Trigger | Scope |
|---|---|---|
| CodeQL | PR + push to main | JS/TypeScript + Python (`security-extended` queries) |
| Trivy (image) | PR + push to main | All container images (CRITICAL/HIGH, block on fixable) |
| Trivy (filesystem) | Nightly | Full repo filesystem |
| npm audit | Nightly | Node.js dependencies |
| pip-audit | Nightly | Python dependencies |
| govulncheck | Nightly | Go dependencies |
| ZAP (DAST) | CI on staging | OWASP Top 10 scanning |

---

## D8 — Mobile Polish & Release

### Release infrastructure

```
Developer
   │  git push + PR merge
   ▼
CI (ci.yml) → build + test → GHCR image push
   │
   ▼
release.yml (on semver tag vX.Y.Z)
   ├── GitHub Release (changelog auto-generated)
   ├── GHCR: promote :sha → :vX.Y.Z + :latest
   └── EAS: eas update --channel production (OTA delta)

EAS Build profiles:
   development  → simulator APK (internal distribution)
   preview      → adhoc iOS + APK (staging channel)
   production   → AAB + IPA (autoIncrement, production channel)
```

### Mobile features added

| Feature | Implementation |
|---|---|
| Error boundary | `ErrorBoundary.tsx` — Sentry capture, dev stack trace, Restart button |
| Analytics | `analytics.service.ts` — anonId/sessionId, 30s flush, 20-event threshold, re-queue on 5xx |
| Deep links | `deepLink.ts` — `sudokuultra://` scheme + `https://sudokuultra.example.com` universal links, 15 routes |
| Push notifications | `expo-notifications` plugin, `UIBackgroundModes: [fetch, remote-notification]` |
| Universal links | iOS `associatedDomains`, Android `intentFilters` for `/join` and `/puzzle` |

---

## D9 — Load Testing & Performance

### k6 test suite — `k6/scripts/`

| Script | Scenario | VUs | Duration | Pass criteria |
|---|---|---|---|---|
| `smoke.js` | Health checks | 1 | 30 s | All 2xx |
| `game.js` | Game service load | 50 | 6 min | p95 < 500 ms, error < 1% |
| `ml.js` | ML service load | 10 | 5 min | p95 < 5000 ms, error < 2% |
| `friends.js` | Friends/social load | 50 | 6 min | p95 < 500 ms, error < 1% |
| `multiplayer.js` | WebSocket (WS) load | 100 | 5 min | WS handshake p95 < 500 ms |
| `full-journey.js` | End-to-end user journey | 50 | 6 min | `journey_failed` < 5 |
| `rate-limit.js` | 429 verification | 1 | 1 iter | `rate_limit_429_count` >= 3 |

### Nightly regression gate

The nightly `k6-load-tests` job compares p95 against baselines; any breach > 20% opens a GitHub issue labelled `performance` + `nightly`.

See [Performance Budget](performance-budget.md) for full SLO tables and baseline values.

---

## D10 — Documentation & Runbooks

This document. Additional docs delivered:

| Document | Path |
|---|---|
| On-Call Runbook | `docs/operations/on-call-runbook.md` |
| Contributing Guide | `docs/development/contributing.md` |
| Disaster Recovery | `docs/deployment/disaster-recovery.md` |
| Performance Budget | `docs/deployment/performance-budget.md` |
| Helm + Terraform + ArgoCD Guide | `docs/deployment/helm-terraform-argocd.md` |
| Model Runbook | `docs/mlops/model-runbook.md` |
| MLOps SLA | `docs/mlops/sla.md` |
| Branch Protection Setup | `docs/deployment/branch-protection.md` |

---

## Security model summary

| Boundary | Controls |
|---|---|
| Public internet → Nginx | TLS termination, rate limiting, security headers |
| Nginx → Services | Internal cluster network, NetworkPolicy allow-lists |
| Service → Service | NetworkPolicy micro-segmentation, mTLS (future) |
| Service → Secrets | Vault K8s auth, short-lived tokens (TTL 1h), no env var secrets in production |
| Service → Database | NetworkPolicy (pod selector), Vault-managed credentials |
| Container runtime | Non-root UID 1000, drop ALL capabilities, no privilege escalation |
| Supply chain | SAST (CodeQL), SCA (Trivy/npm audit/pip-audit/govulncheck), DAST (ZAP) |

---

## Infrastructure sizing (production defaults)

| Service | Replicas | CPU request | CPU limit | Memory request | Memory limit |
|---|---|---|---|---|---|
| game-service | 2 | 250m | 1000m | 256Mi | 512Mi |
| ml-service | 2 | 500m | 2000m | 512Mi | 2Gi |
| multiplayer | 2 | 250m | 1000m | 256Mi | 512Mi |
| Prometheus | 1 | 500m | 1000m | 1Gi | 2Gi |
| Grafana | 1 | 250m | 500m | 256Mi | 512Mi |
| OTel Collector | 1 | 200m | 500m | 256Mi | 512Mi |
| MinIO | 1 (StatefulSet) | 500m | 1000m | 512Mi | 1Gi |

HPA is configured on all three application services (min 2, max 10, target CPU 70%).
