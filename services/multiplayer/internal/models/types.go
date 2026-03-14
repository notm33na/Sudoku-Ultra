package models

import "time"

// ─── Room State Machine ───────────────────────────────────────────────────────

// RoomState represents the lifecycle state of a multiplayer room.
type RoomState string

const (
	StateWaiting    RoomState = "waiting"     // accepting players, waiting for ready
	StateCountdown  RoomState = "countdown"   // all ready, 3-2-1 before start
	StateInProgress RoomState = "in_progress" // game active
	StateFinished   RoomState = "finished"    // game over
)

// RoomType distinguishes public matchmade rooms from private invite rooms.
type RoomType string

const (
	RoomTypePublic  RoomType = "public"
	RoomTypePrivate RoomType = "private"
	RoomTypeBot     RoomType = "bot"
)

// EndReason describes why a game ended.
type EndReason string

const (
	EndReasonCompleted  EndReason = "completed"  // winner solved the puzzle
	EndReasonForfeit    EndReason = "forfeit"     // player gave up
	EndReasonDisconnect EndReason = "disconnect"  // player never reconnected
	EndReasonTimeout    EndReason = "timeout"     // reconnect window expired
)

// ─── Player ───────────────────────────────────────────────────────────────────

// Player holds the in-room state of a single participant.
type Player struct {
	UserID      string     `json:"user_id"`
	DisplayName string     `json:"display_name"`
	Ready       bool       `json:"ready"`
	CellsFilled int        `json:"cells_filled"`
	Connected   bool       `json:"connected"`
	IsBot       bool       `json:"is_bot"`
	// Board tracks the player's actual cell values (server-side only, not broadcast).
	Board [81]int `json:"-"`
	// DisconnectedAt is set when a player drops; nil when connected.
	DisconnectedAt *time.Time `json:"-"`
}

// ─── Room ─────────────────────────────────────────────────────────────────────

// Room is the full server-side state of a multiplayer game room.
type Room struct {
	ID         string    `json:"id"`
	Code       string    `json:"code"`       // 6-char invite code (private rooms)
	Type       RoomType  `json:"type"`
	State      RoomState `json:"state"`
	Difficulty string    `json:"difficulty"`
	BotTier    string    `json:"bot_tier,omitempty"` // "easy"|"medium"|"hard" for bot rooms
	Puzzle     [81]int   `json:"puzzle"`             // given cells (0 = empty)
	Solution   [81]int   `json:"solution"`           // authoritative solution
	Players    map[string]*Player `json:"players"` // userID → Player
	CreatorID  string    `json:"creator_id"`
	CreatedAt  time.Time `json:"created_at"`
	StartedAt  *time.Time `json:"started_at,omitempty"`
	FinishedAt *time.Time `json:"finished_at,omitempty"`
	WinnerID   string    `json:"winner_id,omitempty"`
	EndReason  EndReason `json:"end_reason,omitempty"`
}

// PlayerView returns a public-facing snapshot of a player (no board values).
type PlayerView struct {
	UserID      string `json:"user_id"`
	DisplayName string `json:"display_name"`
	Ready       bool   `json:"ready"`
	CellsFilled int    `json:"cells_filled"`
	Connected   bool   `json:"connected"`
	IsBot       bool   `json:"is_bot"`
}

// RoomView is the public projection of a Room sent to clients.
type RoomView struct {
	ID         string                 `json:"id"`
	Code       string                 `json:"code"`
	Type       RoomType               `json:"type"`
	State      RoomState              `json:"state"`
	Difficulty string                 `json:"difficulty"`
	Players    map[string]*PlayerView `json:"players"`
	CreatedAt  time.Time              `json:"created_at"`
	StartedAt  *time.Time             `json:"started_at,omitempty"`
	FinishedAt *time.Time             `json:"finished_at,omitempty"`
	WinnerID   string                 `json:"winner_id,omitempty"`
	EndReason  EndReason              `json:"end_reason,omitempty"`
}

// ─── WebSocket Messages ───────────────────────────────────────────────────────

// MsgType is the discriminator field on every WebSocket message.
type MsgType string

