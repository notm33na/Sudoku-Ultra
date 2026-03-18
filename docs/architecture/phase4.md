# Phase 4 Architecture

## Overview

Phase 4 added eight major capabilities to Sudoku Ultra on top of the Phase 3
multiplayer and bot-opponent foundation. This document describes the new
components, their responsibilities, and how they interact.

```
┌─────────────────────────────────────────────────────────────────────────┐
│  Mobile App (React Native)                                               │
│  HomeScreen · LessonsScreen · LessonDetailScreen · OnboardingScreen     │
│  FriendsScreen · ActivityFeedScreen · DifficultyOverlay                  │
└──────────────────────────┬──────────────────────────────────────────────┘
                           │ HTTPS / WS
                    ┌──────▼──────┐
                    │    Nginx    │  API gateway (port 80 / 443)
                    │  api-gateway│  Routes: /api/* → game-service
                    └──────┬──────┘         /ml/*  → ml-service
                           │                /rooms/* → multiplayer
          ┌────────────────┼──────────────────────┐
          │                │                      │
   ┌──────▼──────┐  ┌──────▼──────┐  ┌───────────▼──────────┐
   │game-service │  │ ml-service  │  │   multiplayer (Go)   │
   │ Node/Express│  │  FastAPI    │  │   WebSocket rooms    │
   │  port 3001  │  │  port 3003  │  │   port 3002          │
   └──────┬──────┘  └──────┬──────┘  └──────────────────────┘
          │                │
     ┌────▼────┐    ┌──────▼──────────────────────────────────┐
     │Postgres │    │  Qdrant       Ollama      MLflow         │
     │  RDS    │    │  vector DB    local LLM   experiment     │
     └─────────┘    │  port 6333    port 11434  tracking       │
                    └─────────────────────────────────────────-┘
```

---

## D1 — RAG Technique Tutor

**Files:** `services/ml-service/app/routers/tutor.py`, `app/services/tutor_service.py`

A LangChain ReAct agent backed by:

- **Qdrant** (`techniques` collection, 384-dim cosine) — 20 technique documents
  seeded by `ml/scripts/seed_techniques.py`.
- **Ollama** (default model: `llama3`) — local LLM for answer generation.
- **sentence-transformers** `all-MiniLM-L6-v2` — query embedding.

Flow: user question → embed query → Qdrant similarity search → top-k chunks
injected into LangChain prompt → Ollama generates answer → returned to client.

If Qdrant or Ollama is unreachable the service falls back to a rule-based
keyword matcher so the endpoint never returns 5xx in dev.

**Endpoint:** `POST /api/v1/tutor/ask`

---

## D2 — XAI Technique Overlay

**Files:** `services/ml-service/app/routers/xai.py`, `app/ml/xai.py`

SHAP TreeExplainer applied to the difficulty classifier to produce a
per-cell importance heatmap.  The 81-cell grid is mapped to 10 aggregate
features (candidate density, constraint saturation, backtrack depth, etc.),
SHAP values are computed, then redistributed back to individual cells via a
weighted mapping.  Values are min-max normalised to [0, 1].

The mobile `DifficultyOverlay` component renders the heatmap as a coloured
cell overlay using a green→red gradient.

**Endpoint:** `POST /api/v1/xai/explain`

---

## D3 — Gamified Technique Lessons

**Files:** `services/game-service/src/routes/lesson.routes.ts`,
`src/services/lesson.service.ts`, `services/game-service/src/data/lessons.ts`

15 lessons defined as static data (technique name, description, XP reward,
badge ID, step count).  Progress is tracked in the `LessonProgress` and
`UserBadge` Prisma tables.  Completing a lesson emits a `lesson_completed`
(and optionally `badge_earned`) activity feed event.

Mobile screens: `LessonsScreen` (list with XP progress bar) and
`LessonDetailScreen` (step-by-step interactive walkthrough).

**Endpoints:** `GET /api/lessons`, `GET /api/lessons/:id`,
`POST /api/lessons/:id/progress`, `POST /api/lessons/:id/complete`

---

## D4 — Newbie Onboarding

**Files:** `services/game-service/src/routes/onboarding.routes.ts`,
`src/services/onboarding.service.ts`

Nine-step interactive onboarding flow.  Progress is stored in
`OnboardingProgress`.  The mobile `OnboardingScreen` renders each step as a
full-screen card; the flow can be skipped and resumed later.

**Endpoints:** `GET /api/onboarding/status`, `POST /api/onboarding/step`,
`POST /api/onboarding/complete`, `POST /api/onboarding/skip`

---

## D5 — GAN Puzzle Generation

**Files:** `services/ml-service/app/routers/gan.py`, `app/ml/gan.py`,
`app/services/gan_service.py`, `ml/scripts/train_gan.py`

WGAN-GP architecture:

- Generator: latent vector (64-dim) + difficulty one-hot → 9×9 grid logits
- Critic: 9×9 grid → scalar Wasserstein distance
- Post-processing: argmax → backtracking repair → unique-solution guarantee
- MLflow experiment tracking for loss curves and FID scores

