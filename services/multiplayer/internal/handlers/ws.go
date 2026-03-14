package handlers

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"strings"
	"time"
	"unicode/utf8"

	"github.com/go-chi/chi/v5"
	"github.com/gorilla/websocket"
	"go.uber.org/zap"

	"github.com/sudoku-ultra/multiplayer/internal/hub"
	"github.com/sudoku-ultra/multiplayer/internal/models"
	"github.com/sudoku-ultra/multiplayer/internal/room"
)

const (
	maxChatLen     = 500 // max chars per message
	maxChatWarnings = 3  // warnings before mute
)

var upgrader = websocket.Upgrader{
	ReadBufferSize:  1024,
	WriteBufferSize: 1024,
	CheckOrigin: func(r *http.Request) bool {
		// Allow all origins in development; restrict in production via ALLOWED_ORIGINS env.
		return true
	},
}

// WS handles the WebSocket upgrade and message dispatch for a room.
type WS struct {
	hub          *hub.Hub
	manager      *room.Manager
	secret       string
	mlServiceURL string // base URL for ml-service (moderation, etc.)
	log          *zap.Logger
}

// NewWS constructs the WebSocket handler.
func NewWS(h *hub.Hub, m *room.Manager, secret, mlServiceURL string, log *zap.Logger) *WS {
	return &WS{hub: h, manager: m, secret: secret, mlServiceURL: mlServiceURL, log: log}
}

// ServeWS upgrades an HTTP connection to WebSocket and registers the client.
// Route: GET /rooms/:id/ws
func (ws *WS) ServeWS(w http.ResponseWriter, r *http.Request) {
	roomID := chi.URLParam(r, "id")

	// Auth: accept token from query param (WS can't set headers in browser) or header.
	token := r.URL.Query().Get("token")
	if token == "" {
		token = strings.TrimPrefix(r.Header.Get("Authorization"), "Bearer ")
	}
	userID, displayName := parseToken(token, ws.secret)
	if userID == "" {
		http.Error(w, "unauthorized", http.StatusUnauthorized)
		return
	}

	rm, ok := ws.manager.Get(roomID)
	if !ok {
		http.Error(w, "room not found", http.StatusNotFound)
		return
	}

	// PHASE-4-HOOK: spectator mode — allow a third connection type that receives
	// MsgOpponentCell / MsgOpponentProgress broadcasts but cannot send MsgCellFill
	// or MsgReady. Spectators join via GET /rooms/:id/ws?role=spectator.
	// Implement spectator role gating, separate hub channel, and view-only client here.

	// If the player is reconnecting, mark them connected again.
	isReconnect := rm.HasPlayer(userID)
	if !isReconnect {
		// New connection — they must have joined via HTTP first.
		// For public matched rooms, both players are pre-added; this is fine.
		p := &models.Player{UserID: userID, DisplayName: displayName}
		if err := rm.AddPlayer(p, 2); err != nil {
			http.Error(w, err.Error(), http.StatusConflict)
			return
		}
	}

	conn, err := upgrader.Upgrade(w, r, nil)
	if err != nil {
		ws.log.Error("websocket upgrade failed", zap.Error(err))
		return
	}

	client := ws.hub.NewClient(conn, userID, roomID)
	ws.hub.Register(client)

	if isReconnect {
		rm.MarkConnected(userID)
		// Send full room state on reconnect.
		ws.hub.Send(userID, models.OutboundMessage{
			Type:    models.MsgReconnected,
			Payload: rm.View(),
		})
		ws.log.Info("player reconnected", zap.String("user_id", userID), zap.String("room_id", roomID))
	} else {
		// Notify others that this player joined.
		ws.hub.Broadcast(roomID, models.OutboundMessage{
			Type: models.MsgPlayerJoined,
			Payload: map[string]string{
				"user_id":      userID,
				"display_name": displayName,
			},
		})
		// Send current room state to the new joiner.
		ws.hub.Send(userID, models.OutboundMessage{
			Type:    models.MsgRoomState,
			Payload: rm.View(),
		})
	}

	go client.WritePump()
	client.ReadPump() // blocks until disconnect
}

// ─── Message Dispatcher ───────────────────────────────────────────────────────

// OnMessage is registered as the hub's inbound message handler.
func (ws *WS) OnMessage(roomID, userID string, msg models.InboundMessage) {
	rm, ok := ws.manager.Get(roomID)
	if !ok {
		return
	}

	switch msg.Type {

	case models.MsgReady:
		ws.handleReady(rm, userID, true)

	case models.MsgUnready:
		ws.handleReady(rm, userID, false)

	case models.MsgCellFill:
		ws.handleCellFill(rm, userID, msg.Payload)

	case models.MsgForfeit:
		ws.handleForfeit(rm, userID)

	case models.MsgPing:
		ws.hub.Send(userID, models.OutboundMessage{Type: models.MsgPong})

	case models.MsgChatSend:
		ws.handleChat(rm, userID, msg.Payload)

	default:
		ws.hub.Send(userID, models.OutboundMessage{
			Type:    models.MsgError,
			Payload: models.ErrorPayload{Code: "UNKNOWN_TYPE", Message: "unknown message type"},
		})
	}
}