const (
	// Inbound (client → server)
	MsgReady    MsgType = "ready"
	MsgUnready  MsgType = "unready"
	MsgCellFill MsgType = "cell_fill"
	MsgForfeit  MsgType = "forfeit"
	MsgPing     MsgType = "ping"
	MsgChatSend MsgType = "chat" // chat message from client

	// Outbound (server → client)
	MsgRoomState        MsgType = "room_state"
	MsgPlayerJoined     MsgType = "player_joined"
	MsgPlayerLeft       MsgType = "player_left"
	MsgReadyChanged     MsgType = "ready_changed"
	MsgCountdown        MsgType = "countdown"
	MsgGameStart        MsgType = "game_start"
	MsgOpponentCell     MsgType = "opponent_cell" // cell index only, no value
	MsgOpponentProgress MsgType = "opponent_progress"
	MsgGameEnd          MsgType = "game_end"
	MsgError            MsgType = "error"
	MsgPong             MsgType = "pong"
	MsgReconnected      MsgType = "reconnected"
	MsgChatMessage      MsgType = "chat_message" // relayed chat message
	MsgChatBlocked      MsgType = "chat_blocked" // toxic message blocked
	MsgChatMuted        MsgType = "chat_muted"   // sender is muted
)

// InboundMessage is the envelope for all messages received from a client.
type InboundMessage struct {
	Type    MsgType        `json:"type"`
	Payload map[string]any `json:"payload,omitempty"`
}

// OutboundMessage is the envelope for all messages sent to a client.
type OutboundMessage struct {
	Type    MsgType `json:"type"`
	Payload any     `json:"payload,omitempty"`
}

// ─── Specific Payload Types ───────────────────────────────────────────────────

type CellFillPayload struct {
	CellIndex int `json:"cell_index"` // 0–80
	Value     int `json:"value"`      // 1–9
}

type OpponentCellPayload struct {
	UserID    string `json:"user_id"`
	CellIndex int    `json:"cell_index"` // index only — no value exposed
}

type OpponentProgressPayload struct {
	UserID      string `json:"user_id"`
	CellsFilled int    `json:"cells_filled"`
}

type CountdownPayload struct {
	Seconds int `json:"seconds"`
}

type GameStartPayload struct {
	Puzzle     [81]int `json:"puzzle"`
	Difficulty string  `json:"difficulty"`
}

type GameEndPayload struct {
	WinnerID string    `json:"winner_id"`
	Reason   EndReason `json:"reason"`
}

type ErrorPayload struct {
	Code    string `json:"code"`
	Message string `json:"message"`
}

// ─── Chat Payloads ────────────────────────────────────────────────────────────

// ChatMessagePayload is broadcast to all room members when a message is relayed.
type ChatMessagePayload struct {
	SenderID    string `json:"sender_id"`
	DisplayName string `json:"display_name"`
	Text        string `json:"text"`
	Timestamp   string `json:"timestamp"` // RFC3339
}

// ChatBlockedPayload is sent to the sender when a message is rejected.
type ChatBlockedPayload struct {
	Warning   int    `json:"warning"`   // 1, 2, or 3
	Remaining int    `json:"remaining"` // warnings before mute
	Message   string `json:"message"`
}

// ─── HTTP Request/Response Bodies ────────────────────────────────────────────

type CreateRoomRequest struct {
	Difficulty string   `json:"difficulty"` // super_easy|easy|medium|hard|super_hard|extreme
	Type       RoomType `json:"type"`       // public|private|bot
	BotTier    string   `json:"bot_tier,omitempty"` // easy|medium|hard (bot rooms only)
}

type CreateRoomResponse struct {
	RoomID string `json:"room_id"`
	Code   string `json:"code,omitempty"`
	Type   RoomType `json:"type"`
}

type JoinRoomRequest struct {
	Code string `json:"code"` // required for private rooms
}

// PuzzleResponse is the shape returned by game-service for puzzle fetch.
type PuzzleResponse struct {
	Puzzle     [81]int `json:"puzzle"`
	Solution   [81]int `json:"solution"`
	Difficulty string  `json:"difficulty"`
	ClueCount  int     `json:"clueCount"`
}
