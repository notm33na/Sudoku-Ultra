#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────────────
# Vault setup script — run once per environment to configure Kubernetes auth,
# the sudoku-ultra policy, and seed initial secrets.
#
# Prerequisites:
#   vault CLI authenticated with a root/admin token
#   kubectl access to the target cluster
#
# Usage:
#   VAULT_ADDR=https://vault.example.com \
#   VAULT_TOKEN=<root-token> \
#   KUBE_NAMESPACE=sudoku-ultra \
#   bash infra/vault/setup.sh
# ──────────────────────────────────────────────────────────────────────────────

set -euo pipefail

NAMESPACE="${KUBE_NAMESPACE:-sudoku-ultra}"
SA_NAME="sudoku-ultra"
POLICY_NAME="sudoku-ultra"
ROLE_NAME="sudoku-ultra"

echo "==> Enabling Kubernetes auth method..."
vault auth enable kubernetes 2>/dev/null || echo "  Already enabled."

echo "==> Configuring Kubernetes auth..."
KUBE_HOST=$(kubectl config view --minify -o jsonpath='{.clusters[0].cluster.server}')
SA_JWT=$(kubectl get secret \
  "$(kubectl get serviceaccount "${SA_NAME}" -n "${NAMESPACE}" \
    -o jsonpath='{.secrets[0].name}')" \
  -n "${NAMESPACE}" -o jsonpath='{.data.token}' | base64 --decode)
KUBE_CA=$(kubectl get cm kube-root-ca.crt -n kube-system -o jsonpath='{.data.ca\.crt}')

vault write auth/kubernetes/config \
  token_reviewer_jwt="${SA_JWT}" \
  kubernetes_host="${KUBE_HOST}" \
  kubernetes_ca_cert="${KUBE_CA}"

echo "==> Writing policy..."
vault policy write "${POLICY_NAME}" infra/vault/policy.hcl

echo "==> Creating Kubernetes role..."
vault write "auth/kubernetes/role/${ROLE_NAME}" \
  bound_service_account_names="${SA_NAME}" \
  bound_service_account_namespaces="${NAMESPACE}" \
  policies="${POLICY_NAME}" \
  ttl=1h

echo "==> Enabling KV v2 secrets engine..."
vault secrets enable -path=secret kv-v2 2>/dev/null || echo "  Already enabled."

echo "==> Seeding placeholder secrets (replace values in production)..."
vault kv put secret/sudoku-ultra/shared \
  jwt_secret="REPLACE_ME" \
  internal_secret="REPLACE_ME"

vault kv put secret/sudoku-ultra/game-service \
  database_url="REPLACE_ME" \
  sentry_dsn="REPLACE_ME"

vault kv put secret/sudoku-ultra/ml-service \
  huggingface_token="REPLACE_ME" \
  sentry_dsn="REPLACE_ME"

vault kv put secret/sudoku-ultra/multiplayer \
  sentry_dsn="REPLACE_ME"

echo "==> Done. Update placeholder values before deploying to production."
