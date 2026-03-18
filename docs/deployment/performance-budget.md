# Performance Budget — Sudoku Ultra

> **Policy:** Any p95 latency regression > 20% above baseline blocks release.
> Nightly k6 suite enforces these thresholds automatically.
> Last reviewed: 2026-03-19

---

## Service SLOs

### game-service (HTTP)

| Endpoint | p50 target | p95 target | p99 target | Error rate |
|---|---|---|---|---|
| `GET /health` | < 10 ms | < 30 ms | < 50 ms | < 0.1% |
| `GET /api/home` | < 80 ms | < 300 ms | < 500 ms | < 1% |
| `POST /api/auth/login` | < 100 ms | < 300 ms | < 500 ms | < 1% |
| `POST /api/auth/register` | < 150 ms | < 400 ms | < 600 ms | < 1% |
| `GET /api/puzzles` | < 50 ms | < 200 ms | < 400 ms | < 1% |
| `POST /api/sessions` | < 100 ms | < 400 ms | < 600 ms | < 1% |
| `PATCH /api/sessions/:id` | < 80 ms | < 300 ms | < 500 ms | < 1% |
| `POST /api/sessions/:id/complete` | < 150 ms | < 500 ms | < 800 ms | < 1% |
| `GET /api/scores` | < 60 ms | < 300 ms | < 500 ms | < 1% |
| `GET /api/daily` | < 50 ms | < 200 ms | < 400 ms | < 1% |
| `POST /api/admin/gdpr/delete` | < 500 ms | < 2000 ms | < 5000 ms | < 1% |

### ml-service (HTTP)

| Endpoint | p50 target | p95 target | p99 target | Error rate |
|---|---|---|---|---|
| `GET /health` | < 10 ms | < 30 ms | < 50 ms | < 0.1% |
| `POST /api/v1/xai/cell-importance` | < 500 ms | < 3000 ms | < 5000 ms | < 2% |
| `POST /api/v1/gan/generate` | < 2000 ms | < 8000 ms | < 15000 ms | < 2% |
| `POST /api/v1/search/puzzles/similar-features` | < 200 ms | < 2000 ms | < 3000 ms | < 2% |
| `POST /api/v1/tutor/hint` | < 300 ms | < 2000 ms | < 5000 ms | < 2% |
| `GET /api/v1/analytics/warehouse-summary` | < 300 ms | < 1500 ms | < 3000 ms | < 1% |

### multiplayer-service (HTTP + WebSocket)

| Metric | Target |
|---|---|
| `POST /rooms` p95 | < 800 ms |
| WebSocket handshake p95 | < 500 ms |
| Cell update round-trip p95 | < 100 ms |
| Active connections (steady state) | ≤ 4000 |
| WS error rate | < 1% |
| Room creation error rate | < 1% |

---

## Concurrency Targets

Measured at steady-state load; all targets must hold for the soak duration (30 min at 20 VUs).

| Scenario | VUs | Duration | Pass criteria |
|---|---|---|---|
| Smoke | 1 | 30 s | All endpoints return 2xx |
| Load | 50 | 6 min | p95 < 500 ms, error < 1% |
| Soak | 20 | 30 min | p95 < 800 ms, error < 1%, no memory leak |
| Stress | 200 | 10 min | p95 < 2000 ms, error < 5% |
| Spike (200 VU burst) | 200 → 5 | 2.5 min | p95 < 3000 ms, error < 10% |
| Full journey | 50 | 6 min | `journey_failed` count < 5 |
| Multiplayer WS | 100 | 5 min | WS handshake p95 < 500 ms |

---

## Mobile Edge AI Budgets

Measured on-device via `edgeAI.benchmark.ts` (warm-up 3 runs, measure 5 runs, report median).

| Model | High-end (≤ 50 ms) | Mid-range (≤ 100 ms) | Low-end (≤ 200 ms) |
|---|---|---|---|
| Skill Classifier (ONNX) | p95 < 50 ms | p95 < 100 ms | p95 < 200 ms |
| Puzzle Clustering (ONNX) | p95 < 50 ms | p95 < 100 ms | p95 < 200 ms |
| Scanner (TFLite) | p95 < 50 ms | p95 < 100 ms | p95 < 200 ms |

All three models must pass on all three device profiles in CI.

---

## Nightly Regression Gate

The nightly k6 job (`nightly.yml`) reads JSON results and checks p95 against these baselines:

| Script | Baseline p95 |
|---|---|
| `smoke.js` | 500 ms |
| `game.js` | 500 ms |
| `ml.js` | 5000 ms |
| `friends.js` | 500 ms |
| `multiplayer.js` (HTTP) | 800 ms |
| `full-journey.js` | 800 ms |

**Regression threshold:** baseline × 1.20 (20% slack).
Any breach opens a GitHub issue with label `performance` + `nightly`.

---

## Bundle Size Budget

| Platform | Max bundle size | Enforced by |
|---|---|---|
| Android (OTA update) | 25 MB | `ota-update.yml` bundle-size job |
| iOS (OTA update) | 25 MB | `ota-update.yml` bundle-size job |

---

## Prometheus Alert Alignment

These SLOs map directly to Prometheus alert rules in `infra/prometheus/rules/alerts.yml`:

| Alert | Threshold | SLO source |
|---|---|---|
| `HighAPIErrorRate` | 5xx rate > 5% for 5 min | game-service error rate < 1% |
| `HighAPILatency` | P99 > 2 s for 5 min | game-service p99 < 500–800 ms |
| `MLModelAccuracyBreach` | accuracy/AUC below threshold | ML model quality SLO |
| `WebSocketConnectionSpike` | > 4000 connections | multiplayer ≤ 4000 target |
| `PostgresSlowQueries` | avg > 0.5 s for 5 min | DB p95 < 100 ms (internal) |
| `PodOOMKilled` | count > 0 | memory limit compliance |

---

## How to Update Baselines

After a planned architecture change that legitimately improves or increases latency:

1. Run the full nightly suite against staging manually.
2. Record new p95 values from `k6/results/*.json`.
3. Update the baseline table above and the `BASELINES` map in `nightly.yml`.
4. Commit with message: `perf: update performance baselines for <change>`.