// OnDisconnect is registered as the hub's disconnect handler.
func (ws *WS) OnDisconnect(roomID, userID string) {
	rm, ok := ws.manager.Get(roomID)
	if !ok {
		return
	}

	state := rm.State()

	// Notify others.
	ws.hub.Broadcast(roomID, models.OutboundMessage{
		Type:    models.MsgPlayerLeft,
		Payload: map[string]string{"user_id": userID},
	})

	switch state {
	case models.StateWaiting, models.StateCountdown:
		// Cancel countdown if active and remove the player.
		rm.CancelCountdown()
		rm.RemovePlayer(userID)
		ws.log.Info("player left waiting room", zap.String("user_id", userID), zap.String("room_id", roomID))

	case models.StateInProgress:
		// Mark disconnected and start the reconnect window.
		rm.MarkDisconnected(userID)
		ws.manager.StartReconnectTimer(rm, userID)
		ws.log.Info("player disconnected mid-game", zap.String("user_id", userID), zap.String("room_id", roomID))
	}
}

// ─── Ready ────────────────────────────────────────────────────────────────────

func (ws *WS) handleReady(rm *room.Room, userID string, ready bool) {
	allReady, err := rm.SetReady(userID, ready)
	if err != nil {
		ws.hub.Send(userID, models.OutboundMessage{
			Type:    models.MsgError,
			Payload: models.ErrorPayload{Code: "NOT_IN_ROOM", Message: err.Error()},
		})
		return
	}

	ws.hub.Broadcast(rm.ID(), models.OutboundMessage{
		Type: models.MsgReadyChanged,
		Payload: map[string]any{
			"user_id": userID,
			"ready":   ready,
		},
	})

	if !ready && rm.State() == models.StateCountdown {
		rm.CancelCountdown()
		ws.hub.Broadcast(rm.ID(), models.OutboundMessage{
			Type:    models.MsgRoomState,
			Payload: rm.View(),
		})
		return
	}

	if allReady && rm.State() == models.StateWaiting {
		ws.manager.RunCountdown(rm)
	}
}

// ─── Cell Fill ────────────────────────────────────────────────────────────────

func (ws *WS) handleCellFill(rm *room.Room, userID string, payload map[string]any) {
	cellIndex, ok1 := intFromPayload(payload, "cell_index")
	value, ok2 := intFromPayload(payload, "value")
	if !ok1 || !ok2 {
		ws.hub.Send(userID, models.OutboundMessage{
			Type:    models.MsgError,
			Payload: models.ErrorPayload{Code: "BAD_PAYLOAD", Message: "cell_index and value required"},
		})
		return
	}

	correct, complete, err := rm.ApplyCell(userID, cellIndex, value)
	if err != nil {
		ws.hub.Send(userID, models.OutboundMessage{
			Type:    models.MsgError,
			Payload: models.ErrorPayload{Code: "CELL_ERROR", Message: err.Error()},
		})
		return
	}

	if !correct {
		// Wrong answer — don't broadcast; let client handle locally.
		return
	}

	// Broadcast cell index (no value) to opponent.
	opponentID := rm.OpponentID(userID)
	if opponentID != "" {
		ws.hub.Send(opponentID, models.OutboundMessage{
			Type: models.MsgOpponentCell,
			Payload: models.OpponentCellPayload{
				UserID:    userID,
				CellIndex: cellIndex,
			},
		})
		ws.hub.Send(opponentID, models.OutboundMessage{
			Type: models.MsgOpponentProgress,
			// CellsFilled is read from the room's player state (already incremented).
			Payload: func() models.OpponentProgressPayload {
				view := rm.View()
				if p, ok := view.Players[userID]; ok {
					return models.OpponentProgressPayload{
						UserID:      userID,
						CellsFilled: p.CellsFilled,
					}
				}
				return models.OpponentProgressPayload{UserID: userID}
			}(),
		})
	}

	if complete {
		ws.finishGame(rm, userID, models.EndReasonCompleted)
	}
}

// ─── Forfeit ──────────────────────────────────────────────────────────────────

func (ws *WS) handleForfeit(rm *room.Room, userID string) {
	if rm.IsFinished() {
		return
	}
	winnerID := rm.OpponentID(userID)
	ws.finishGame(rm, winnerID, models.EndReasonForfeit)
	ws.log.Info("player forfeited", zap.String("user_id", userID), zap.String("room_id", rm.ID()))
}

