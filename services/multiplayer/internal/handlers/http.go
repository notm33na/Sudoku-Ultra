package handlers

import (
	"context"
	"encoding/json"
	"net/http"
	"strings"
	"time"

	"github.com/go-chi/chi/v5"
	"go.uber.org/zap"

	"github.com/sudoku-ultra/multiplayer/internal/models"
	"github.com/sudoku-ultra/multiplayer/internal/room"
)

// HTTP bundles the HTTP handler dependencies.
type HTTP struct {
	manager   *room.Manager
	jwtSecret string
	log       *zap.Logger
}

// NewHTTP constructs the HTTP handler bundle.
func NewHTTP(manager *room.Manager, jwtSecret string, log *zap.Logger) *HTTP {
	return &HTTP{
		manager:   manager,
		jwtSecret: jwtSecret,
		log:       log,
	}
}

// ─── POST /rooms ──────────────────────────────────────────────────────────────

func (h *HTTP) CreateRoom(w http.ResponseWriter, r *http.Request) {
	userID, displayName, ok := h.authenticate(w, r)
	if !ok {
		return
	}

	var req models.CreateRoomRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, "INVALID_BODY", "request body must be valid JSON")
		return
	}
	if !validDifficulty(req.Difficulty) {
		writeError(w, http.StatusBadRequest, "INVALID_DIFFICULTY",
			"difficulty must be one of: super_easy, easy, medium, hard, super_hard, extreme")
		return
	}
	if req.Type == "" {
		req.Type = models.RoomTypePublic
	}
	if req.Type != models.RoomTypePublic && req.Type != models.RoomTypePrivate && req.Type != models.RoomTypeBot {
		writeError(w, http.StatusBadRequest, "INVALID_TYPE", "type must be public, private, or bot")
		return
	}

	ctx, cancel := context.WithTimeout(r.Context(), 6*time.Second)
	defer cancel()

	// Public matchmaking — attempt to pair before creating a dedicated room.
	if req.Type == models.RoomTypePublic {
		rm, err := h.manager.Enqueue(ctx, userID, displayName, req.Difficulty)
		if err != nil {
			h.log.Error("matchmaking error", zap.Error(err))
			writeError(w, http.StatusInternalServerError, "MATCHMAKING_ERROR", err.Error())
			return
		}
		if rm != nil {
			// Matched immediately — room ready for both players to connect.
			writeJSON(w, http.StatusCreated, models.CreateRoomResponse{
				RoomID: rm.ID(),
				Type:   models.RoomTypePublic,
			})
			return
		}
		// Still queued — client should poll or the WS connection will surface the match.
		writeJSON(w, http.StatusAccepted, map[string]string{
			"status":  "queued",
			"message": "waiting for opponent",
		})
		return
	}

	// Bot rooms: delegate to CreateBotRoom (pre-adds bot player + creator).
	if req.Type == models.RoomTypeBot {
		botTier := req.BotTier
		if botTier == "" {
			botTier = "medium"
		}
		rm, err := h.manager.CreateBotRoom(ctx, userID, displayName, botTier, req)
		if err != nil {
			h.log.Error("create bot room error", zap.Error(err))
			writeError(w, http.StatusInternalServerError, "CREATE_ROOM_ERROR", err.Error())
			return
		}
		writeJSON(w, http.StatusCreated, models.CreateRoomResponse{
			RoomID: rm.ID(),
			Type:   models.RoomTypeBot,
		})
		return
	}

	rm, err := h.manager.CreateRoom(ctx, userID, req)
	if err != nil {
		h.log.Error("create room error", zap.Error(err))
		writeError(w, http.StatusInternalServerError, "CREATE_ROOM_ERROR", err.Error())
		return
	}

	// For private rooms, also join the creator.
	if req.Type == models.RoomTypePrivate {
		if _, err := h.manager.JoinRoom(rm.ID(), userID, displayName); err != nil {
			h.log.Error("creator join error", zap.Error(err))
			writeError(w, http.StatusInternalServerError, "JOIN_ERROR", err.Error())
			return
		}
	}

	writeJSON(w, http.StatusCreated, models.CreateRoomResponse{
		RoomID: rm.ID(),
		Code:   rm.Code(),
		Type:   req.Type,
	})
}

