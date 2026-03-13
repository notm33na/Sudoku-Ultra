package main

import (
	"context"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/go-chi/chi/v5"
	chimiddleware "github.com/go-chi/chi/v5/middleware"
	"github.com/prometheus/client_golang/prometheus/promhttp"
	"go.uber.org/zap"
	"go.uber.org/zap/zapcore"

	"github.com/sudoku-ultra/multiplayer/internal/config"
	"github.com/sudoku-ultra/multiplayer/internal/handlers"
	"github.com/sudoku-ultra/multiplayer/internal/hub"
	"github.com/sudoku-ultra/multiplayer/internal/models"
	"github.com/sudoku-ultra/multiplayer/internal/room"
)

func main() {
	cfg := config.Load()
	log := buildLogger(cfg.LogLevel)
	defer log.Sync()

	log.Info("starting multiplayer service", zap.String("port", cfg.Port))

	// ── Core Components ───────────────────────────────────────────────────────

	manager := room.NewManager(cfg, log)

	// The WS handler and Hub are mutually dependent: hub needs onMessage/onDisconnect
	// callbacks from WS; WS needs hub to send messages. Wire via closure after creation.
	var wsHandler *handlers.WS

	h := hub.New(
		log,
		func(roomID, userID string) {
			if wsHandler != nil {
				wsHandler.OnDisconnect(roomID, userID)
			}
		},
		func(roomID, userID string, msg models.InboundMessage) {
			if wsHandler != nil {
				wsHandler.OnMessage(roomID, userID, msg)
			}
		},
	)

	// Inject hub's Broadcast function into the room manager so rooms can notify players.
	manager.SetBroadcastFn(h.Broadcast)

	httpH := handlers.NewHTTP(manager, cfg.JWTSecret, log)
	wsHandler = handlers.NewWS(h, manager, cfg.JWTSecret, log)

	// ── Router ────────────────────────────────────────────────────────────────

	r := chi.NewRouter()
	r.Use(chimiddleware.RealIP)
	r.Use(chimiddleware.RequestID)
	r.Use(chimiddleware.Recoverer)
	r.Use(chimiddleware.Timeout(30 * time.Second))
	r.Use(requestLogger(log))

	r.Get("/health", healthHandler())
	r.Handle("/metrics", promhttp.Handler())

	r.Post("/rooms", httpH.CreateRoom)
	r.Get("/rooms/{id}", httpH.GetRoom)
	r.Post("/rooms/{id}/join", httpH.JoinRoom)
	r.Get("/rooms/{id}/ws", wsHandler.ServeWS)

	// ── Server ────────────────────────────────────────────────────────────────

	srv := &http.Server{
		Addr:         ":" + cfg.Port,
		Handler:      r,
		ReadTimeout:  15 * time.Second,
		WriteTimeout: 0, // 0 = no timeout — WebSocket connections are long-lived
		IdleTimeout:  120 * time.Second,
	}

	go func() {
		log.Info("multiplayer service listening", zap.String("addr", srv.Addr))
		if err := srv.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			log.Fatal("server error", zap.Error(err))
		}
	}()

	// ── Graceful Shutdown ─────────────────────────────────────────────────────

	quit := make(chan os.Signal, 1)
	signal.Notify(quit, syscall.SIGINT, syscall.SIGTERM)
	<-quit

	log.Info("shutdown signal received")
	ctx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
	defer cancel()

	if err := srv.Shutdown(ctx); err != nil {
		log.Error("graceful shutdown error", zap.Error(err))
	}
	log.Info("multiplayer service stopped")
}

func healthHandler() http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.Write([]byte(`{"status":"ok","service":"multiplayer","version":"0.1.0"}`))
	}
}

func requestLogger(log *zap.Logger) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			start := time.Now()
			ww := chimiddleware.NewWrapResponseWriter(w, r.ProtoMajor)
			next.ServeHTTP(ww, r)
			// Skip logging for health + metrics to avoid noise.
			if r.URL.Path == "/health" || r.URL.Path == "/metrics" {
				return
			}
			log.Info("http",
				zap.String("method", r.Method),
				zap.String("path", r.URL.Path),
				zap.Int("status", ww.Status()),
				zap.Duration("latency", time.Since(start)),
				zap.String("request_id", chimiddleware.GetReqID(r.Context())),
			)
		})
	}
}

func buildLogger(level string) *zap.Logger {
	var lvl zapcore.Level
	if err := lvl.UnmarshalText([]byte(level)); err != nil {
		lvl = zapcore.InfoLevel
	}
	cfg := zap.NewProductionConfig()
	cfg.Level = zap.NewAtomicLevelAt(lvl)
	l, err := cfg.Build()
	if err != nil {
		panic(err)
	}
	return l
}
