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
	RedisURL        string
	JWTSecret       string
	MaxRoomPlayers  int
	CountdownSecs   int
	ReconnectWindow time.Duration
	MatchmakeQueue  string // Redis key for public matchmaking queue
	LogLevel        string
}

// Load reads configuration from environment variables with sensible defaults.
func Load() *Config {
	return &Config{
		Port:            getEnv("PORT", "3002"),
		GameServiceURL:  getEnv("GAME_SERVICE_URL", "http://game-service:3001"),
		RedisURL:        getEnv("REDIS_URL", "redis://localhost:6379"),
		JWTSecret:       getEnv("JWT_SECRET", "dev-secret-change-in-production"),
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
