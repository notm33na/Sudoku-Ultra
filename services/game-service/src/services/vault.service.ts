/**
 * vault.service.ts — HashiCorp Vault client for game-service.
 *
 * Reads secrets from Vault via the HTTP API using Kubernetes auth.
 * Falls back gracefully when Vault is not configured (dev / Vault-disabled env).
 *
 * Usage:
 *   import { vaultService } from './vault.service';
 *   const secrets = await vaultService.getGameServiceSecrets();
 *
 * Required env vars (when vault.enabled=true in Helm):
 *   VAULT_ADDR       — e.g. https://vault.example.com
 *   VAULT_ROLE       — Kubernetes auth role (e.g. sudoku-ultra)
 *   VAULT_AUTH_PATH  — auth mount path (default: auth/kubernetes)
 *   VAULT_SA_TOKEN_FILE — path to SA JWT (default: /var/run/secrets/kubernetes.io/serviceaccount/token)
 */

import { readFileSync } from 'fs';

const VAULT_ADDR          = process.env.VAULT_ADDR;
const VAULT_ROLE          = process.env.VAULT_ROLE          ?? 'sudoku-ultra';
const VAULT_AUTH_PATH     = process.env.VAULT_AUTH_PATH     ?? 'auth/kubernetes';
const SA_TOKEN_FILE       = process.env.VAULT_SA_TOKEN_FILE ?? '/var/run/secrets/kubernetes.io/serviceaccount/token';
const GAME_SERVICE_PATH   = 'secret/data/sudoku-ultra/game-service';

interface VaultAuthResponse {
    auth: { client_token: string };
}

interface VaultKVResponse {
    data: { data: Record<string, string> };
}

interface GameServiceSecrets {
    jwtSecret: string;
    databaseUrl: string;
    sentryDsn: string;
}

class VaultService {
    private _token: string | null = null;
    private _tokenExpiry: number = 0;

    /** Returns true if Vault is configured in this environment. */
    isEnabled(): boolean {
        return Boolean(VAULT_ADDR);
    }

    /**
     * Authenticate to Vault using Kubernetes service account JWT.
     * Caches the client token until it expires (lease_duration - 60s buffer).
     */
    private async _authenticate(): Promise<string> {
        const now = Date.now();
        if (this._token && now < this._tokenExpiry) {
            return this._token;
        }

        let saJwt: string;
        try {
            saJwt = readFileSync(SA_TOKEN_FILE, 'utf8').trim();
        } catch {
            throw new Error(`[Vault] Cannot read SA token at ${SA_TOKEN_FILE}`);
        }

        const url  = `${VAULT_ADDR}/v1/${VAULT_AUTH_PATH}/login`;
        const body = JSON.stringify({ role: VAULT_ROLE, jwt: saJwt });

        const res = await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body,
        });

        if (!res.ok) {
            const text = await res.text();
            throw new Error(`[Vault] Auth failed (${res.status}): ${text}`);
        }

        const payload = (await res.json()) as VaultAuthResponse;
        this._token       = payload.auth.client_token;
        // Re-authenticate 60 s before expiry — Vault default lease is 768h but
        // we check on every call so this is a conservative safety margin only.
        this._tokenExpiry = now + 60 * 60 * 1000; // 1 h
        return this._token;
    }

    /**
     * Read a KV v2 secret from Vault.
     * Returns the `data.data` map or throws.
     */
    async readSecret(path: string): Promise<Record<string, string>> {
        const token = await this._authenticate();
        const url   = `${VAULT_ADDR}/v1/${path}`;

        const res = await fetch(url, {
            headers: { 'X-Vault-Token': token },
        });

        if (!res.ok) {
            const text = await res.text();
            throw new Error(`[Vault] Read ${path} failed (${res.status}): ${text}`);
        }

        const payload = (await res.json()) as VaultKVResponse;
        return payload.data.data;
    }

    /** Fetch game-service secrets and return typed object. */
    async getGameServiceSecrets(): Promise<GameServiceSecrets> {
        if (!this.isEnabled()) {
            return {
                jwtSecret:   process.env.JWT_SECRET   ?? '',
                databaseUrl: process.env.DATABASE_URL ?? '',
                sentryDsn:   process.env.SENTRY_DSN   ?? '',
            };
        }

        const secrets = await this.readSecret(GAME_SERVICE_PATH);
        return {
            jwtSecret:   secrets['jwt_secret']   ?? '',
            databaseUrl: secrets['database_url'] ?? '',
            sentryDsn:   secrets['sentry_dsn']   ?? '',
        };
    }
}

export const vaultService = new VaultService();
