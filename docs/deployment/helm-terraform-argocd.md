# Deployment Guide: Helm, Terraform, ArgoCD

## Prerequisites

| Tool | Version | Purpose |
|---|---|---|
| `terraform` | 1.8+ | Provision AWS infrastructure |
| `helm` | 3.15+ | Render and install Kubernetes charts |
| `kubectl` | 1.29+ | Interact with EKS cluster |
| `argocd` CLI | 2.10+ | Manage ArgoCD applications |
| `aws` CLI | 2.x | Authenticate with AWS |

---

## 1. Infrastructure — Terraform

### First-time setup

```bash
cd infra/terraform

# Copy and fill in the variables file
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars: set aws_region, cluster_name, db_password, etc.

# Initialise remote state (S3 bucket + DynamoDB table must exist)
terraform init \
  -backend-config="bucket=sudoku-ultra-tfstate" \
  -backend-config="key=prod/terraform.tfstate" \
  -backend-config="region=us-east-1"

terraform plan -out=tfplan
terraform apply tfplan
```

### What gets created

- **VPC** — 3 public + 3 private subnets across 3 AZs
- **EKS** — managed node group (general) + spot node group (ml, tainted `workload=ml`)
- **RDS** — PostgreSQL 16 Multi-AZ in private subnets
- **ElastiCache** — Redis 7 cluster in private subnets
- **ECR** — three repositories: `game-service`, `multiplayer`, `ml-service`

### Outputs

```bash
terraform output kubeconfig_command   # aws eks update-kubeconfig ...
terraform output rds_endpoint
terraform output redis_endpoint
terraform output ecr_game_service_url
```

---

## 2. Secrets — Vault

```bash
# One-time Vault setup (run once after cluster is up)
VAULT_ADDR=https://vault.sudoku-ultra.internal \
VAULT_TOKEN=<root-token> \
bash infra/vault/setup.sh
```

The script:
1. Enables the Kubernetes auth method
2. Creates the `sudoku-ultra` policy (`infra/vault/policy.hcl`)
3. Seeds placeholder secrets at `secret/data/sudoku-ultra/*`

Replace placeholders with real values:
```bash
vault kv put secret/sudoku-ultra/game-service \
  jwt_secret="$(openssl rand -hex 32)" \
  database_url="postgresql://..." \
  sentry_dsn="https://..."
```

---

## 3. Helm Chart

### Chart structure

```
infra/helm/sudoku-ultra/
├── Chart.yaml            # version 0.4.0, dependencies: postgresql, redis, loki-stack
├── values.yaml           # base defaults (dev-safe, no real secrets)
├── values.prod.yaml      # production overrides (committed, no secrets)
├── values.staging.yaml   # staging overrides (committed, no secrets)
└── templates/
    ├── _helpers.tpl
    ├── game-service-deployment.yaml
    ├── game-service-service.yaml
    ├── multiplayer-deployment.yaml
    ├── multiplayer-service.yaml
    ├── ml-service-deployment.yaml
    ├── ml-service-service.yaml
    ├── nginx-deployment.yaml
    ├── nginx-configmap.yaml
    ├── nginx-service.yaml
    ├── ollama-deployment.yaml
    ├── ollama-service.yaml
    ├── qdrant-statefulset.yaml
    ├── qdrant-service.yaml
    ├── jaeger.yaml
    ├── hpa.yaml
    ├── pdb.yaml
    ├── serviceaccount.yaml
    └── secrets.yaml
```

### Lint and dry-run

```bash
helm lint infra/helm/sudoku-ultra \
  --set global.jwtSecret=ci-secret \
  --set global.postgresUrl=postgresql://u:p@host/db

helm template sudoku-ultra infra/helm/sudoku-ultra \
  -f infra/helm/sudoku-ultra/values.yaml \
  -f infra/helm/sudoku-ultra/values.prod.yaml \
  --set global.jwtSecret=ci-secret \
  --set global.postgresUrl=postgresql://u:p@host/db \
  > /dev/null
```

### Manual install / upgrade