// ─── GET /rooms/:id ───────────────────────────────────────────────────────────

func (h *HTTP) GetRoom(w http.ResponseWriter, r *http.Request) {
	roomID := chi.URLParam(r, "id")
	rm, ok := h.manager.Get(roomID)
	if !ok {
		writeError(w, http.StatusNotFound, "ROOM_NOT_FOUND", "room not found")
		return
	}
	writeJSON(w, http.StatusOK, rm.View())
}

// ─── POST /rooms/:id/join ─────────────────────────────────────────────────────

func (h *HTTP) JoinRoom(w http.ResponseWriter, r *http.Request) {
	userID, displayName, ok := h.authenticate(w, r)
	if !ok {
		return
	}

	var req models.JoinRoomRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, "INVALID_BODY", "request body must be valid JSON")
		return
	}

	// Support both join-by-ID (direct) and join-by-code (private).
	roomID := chi.URLParam(r, "id")
	rm, ok := h.manager.Get(roomID)
	if !ok && req.Code != "" {
		rm, ok = h.manager.GetByCode(req.Code)
	}
	if !ok {
		writeError(w, http.StatusNotFound, "ROOM_NOT_FOUND", "room or invite code not found")
		return
	}

	if rm.HasPlayer(userID) {
		// Already in — return current state (reconnect scenario).
		writeJSON(w, http.StatusOK, rm.View())
		return
	}

	if _, err := h.manager.JoinRoom(rm.ID(), userID, displayName); err != nil {
		switch err {
		case room.ErrRoomFull:
			writeError(w, http.StatusConflict, "ROOM_FULL", "room is full")
		case room.ErrRoomNotWaiting:
			writeError(w, http.StatusConflict, "ROOM_IN_PROGRESS", "game already started")
		default:
			writeError(w, http.StatusInternalServerError, "JOIN_ERROR", err.Error())
		}
		return
	}

	writeJSON(w, http.StatusOK, rm.View())
}

// ─── Auth Helper ──────────────────────────────────────────────────────────────

// authenticate extracts userID and displayName from the Authorization header.
// In production this validates a JWT; in dev it accepts a simple "Bearer uid:name" format.
func (h *HTTP) authenticate(w http.ResponseWriter, r *http.Request) (userID, displayName string, ok bool) {
	authHeader := r.Header.Get("Authorization")
	if authHeader == "" {
		writeError(w, http.StatusUnauthorized, "MISSING_TOKEN", "Authorization header required")
		return "", "", false
	}

	token := strings.TrimPrefix(authHeader, "Bearer ")
	userID, displayName = parseToken(token, h.jwtSecret)
	if userID == "" {
		writeError(w, http.StatusUnauthorized, "INVALID_TOKEN", "invalid or expired token")
		return "", "", false
	}
	return userID, displayName, true
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

func writeJSON(w http.ResponseWriter, status int, v any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	json.NewEncoder(w).Encode(v)
}

func writeError(w http.ResponseWriter, status int, code, message string) {
	writeJSON(w, status, map[string]string{"error": code, "message": message})
}

var validDifficulties = map[string]bool{
	"super_easy": true, "easy": true, "medium": true,
	"hard": true, "super_hard": true, "extreme": true,
}

func validDifficulty(d string) bool {
	return validDifficulties[d]
}

// parseToken is a minimal JWT parser. In production, replace with a full JWT library.
// It accepts "uid:displayName" (dev) or a signed JWT (prod — implement verify here).
func parseToken(token, secret string) (userID, displayName string) {
	// Dev mode: "Bearer <userID>:<displayName>"
	if parts := strings.SplitN(token, ":", 2); len(parts) == 2 && secret == "dev-secret-change-in-production" {
		return parts[0], parts[1]
	}
	// TODO: full JWT verification for production
	// claims, err := jwt.Parse(token, func(t *jwt.Token) (interface{}, error) { ... })
	return "", ""
}
