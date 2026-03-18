# Contributing to Sudoku Ultra

Welcome. This guide covers everything you need to get a development environment running, understand the codebase, and contribute code that passes CI.

---

## Table of contents

1. [Prerequisites](#prerequisites)
2. [Local setup](#local-setup)
3. [Project structure](#project-structure)
4. [Running services](#running-services)
5. [Testing](#testing)
6. [Code standards](#code-standards)
7. [Branch strategy](#branch-strategy)
8. [Pull request process](#pull-request-process)
9. [Environment variables](#environment-variables)
10. [Secrets in development](#secrets-in-development)
11. [Debugging tips](#debugging-tips)
12. [Architecture overview](#architecture-overview)

---

## Prerequisites

| Tool | Version | Install |
|---|---|---|
| Node.js | >= 20.x | [nodejs.org](https://nodejs.org) or `nvm use` |
| npm | >= 10.x | Bundled with Node.js |
| Go | >= 1.22 | [go.dev](https://go.dev) |
| Python | >= 3.11 | [python.org](https://python.org) or `pyenv` |
| Docker + Docker Compose | >= 24 + v2 | [docker.com](https://docker.com) |
| kubectl | >= 1.29 | Only needed for staging/prod access |
| Helm | >= 3.15 | Only needed for k8s deployments |

---

## Local setup

```bash
# 1. Clone
git clone https://github.com/your-org/sudoku-ultra.git
cd sudoku-ultra

# 2. Install Node.js dependencies (all workspaces)
npm install

# 3. Build shared packages first (required by services)
npx turbo build --filter=@sudoku-ultra/shared-types
npx turbo build --filter=@sudoku-ultra/sudoku-engine

# 4. Start infrastructure (PostgreSQL, MongoDB, Redis, Qdrant, Kafka)
cd infra && docker compose up -d && cd ..

# 5. Copy environment files
cp services/game-service/.env.example services/game-service/.env
cp services/ml-service/.env.example services/ml-service/.env
cp services/multiplayer/.env.example services/multiplayer/.env

# 6. Run database migrations
cd services/game-service && npx prisma migrate dev && cd ../..

# 7. Install Python dependencies (ml-service)
cd services/ml-service
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cd ../..

# 8. Start all services in dev mode
npx turbo dev
```

Services will be available at:

| Service | URL |
|---|---|
| game-service | http://localhost:3001 |
| multiplayer | http://localhost:3002 |
| ml-service | http://localhost:3003 |
| notifications | http://localhost:3004 |
| web-admin | http://localhost:4200 |

---

## Project structure

```
sudoku-ultra/
├── apps/
│   ├── mobile/              # React Native (Expo) — iOS + Android
│   └── web-admin/           # Angular admin dashboard
├── services/
│   ├── game-service/        # Node.js + Express + Prisma — main API
│   ├── multiplayer/         # Go + WebSocket — real-time rooms
│   ├── ml-service/          # Python + FastAPI — ML inference
│   └── notifications/       # Node.js + Express — push notifications
├── packages/
│   ├── shared-types/        # Shared TypeScript type definitions
│   └── sudoku-engine/       # Core puzzle logic (solver, validator, generator)
├── infra/
│   ├── docker-compose.yml   # Local dev infrastructure
│   ├── terraform/           # AWS infrastructure (EKS, RDS, ElastiCache, S3)
│   ├── helm/                # Helm chart for k8s deployment
│   ├── argocd/              # ArgoCD application manifests
│   ├── backup/              # Backup scripts (PostgreSQL, MongoDB → MinIO)
│   └── otel-collector/      # OTel Collector config
├── k6/
│   ├── config.js            # Shared options and env helpers
│   └── scripts/             # Load test scripts
├── ml/
│   ├── models/              # Trained model artifacts
│   ├── notebooks/           # Jupyter exploration notebooks
│   └── pipelines/           # Airflow DAGs
├── docs/
│   ├── architecture/        # Architecture decision records
│   ├── api/                 # API documentation
│   ├── deployment/          # Deployment guides + runbooks
│   ├── mlops/               # ML model runbooks + SLAs
│   ├── operations/          # On-call runbooks
│   └── development/         # This file and developer guides
└── .github/
    └── workflows/           # GitHub Actions (ci, security, nightly, release)
```

---

## Running services

### Run a specific service

```bash
# game-service only
npx turbo dev --filter=@sudoku-ultra/game-service

# ml-service only
cd services/ml-service && uvicorn app.main:app --reload --port 3003

# multiplayer only
cd services/multiplayer && go run ./cmd/server
```

### Run all services

```bash
npx turbo dev
```

### Restart infrastructure

```bash
cd infra
docker compose down
docker compose up -d
```

---

## Testing

### Run all tests

```bash
npm test
# or
npx turbo test
```

### Run tests for a specific service

```bash
# game-service
cd services/game-service && npm test

# ml-service
cd services/ml-service && pytest

# multiplayer
cd services/multiplayer && go test ./...

# sudoku-engine
cd packages/sudoku-engine && npm test
```

### Run tests with coverage

```bash
# game-service
cd services/game-service && npm run test:coverage

# ml-service
cd services/ml-service && pytest --cov=app --cov-report=html
```

### Run k6 load tests locally

```bash
# Requires k6 installed: https://k6.io/docs/getting-started/installation/
k6 run --env BASE_URL=http://localhost:3001 k6/scripts/smoke.js
k6 run --env BASE_URL=http://localhost:3001 k6/scripts/game.js
```

### Run Edge AI benchmarks (mobile)

```bash
cd apps/mobile
npx jest src/benchmarks/edgeAI.benchmark.ts --testTimeout=60000
```

---

## Code standards

### TypeScript (game-service, shared-types, sudoku-engine, mobile)

- Strict mode enabled (`"strict": true` in tsconfig)
- ESLint + Prettier enforced via pre-commit hook
- Import paths: use `@sudoku-ultra/<package>` aliases, not relative cross-service imports
- No `any` types — use `unknown` and narrow with type guards
- Errors: always use typed error classes; never `throw 'string'`

```bash
npm run lint        # check
npm run lint:fix    # auto-fix
npm run format      # prettier
```

### Python (ml-service)

- `ruff` for linting, `black` for formatting (configured in `pyproject.toml`)
- Type annotations required on all public functions
- Async endpoints in FastAPI: use `async def` + `httpx.AsyncClient` for outbound HTTP

```bash
cd services/ml-service
ruff check .
black .
```

### Go (multiplayer)

- `gofmt` and `golint` enforced
- All exported functions must have godoc comments
- Use `context.Context` as first parameter for all functions making network calls
- Errors: always wrap with `fmt.Errorf("...: %w", err)` for stack context

```bash
cd services/multiplayer
go fmt ./...
go vet ./...
golint ./...
```

### General rules

- No secrets in code or committed `.env` files — use `.env.example` templates
- No console.log/print in production code paths — use the structured logger
- All new endpoints need a corresponding test (unit + integration)
- Database migrations: always forward-only (no rollback migrations); tested locally before PR

---

## Branch strategy

```
main ──────────────────────────────────────────────────► (production-ready)
  └── feature/<ticket-id>-short-description
  └── fix/<ticket-id>-short-description
  └── chore/<ticket-id>-short-description
  └── release/vX.Y.Z   (release branches, cut from main)
```

**Rules:**
- Branch from `main`, PR back to `main`
- Branch names must match the pattern above (enforced by branch protection)
- `main` is protected: no direct push, required status checks, 1 required reviewer
- Delete branch after merge
- Release branches: `release/vX.Y.Z` — only patch fixes allowed; merge back to main after cut

---

## Pull request process

### Before opening a PR

1. Run the full test suite locally: `npm test && npx turbo build`
2. Run the linter: `npm run lint`
3. Ensure your branch is up to date with `main`: `git rebase origin/main`
4. Self-review your diff — check for debug logs, commented-out code, hardcoded values

### PR requirements

All of the following must pass before merge:

| Check | What it validates |
|---|---|
| `lint` | ESLint / ruff / gofmt |
| `test` | Unit tests across all services |
| `build` | TypeScript compilation, Go build, Python import check |
| `security / CodeQL` | SAST scan (JS/TS + Python) |
| `security / trivy-images` | Container image vulnerability scan |

### PR description template

```markdown
## What
<1–3 sentence summary of what changed>

## Why
<Why this change is needed — link to issue or context>

## How to test
<Steps a reviewer can follow to verify the change works>

## Checklist
- [ ] Tests added/updated
- [ ] No secrets or debug code
- [ ] Migrations are forward-only (if applicable)
- [ ] Documentation updated (if applicable)
```

### Review SLA

- Authors respond to review comments within 1 business day
- Reviewers complete reviews within 1 business day of assignment
- Stale PRs (no activity > 5 days) are labelled `stale` and may be closed

---

## Environment variables

Each service has a `.env.example` at its root. Copy to `.env` for local development.

### game-service key variables

| Variable | Purpose | Example |
|---|---|---|
| `DATABASE_URL` | PostgreSQL connection string | `postgresql://postgres:password@localhost:5432/sudoku_ultra` |
| `REDIS_URL` | Redis connection string | `redis://localhost:6379` |
| `JWT_SECRET` | JWT signing secret (min 32 chars) | `dev-secret-change-in-prod` |
| `JWT_REFRESH_SECRET` | Refresh token secret | `dev-refresh-secret` |
| `VAULT_ADDR` | Vault address (leave blank to use env vars) | `http://localhost:8200` |
| `SENTRY_DSN` | Sentry error reporting (optional) | `https://...@sentry.io/...` |
| `NODE_ENV` | Environment | `development` |

### ml-service key variables

| Variable | Purpose | Example |
|---|---|---|
| `DATABASE_URL` | MongoDB connection string | `mongodb://localhost:27017/sudoku_ultra` |
| `QDRANT_URL` | Qdrant vector DB URL | `http://localhost:6333` |
| `MLFLOW_TRACKING_URI` | MLflow server URL | `http://localhost:5000` |
| `VAULT_ADDR` | Vault address (optional) | `http://localhost:8200` |

### multiplayer key variables

| Variable | Purpose | Example |
|---|---|---|
| `DATABASE_URL` | PostgreSQL connection string | `postgresql://postgres:password@localhost:5432/sudoku_ultra` |
| `REDIS_URL` | Redis connection string | `redis://localhost:6379` |
| `JWT_SECRET` | JWT validation secret (must match game-service) | `dev-secret-change-in-prod` |
| `PORT` | WebSocket server port | `3002` |
| `VAULT_ADDR` | Vault address (optional) | `http://localhost:8200` |

---

## Secrets in development

**Never commit real secrets.** The `.env.example` files contain placeholder values.

For local development, use the placeholder values in `.env.example` — they work against the Docker Compose infrastructure stack.

For staging/production, secrets are managed by HashiCorp Vault. The Vault agent sidecar injects them into each pod at startup. See [Phase 5 Architecture](../architecture/phase5.md#vault-secret-injection) for details.

**Pre-commit hook** runs `git secrets --scan` to prevent accidental secret commits. If you get a false positive, add the pattern to `.gitallowed`.

---

## Debugging tips

### game-service (Node.js)

```bash
# Debug mode with inspector
cd services/game-service
node --inspect -r ts-node/register src/index.ts
# Open chrome://inspect in Chrome
```

### ml-service (Python)

```bash
# Attach debugger
cd services/ml-service
python -m debugpy --listen 5678 -m uvicorn app.main:app --reload --port 3003
# Attach VS Code debugger to port 5678
```

### multiplayer (Go)

```bash
# Use Delve
cd services/multiplayer
dlv debug ./cmd/server -- --port 3002
```

### Tracing a request end-to-end

All services emit OpenTelemetry traces. To trace a request:

1. Start the OTel Collector and Jaeger: `docker compose -f infra/docker-compose.yml up otel-collector jaeger`
2. Make the request
3. Open Jaeger UI at http://localhost:16686
4. Search by service name and time range

### Checking rate limits locally

The Express rate limiters are bypassed when `NODE_ENV=test`. For manual testing of rate limit behaviour:

```bash
# Temporarily set NODE_ENV=development (not test) and make rapid requests
for i in {1..15}; do curl -s -o /dev/null -w "%{http_code}\n" \
  -X POST http://localhost:3001/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"x@y.com","password":"wrong"}'; done
# You should see 401s followed by 429s
```

---

## Architecture overview

Full architecture diagrams are in:

- [Phase 5 Architecture](../architecture/phase5.md) — current production architecture (all phases)
- [Phase 4 Architecture](../architecture/phase4.md) — detail on gamification, onboarding, edge AI

**Key design decisions:**

| Decision | Rationale |
|---|---|
| Monorepo (Turborepo) | Shared types enforced at compile time; atomic cross-service changes |
| Go for multiplayer | Low-latency goroutines; native WebSocket support; minimal memory per connection |
| FastAPI for ML | Async Python; pydantic validation; integrates with PyTorch/scikit-learn naturally |
| Vault for secrets | Zero plaintext secrets in k8s; short-lived tokens; audit trail |
| ArgoCD GitOps | Declarative; all cluster state in Git; easy rollback |
| OTel Collector | Vendor-neutral telemetry; single egress point; can swap backends without code changes |
| ONNX/TFLite for edge | Portable across iOS/Android; smaller bundle than full PyTorch Mobile |