The game-service proxies GAN generation requests to ml-service at
`POST /api/v1/gan/generate`.  The puzzle is returned as a `Cell[][]` grid
identical in shape to engine-generated puzzles and stored in Postgres.

**Endpoint (game-service):** `POST /api/puzzles/generate-gan`
**Endpoint (ml-service):** `POST /api/v1/gan/generate`

---

## D6 — Embeddings & Semantic Search

**Files:** `services/ml-service/app/routers/semantic_search.py`,
`app/ml/puzzle_embeddings.py`, `app/ml/user_embeddings.py`,
`app/services/semantic_search_service.py`, `ml/scripts/index_puzzles.py`

Two Qdrant collections:

| Collection | Vectors | Distance | Contents |
|---|---|---|---|
| `puzzles` | 384-dim | COSINE | Puzzle feature embeddings |
| `users` | 384-dim | COSINE | User preference vectors |
| `techniques` | 384-dim | COSINE | Technique documents (seeded by seed_techniques.py) |

Search types proxied through `POST /api/puzzles/search` on game-service:

| `type` | Description |
|---|---|
| `similar` | Puzzles similar to a given `puzzle_id` |
| `for-user` | Personalised recommendations for a `user_id` |
| `by-technique` | Puzzles that exercise a named technique |
| `similar-features` | Puzzles matching a feature description (difficulty + clue_count + techniques) |

---

## D7 — Friends System & Social Layer

**Files:** `services/game-service/src/routes/friend.routes.ts`,
`src/services/friend.service.ts`

Prisma models: `Friendship` (status: pending | accepted | declined | blocked),
`ActivityFeed` (userId, actorId, type, payload).

Activity fan-out: when a puzzle is completed or a lesson/badge is awarded,
`emitActivity()` fans out a feed entry to every accepted friend of the actor
via `createMany`.

Mobile screens: `FriendsScreen` (3-tab hub: Friends / Requests / Leaderboard)
and `ActivityFeedScreen` (cursor-paginated feed with pull-to-refresh).

**Endpoints:** `POST /api/friends/request`, `POST /api/friends/:id/accept`,
`POST /api/friends/:id/decline`, `POST /api/friends/:id/block`,
`GET /api/friends`, `GET /api/friends/pending`,
`GET /api/friends/feed`, `GET /api/friends/leaderboard`

---

## D8 — Platform Hardening

### Kubernetes / Helm (v0.4.0)

Chart at `infra/helm/sudoku-ultra/`.  New templates added in Phase 4:

| Template | Resource |
|---|---|
| `nginx-deployment.yaml` + `nginx-configmap.yaml` | Nginx API gateway Deployment + ConfigMap |
| `nginx-service.yaml` | LoadBalancer Service (port 80/443) |
| `ollama-deployment.yaml` | Ollama Deployment + PVC |
| `ollama-service.yaml` | ClusterIP Service (port 11434) |
| `hpa.yaml` | HorizontalPodAutoscaler for all services |
| `pdb.yaml` | PodDisruptionBudget for all services |
| `qdrant-statefulset.yaml` + `qdrant-service.yaml` | Qdrant StatefulSet |
| `jaeger.yaml` | Jaeger all-in-one Deployment |

Per-env overrides: `values.prod.yaml`, `values.staging.yaml`.

### Terraform (EKS)

Modules at `infra/terraform/`: VPC, EKS cluster, RDS (Postgres), ElastiCache
(Redis), ECR repositories.  State stored in S3 + DynamoDB lock.

### ArgoCD (GitOps)

Two Applications defined in `infra/argocd/application.yaml`:
- `sudoku-ultra` → `main` branch → `sudoku-ultra` namespace
- `sudoku-ultra-staging` → `develop` branch → `sudoku-ultra-staging` namespace

CI updates `image.tag` in `values.yaml` and triggers ArgoCD sync after each
successful Docker push.

### Vault

Policy at `infra/vault/policy.hcl`.  Setup script at `infra/vault/setup.sh`.
Vault agent sidecar injection enabled in `values.prod.yaml` via
`vault.enabled: true`.

### Observability

- **Jaeger** — distributed tracing (all services instrument via OpenTelemetry)
- **Loki** — log aggregation (deployed as sub-chart)
- **Prometheus** — metrics scraping (annotations on all pods)

### Security

- **OWASP ZAP** — weekly API scan + on push to main (`.github/workflows/security.yml`)
- **Trivy** — container image vulnerability scan for all three images
- **npm audit / pip-audit / govulncheck** — dependency audits on every CI run
- **cosign** — keyless OIDC image signing after every Docker push

### Load Testing

`k6/` scripts: `smoke.js` (post-deploy gate), `game.js` (puzzle lifecycle),
`friends.js` (social endpoints), `ml.js` (inference latency).

### Contract Testing

Pact consumer contracts in `pact/consumer/game-api.pact.test.ts`.  Provider
verification in `pact/provider/game-service.verify.test.ts` backed by real
Prisma state seeding via `/_pact/provider-states` (registered only when
`NODE_ENV=test`).
