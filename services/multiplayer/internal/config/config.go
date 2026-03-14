package config

import (
	"os"
	"strconv"
	"time"
)

// Config holds all runtime configuration for the multiplayer service.
type Config struct {
	Port            string
	GameServiceURL  string
	BotServiceURL   string // ml-service endpoint for bot moves
	MLServiceURL    string // ml-service base URL (used for moderation, etc.)
	RedisURL        string
	JWTSecret       string
	InternalSecret  string // shared secret for service-to-service calls
	MaxRoomPlayers  int
	CountdownSecs   int
	ReconnectWindow time.Duration
	MatchmakeQueue  string // Redis key for public matchmaking queue
	LogLevel        string
}

// BotDelayRange returns the [min, max] delay in milliseconds for a given bot tier.
func (c *Config) BotDelayRange(tier string) (minMs, maxMs int) {
	switch tier {
	case "hard":
		return 100, 300
	case "medium":
		return 200, 500
	default: // easy
		return 500, 2000
	}
}

// Load reads configuration from environment variables with sensible defaults.
func Load() *Config {
	return &Config{
		Port:            getEnv("PORT", "3002"),
		GameServiceURL:  getEnv("GAME_SERVICE_URL", "http://game-service:3001"),
		BotServiceURL:   getEnv("BOT_SERVICE_URL", "http://ml-service:8000"),
		MLServiceURL:    getEnv("ML_SERVICE_URL", "http://ml-service:8000"),
		RedisURL:        getEnv("REDIS_URL", "redis://localhost:6379"),
		JWTSecret:       getEnv("JWT_SECRET", "dev-secret-change-in-production"),
		InternalSecret:  getEnv("INTERNAL_SECRET", "dev-internal-secret-change-in-production"),
		MaxRoomPlayers:  getEnvInt("MAX_ROOM_PLAYERS", 2),
		CountdownSecs:   getEnvInt("COUNTDOWN_SECS", 3),
		ReconnectWindow: getEnvDuration("RECONNECT_WINDOW_SECS", 30) * time.Second,
		MatchmakeQueue:  getEnv("MATCHMAKE_QUEUE_KEY", "multiplayer:matchmaking"),
		LogLevel:        getEnv("LOG_LEVEL", "info"),
	}
}

func getEnv(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}

func getEnvInt(key string, fallback int) int {
	if v := os.Getenv(key); v != "" {
		if n, err := strconv.Atoi(v); err == nil {
			return n
		}
	}
	return fallback
}

func getEnvDuration(key string, fallbackSecs int) time.Duration {
	if v := os.Getenv(key); v != "" {
		if n, err := strconv.Atoi(v); err == nil {
			return time.Duration(n)
		}
	}
	return time.Duration(fallbackSecs)
}
