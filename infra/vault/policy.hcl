# ──────────────────────────────────────────────────────────────────────────────
# Vault Policy — sudoku-ultra
#
# Apply with:
#   vault policy write sudoku-ultra infra/vault/policy.hcl
# ──────────────────────────────────────────────────────────────────────────────

# ── Game service secrets ──────────────────────────────────────────────────────
path "secret/data/sudoku-ultra/game-service" {
  capabilities = ["read"]
}

path "secret/metadata/sudoku-ultra/game-service" {
  capabilities = ["read", "list"]
}

# ── ML service secrets ────────────────────────────────────────────────────────
path "secret/data/sudoku-ultra/ml-service" {
  capabilities = ["read"]
}

path "secret/metadata/sudoku-ultra/ml-service" {
  capabilities = ["read", "list"]
}

# ── Multiplayer secrets ───────────────────────────────────────────────────────
path "secret/data/sudoku-ultra/multiplayer" {
  capabilities = ["read"]
}

path "secret/metadata/sudoku-ultra/multiplayer" {
  capabilities = ["read", "list"]
}

# ── Shared platform secrets ───────────────────────────────────────────────────
path "secret/data/sudoku-ultra/shared" {
  capabilities = ["read"]
}

path "secret/metadata/sudoku-ultra/shared" {
  capabilities = ["read", "list"]
}

# ── Database credentials (dynamic secrets via database engine) ────────────────
path "database/creds/sudoku-ultra-app" {
  capabilities = ["read"]
}

# ── PKI (TLS certificates) ────────────────────────────────────────────────────
path "pki/issue/sudoku-ultra" {
  capabilities = ["create", "update"]
}