// ─── Game End ─────────────────────────────────────────────────────────────────

func (ws *WS) finishGame(rm *room.Room, winnerID string, reason models.EndReason) {
	ws.manager.FinishRoom(rm, winnerID, reason)
	ws.hub.Broadcast(rm.ID(), models.OutboundMessage{
		Type: models.MsgGameEnd,
		Payload: models.GameEndPayload{
			WinnerID: winnerID,
			Reason:   reason,
		},
	})
	ws.log.Info("game ended",
		zap.String("room_id", rm.ID()),
		zap.String("winner", winnerID),
		zap.String("reason", string(reason)))
}

// ─── Chat ─────────────────────────────────────────────────────────────────────

func (ws *WS) handleChat(rm *room.Room, userID string, payload map[string]any) {
	// Muted users cannot send.
	if rm.IsUserMuted(userID) {
		ws.hub.Send(userID, models.OutboundMessage{
			Type:    models.MsgChatMuted,
			Payload: map[string]string{"message": "You are muted for this session."},
		})
		return
	}

	text, ok := payload["text"].(string)
	if !ok || strings.TrimSpace(text) == "" {
		return
	}

	// Truncate to maxChatLen characters (not bytes).
	if utf8.RuneCountInString(text) > maxChatLen {
		runes := []rune(text)
		text = string(runes[:maxChatLen])
	}
	text = strings.TrimSpace(text)

	// Moderate — fail open (allow message) if ml-service is unreachable.
	isToxic := false
	if ws.mlServiceURL != "" {
		result, err := ws.moderate(text)
		if err != nil {
			ws.log.Warn("moderation request failed (fail open)", zap.Error(err))
		} else {
			isToxic = result.IsToxic
		}
	}

	if isToxic {
		warnings := rm.RecordChatWarning(userID)
		if warnings >= maxChatWarnings {
			rm.MuteUser(userID)
			ws.hub.Send(userID, models.OutboundMessage{
				Type:    models.MsgChatMuted,
				Payload: map[string]string{"message": "You have been muted for sending toxic messages."},
			})
			ws.log.Info("user muted for toxic chat",
				zap.String("user_id", userID),
				zap.String("room_id", rm.ID()),
			)
			return
		}
		ws.hub.Send(userID, models.OutboundMessage{
			Type: models.MsgChatBlocked,
			Payload: models.ChatBlockedPayload{
				Warning:   warnings,
				Remaining: maxChatWarnings - warnings,
				Message:   fmt.Sprintf("Message blocked. Warning %d of %d.", warnings, maxChatWarnings),
			},
		})
		return
	}

	// Look up display name from room view.
	displayName := userID
	if p, ok2 := rm.View().Players[userID]; ok2 {
		displayName = p.DisplayName
	}

	entry := room.NewChatEntry(userID, displayName, text)
	rm.AddChat(entry)

	ws.hub.Broadcast(rm.ID(), models.OutboundMessage{
		Type: models.MsgChatMessage,
		Payload: models.ChatMessagePayload{
			SenderID:    userID,
			DisplayName: displayName,
			Text:        text,
			Timestamp:   entry.Timestamp,
		},
	})
}

// moderationResult is the subset of /api/v1/moderate we care about.
type moderationResult struct {
	IsToxic    bool    `json:"is_toxic"`
	Confidence float64 `json:"confidence"`
	Category   string  `json:"category"`
}

// moderate calls the ml-service moderation endpoint.
// Returns nil result + error if unreachable; callers fail open.
func (ws *WS) moderate(text string) (*moderationResult, error) {
	body, err := json.Marshal(map[string]string{"text": text})
	if err != nil {
		return nil, err
	}

	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()

	req, err := http.NewRequestWithContext(ctx, http.MethodPost,
		ws.mlServiceURL+"/api/v1/moderate", bytes.NewReader(body))
	if err != nil {
		return nil, err
	}
	req.Header.Set("Content-Type", "application/json")

	resp, err := (&http.Client{}).Do(req)
	if err != nil {
		return nil, fmt.Errorf("ml-service unreachable: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("ml-service returned %d", resp.StatusCode)
	}

	var result moderationResult
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return nil, fmt.Errorf("decode moderation response: %w", err)
	}
	return &result, nil
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

func intFromPayload(p map[string]any, key string) (int, bool) {
	if p == nil {
		return 0, false
	}
	v, ok := p[key]
	if !ok {
		return 0, false
	}
	switch n := v.(type) {
	case float64:
		return int(n), true
	case int:
		return n, true
	}
	return 0, false
}