```bash
# Authenticate kubectl
aws eks update-kubeconfig --region us-east-1 --name sudoku-ultra

# Install (first time)
helm upgrade --install sudoku-ultra infra/helm/sudoku-ultra \
  -n sudoku-ultra --create-namespace \
  -f infra/helm/sudoku-ultra/values.yaml \
  -f infra/helm/sudoku-ultra/values.prod.yaml \
  --set global.jwtSecret="$JWT_SECRET" \
  --set global.postgresUrl="$DATABASE_URL" \
  --set global.redisUrl="$REDIS_URL" \
  --set global.sentryDsn="$SENTRY_DSN" \
  --set image.tag="sha-$(git rev-parse --short HEAD)"

# Check rollout
kubectl -n sudoku-ultra rollout status deployment/sudoku-ultra-game-service
kubectl -n sudoku-ultra rollout status deployment/sudoku-ultra-ml-service
```

---

## 4. ArgoCD (GitOps)

ArgoCD manages all production and staging deployments.  Direct `helm upgrade`
is only for emergencies — normal flow goes through Git.

### Initial ArgoCD setup

```bash
# Install ArgoCD into the cluster
kubectl create namespace argocd
kubectl apply -n argocd \
  -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml

# Apply the AppProject and Application manifests
kubectl apply -f infra/argocd/project.yaml -n argocd
kubectl apply -f infra/argocd/application.yaml -n argocd
```

### GitOps deploy flow

1. Developer merges PR to `main`.
2. CI builds and pushes Docker images to GHCR (tagged `sha-<short>`).
3. CI updates `image.tag` in `values.yaml` and commits `[skip ci]`.
4. ArgoCD detects the new commit (polling every 3 min or via webhook).
5. ArgoCD syncs: runs `helm template` + applies diff to the cluster.
6. k6 smoke test runs post-deploy to verify key endpoints.

### Manual sync

```bash
argocd app sync sudoku-ultra
argocd app sync sudoku-ultra-staging

# Watch sync status
argocd app get sudoku-ultra --watch
```

### Rollback

```bash
# List history
argocd app history sudoku-ultra

# Roll back to a specific revision
argocd app rollback sudoku-ultra <REVISION>
```

---

## 5. Environment Differences

| Setting | Staging | Production |
|---|---|---|
| Replicas (game-service) | 1 | 3 |
| HPA min replicas | 1 | 3 |
| Vault | disabled (CI --set) | enabled (agent sidecar) |
| Ollama | enabled | disabled (HuggingFace) |
| nginx service type | ClusterIP | LoadBalancer |
| ArgoCD branch | `develop` | `main` |
| Namespace | `sudoku-ultra-staging` | `sudoku-ultra` |

---

## 6. Seed Qdrant Techniques (one-time)

The `techniques` Qdrant collection must be populated before the RAG tutor
works.  In docker-compose this is handled automatically by the `qdrant-seed`
init service.  In Kubernetes, run the seed script as a one-off Job:

```bash
kubectl -n sudoku-ultra run qdrant-seed \
  --image=python:3.11-slim \
  --restart=Never \
  --env="QDRANT_URL=http://qdrant:6333" \
  -- bash -c "
    pip install -q qdrant-client==1.10.1 sentence-transformers==3.1.1 &&
    python /scripts/seed_techniques.py --qdrant-url http://qdrant:6333 --reset
  "
# Monitor:
kubectl -n sudoku-ultra logs -f qdrant-seed
```

---

## 7. Troubleshooting

### ArgoCD shows OutOfSync but nothing changed

```bash
argocd app diff sudoku-ultra   # show what ArgoCD thinks changed
```
Often caused by HPA mutating `spec.replicas` — this is suppressed via
`ignoreDifferences` in `application.yaml`.

### Helm upgrade fails with "resource already exists"

```bash
helm -n sudoku-ultra get manifest sudoku-ultra | grep "kind: Secret"
# If secrets.yaml was applied manually, delete and let Helm manage it:
kubectl -n sudoku-ultra delete secret sudoku-ultra-secrets
helm upgrade sudoku-ultra ...
```

### ml-service OOMKilled

The ml-service node group uses `r6i.xlarge` instances (32 GiB RAM).  If the
pod is being OOMKilled, increase `mlService.resources.limits.memory` in
`values.prod.yaml` and push to trigger an ArgoCD sync.

### Qdrant search returns empty results

Run the seed job above to repopulate the `techniques` collection.  For the
`puzzles` collection, trigger a re-index:

```bash
# Index all puzzles (runs ml/scripts/index_puzzles.py)
kubectl -n sudoku-ultra run puzzle-index \
  --image=python:3.11-slim --restart=Never \
  -- python /scripts/index_puzzles.py
```
