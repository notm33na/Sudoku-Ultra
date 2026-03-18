"""
vault_client.py — HashiCorp Vault client for ml-service.

Reads secrets from Vault via the HTTP API using Kubernetes auth.
Falls back gracefully when Vault is not configured (dev / Vault-disabled env).

Usage:
    from app.services.vault_client import vault_client
    secrets = await vault_client.get_ml_service_secrets()

Required env vars (when vault.enabled=true in Helm):
    VAULT_ADDR            — e.g. https://vault.example.com
    VAULT_ROLE            — Kubernetes auth role (e.g. sudoku-ultra)
    VAULT_AUTH_PATH       — auth mount path (default: auth/kubernetes)
    VAULT_SA_TOKEN_FILE   — path to SA JWT
                            (default: /var/run/secrets/kubernetes.io/serviceaccount/token)
"""

from __future__ import annotations

import os
import time
import logging
from dataclasses import dataclass
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

_VAULT_ADDR        = os.getenv("VAULT_ADDR")
_VAULT_ROLE        = os.getenv("VAULT_ROLE", "sudoku-ultra")
_VAULT_AUTH_PATH   = os.getenv("VAULT_AUTH_PATH", "auth/kubernetes")
_SA_TOKEN_FILE     = os.getenv(
    "VAULT_SA_TOKEN_FILE",
    "/var/run/secrets/kubernetes.io/serviceaccount/token",
)
_ML_SERVICE_PATH   = "secret/data/sudoku-ultra/ml-service"
_TOKEN_TTL_SECONDS = 3600  # re-authenticate after 1 h


@dataclass
class MLServiceSecrets:
    database_url: str
    qdrant_api_key: str
    sentry_dsn: str
    pii_hmac_secret: str


class VaultClient:
    """Minimal async Vault client backed by httpx."""

    def __init__(self) -> None:
        self._token: Optional[str] = None
        self._token_expiry: float = 0.0

    # ── Public helpers ────────────────────────────────────────────────────────

    def is_enabled(self) -> bool:
        """Return True when Vault is configured in this environment."""
        return bool(_VAULT_ADDR)

    async def read_secret(self, path: str) -> dict[str, str]:
        """Read a KV v2 secret path; returns the ``data.data`` map."""
        token = await self._authenticate()
        url   = f"{_VAULT_ADDR}/v1/{path}"

        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url, headers={"X-Vault-Token": token})

        if not resp.is_success:
            raise RuntimeError(
                f"[Vault] Read {path} failed ({resp.status_code}): {resp.text}"
            )

        return resp.json()["data"]["data"]

    async def get_ml_service_secrets(self) -> MLServiceSecrets:
        """Fetch ml-service secrets; falls back to env vars when Vault is off."""
        if not self.is_enabled():
            return MLServiceSecrets(
                database_url    = os.getenv("DATABASE_URL", ""),
                qdrant_api_key  = os.getenv("QDRANT_API_KEY", ""),
                sentry_dsn      = os.getenv("SENTRY_DSN", ""),
                pii_hmac_secret = os.getenv("PII_HMAC_SECRET", ""),
            )

        secrets = await self.read_secret(_ML_SERVICE_PATH)
        return MLServiceSecrets(
            database_url    = secrets.get("database_url", ""),
            qdrant_api_key  = secrets.get("qdrant_api_key", ""),
            sentry_dsn      = secrets.get("sentry_dsn", ""),
            pii_hmac_secret = secrets.get("pii_hmac_secret", ""),
        )

    # ── Private ───────────────────────────────────────────────────────────────

    async def _authenticate(self) -> str:
        now = time.monotonic()
        if self._token and now < self._token_expiry:
            return self._token

        try:
            with open(_SA_TOKEN_FILE) as fh:
                sa_jwt = fh.read().strip()
        except OSError as exc:
            raise RuntimeError(
                f"[Vault] Cannot read SA token at {_SA_TOKEN_FILE}: {exc}"
            ) from exc

        url  = f"{_VAULT_ADDR}/v1/{_VAULT_AUTH_PATH}/login"
        body = {"role": _VAULT_ROLE, "jwt": sa_jwt}

        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(url, json=body)

        if not resp.is_success:
            raise RuntimeError(
                f"[Vault] Auth failed ({resp.status_code}): {resp.text}"
            )

        self._token        = resp.json()["auth"]["client_token"]
        self._token_expiry = now + _TOKEN_TTL_SECONDS
        logger.info("[Vault] Authenticated (token cached for %ds)", _TOKEN_TTL_SECONDS)
        return self._token  # type: ignore[return-value]


vault_client = VaultClient()
