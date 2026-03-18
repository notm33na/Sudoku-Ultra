// Package vault provides a minimal HashiCorp Vault client for the multiplayer
// service. It authenticates via Kubernetes service-account JWT and reads KV v2
// secrets. Falls back to environment variables when Vault is not configured.
//
// Required env vars (when vault.enabled=true in Helm):
//
//	VAULT_ADDR           — e.g. https://vault.example.com
//	VAULT_ROLE           — Kubernetes auth role (e.g. sudoku-ultra)
//	VAULT_AUTH_PATH      — auth mount path (default: auth/kubernetes)
//	VAULT_SA_TOKEN_FILE  — SA JWT file path
//	                       (default: /var/run/secrets/kubernetes.io/serviceaccount/token)
package vault

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"sync"
	"time"
)

const (
	defaultAuthPath   = "auth/kubernetes"
	defaultSAFile     = "/var/run/secrets/kubernetes.io/serviceaccount/token"
	defaultRole       = "sudoku-ultra"
	multiplayerPath   = "secret/data/sudoku-ultra/multiplayer"
	tokenTTL          = time.Hour
)

// MultiplayerSecrets holds secrets for the multiplayer service.
type MultiplayerSecrets struct {
	JWTSecret    string
	DatabaseURL  string
	RedisURL     string
	SentryDSN    string
}

// Client is a minimal Vault HTTP client.
type Client struct {
	addr       string
	role       string
	authPath   string
	saTokenFile string
	httpClient *http.Client

	mu          sync.Mutex
	token       string
	tokenExpiry time.Time
}

// New creates a Client from environment variables.
// Returns nil and false if VAULT_ADDR is not set (Vault disabled).
func New() (*Client, bool) {
	addr := os.Getenv("VAULT_ADDR")
	if addr == "" {
		return nil, false
	}
	role := os.Getenv("VAULT_ROLE")
	if role == "" {
		role = defaultRole
	}
	authPath := os.Getenv("VAULT_AUTH_PATH")
	if authPath == "" {
		authPath = defaultAuthPath
	}
	saFile := os.Getenv("VAULT_SA_TOKEN_FILE")
	if saFile == "" {
		saFile = defaultSAFile
	}
	return &Client{
		addr:        addr,
		role:        role,
		authPath:    authPath,
		saTokenFile: saFile,
		httpClient:  &http.Client{Timeout: 10 * time.Second},
	}, true
}

// GetMultiplayerSecrets returns secrets for the multiplayer service.
// If the client is nil (Vault disabled), it falls back to env vars.
func GetMultiplayerSecrets(ctx context.Context, c *Client) (*MultiplayerSecrets, error) {
	if c == nil {
		return &MultiplayerSecrets{
			JWTSecret:   getEnvOr("JWT_SECRET", "dev-secret-change-in-production"),
			DatabaseURL: getEnvOr("DATABASE_URL", ""),
			RedisURL:    getEnvOr("REDIS_URL", "redis://localhost:6379"),
			SentryDSN:   getEnvOr("SENTRY_DSN", ""),
		}, nil
	}

	data, err := c.ReadSecret(ctx, multiplayerPath)
	if err != nil {
		return nil, err
	}
	return &MultiplayerSecrets{
		JWTSecret:   stringVal(data, "jwt_secret"),
		DatabaseURL: stringVal(data, "database_url"),
		RedisURL:    stringVal(data, "redis_url"),
		SentryDSN:   stringVal(data, "sentry_dsn"),
	}, nil
}

// ReadSecret reads a KV v2 path and returns the data.data map.
func (c *Client) ReadSecret(ctx context.Context, path string) (map[string]string, error) {
	token, err := c.authenticate(ctx)
	if err != nil {
		return nil, err
	}

	url := fmt.Sprintf("%s/v1/%s", c.addr, path)
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
	if err != nil {
		return nil, err
	}
	req.Header.Set("X-Vault-Token", token)

	resp, err := c.httpClient.Do(req)
	if err != nil {
		return nil, fmt.Errorf("vault read %s: %w", path, err)
	}
	defer resp.Body.Close()

	body, _ := io.ReadAll(resp.Body)
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("vault read %s: status %d: %s", path, resp.StatusCode, body)
	}

	var payload struct {
		Data struct {
			Data map[string]string `json:"data"`
		} `json:"data"`
	}
	if err := json.Unmarshal(body, &payload); err != nil {
		return nil, fmt.Errorf("vault read %s: unmarshal: %w", path, err)
	}
	return payload.Data.Data, nil
}

// authenticate returns a cached Vault client token, refreshing if expired.
func (c *Client) authenticate(ctx context.Context) (string, error) {
	c.mu.Lock()
	defer c.mu.Unlock()

	if c.token != "" && time.Now().Before(c.tokenExpiry) {
		return c.token, nil
	}

	saJWT, err := os.ReadFile(c.saTokenFile)
	if err != nil {
		return "", fmt.Errorf("vault: read SA token %s: %w", c.saTokenFile, err)
	}

	body, _ := json.Marshal(map[string]string{
		"role": c.role,
		"jwt":  string(bytes.TrimSpace(saJWT)),
	})

	url := fmt.Sprintf("%s/v1/%s/login", c.addr, c.authPath)
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, url,
		bytes.NewReader(body))
	if err != nil {
		return "", err
	}
	req.Header.Set("Content-Type", "application/json")

	resp, err := c.httpClient.Do(req)
	if err != nil {
		return "", fmt.Errorf("vault auth: %w", err)
	}
	defer resp.Body.Close()

	respBody, _ := io.ReadAll(resp.Body)
	if resp.StatusCode != http.StatusOK {
		return "", fmt.Errorf("vault auth failed (%d): %s", resp.StatusCode, respBody)
	}

	var authResp struct {
		Auth struct {
			ClientToken string `json:"client_token"`
		} `json:"auth"`
	}
	if err := json.Unmarshal(respBody, &authResp); err != nil {
		return "", fmt.Errorf("vault auth: unmarshal: %w", err)
	}

	c.token       = authResp.Auth.ClientToken
	c.tokenExpiry = time.Now().Add(tokenTTL)
	return c.token, nil
}

func getEnvOr(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}

func stringVal(m map[string]string, key string) string {
	return m[key]
}
