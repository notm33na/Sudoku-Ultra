package room

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"math/rand"
	"net/http"
	"sync"
	"time"

	"github.com/google/uuid"
	"go.uber.org/zap"

	"github.com/sudoku-ultra/multiplayer/internal/config"
	"github.com/sudoku-ultra/multiplayer/internal/metrics"
	"github.com/sudoku-ultra/multiplayer/internal/models"
)

// Manager owns all Rooms and the matchmaking queue.
// It is the single source of truth for room lifecycle.
type Manager struct {
	mu     sync.RWMutex
	rooms  map[string]*Room   // roomID → Room
	codes  map[string]string  // inviteCode → roomID
	queue  []queueEntry       // simple in-memory public matchmaking queue
	cfg    *config.Config
	log    *zap.Logger

	// broadcastFn is injected from the Hub so the room can send messages.
	broadcastFn func(roomID string, msg models.OutboundMessage)
}

type queueEntry struct {
	userID      string
	displayName string
	difficulty  string
	enqueuedAt  time.Time
}

// NewManager creates an empty room manager.
func NewManager(cfg *config.Config, log *zap.Logger) *Manager {
	return &Manager{
		rooms: make(map[string]*Room),
		codes: make(map[string]string),
		cfg:   cfg,
		log:   log,
	}
}

// SetBroadcastFn injects the hub broadcast function. Called once after Hub is built.
func (m *Manager) SetBroadcastFn(fn func(roomID string, msg models.OutboundMessage)) {
	m.broadcastFn = fn
}

// ─── Room Creation ────────────────────────────────────────────────────────────

// CreateRoom creates a new room and registers it. Returns the room.
func (m *Manager) CreateRoom(
	ctx context.Context,
	creatorID string,
	req models.CreateRoomRequest,
) (*Room, error) {
	puzzle, solution, err := m.fetchPuzzle(ctx, req.Difficulty)
	if err != nil {
		return nil, fmt.Errorf("fetch puzzle: %w", err)
	}

	id := uuid.New().String()
	code := ""
	if req.Type == models.RoomTypePrivate {
		code = m.generateUniqueCode()
	}

	rm := NewRoom(id, code, creatorID, req.Type, req.Difficulty, puzzle, solution, m.broadcastFn)

	m.mu.Lock()
	m.rooms[id] = rm
	if code != "" {
		m.codes[code] = id
	}
	m.mu.Unlock()

	metrics.ActiveRooms.Inc()
	metrics.RoomsCreatedTotal.WithLabelValues(string(req.Type)).Inc()
	m.log.Info("room created", zap.String("room_id", id), zap.String("type", string(req.Type)), zap.String("difficulty", req.Difficulty))
	return rm, nil
}

// ─── Matchmaking ──────────────────────────────────────────────────────────────

// Enqueue adds a player to the public matchmaking queue.
// If another player is already waiting for the same difficulty, a room is created
// and both players are added to it. Returns the room (may be nil if still queued).
func (m *Manager) Enqueue(
	ctx context.Context,
	userID, displayName, difficulty string,
) (*Room, error) {
	m.mu.Lock()
	defer m.mu.Unlock()

	// Look for an existing entry with the same difficulty.
	for i, entry := range m.queue {
		if entry.difficulty == difficulty && entry.userID != userID {
			// Pair found — remove from queue and create room.
			m.queue = append(m.queue[:i], m.queue[i+1:]...)
			metrics.MatchmakingQueueSize.Dec()

			m.mu.Unlock()
			rm, err := m.createMatchedRoom(ctx, entry, userID, displayName, difficulty)
			m.mu.Lock()
			return rm, err
		}
	}

	// No match yet — add to queue.
	m.queue = append(m.queue, queueEntry{
		userID:      userID,
		displayName: displayName,
		difficulty:  difficulty,
		enqueuedAt:  time.Now().UTC(),
	})
	metrics.MatchmakingQueueSize.Inc()
	m.log.Info("player queued", zap.String("user_id", userID), zap.String("difficulty", difficulty))
	return nil, nil
}

// DequeuePlayer removes a player from the matchmaking queue (they cancelled).
func (m *Manager) DequeuePlayer(userID string) {
	m.mu.Lock()
	defer m.mu.Unlock()
	for i, e := range m.queue {
		if e.userID == userID {
			m.queue = append(m.queue[:i], m.queue[i+1:]...)
			metrics.MatchmakingQueueSize.Dec()
			return
		}
	}
}

// createMatchedRoom is called without the outer lock held.
func (m *Manager) createMatchedRoom(
	ctx context.Context,
	p1 queueEntry,
	p2UserID, p2DisplayName, difficulty string,
) (*Room, error) {
	puzzle, solution, err := m.fetchPuzzle(ctx, difficulty)
	if err != nil {
		return nil, fmt.Errorf("fetch puzzle for matched room: %w", err)
	}

	id := uuid.New().String()
	rm := NewRoom(id, "", p1.userID, models.RoomTypePublic, difficulty, puzzle, solution, m.broadcastFn)

	player1 := &models.Player{UserID: p1.userID, DisplayName: p1.displayName}
	player2 := &models.Player{UserID: p2UserID, DisplayName: p2DisplayName}

	if err := rm.AddPlayer(player1, m.cfg.MaxRoomPlayers); err != nil {
		return nil, err
	}
	if err := rm.AddPlayer(player2, m.cfg.MaxRoomPlayers); err != nil {
		return nil, err
	}

	m.mu.Lock()
	m.rooms[id] = rm
	m.mu.Unlock()

	metrics.ActiveRooms.Inc()
	metrics.RoomsCreatedTotal.WithLabelValues("public").Inc()
	m.log.Info("matched room created", zap.String("room_id", id),
		zap.String("p1", p1.userID), zap.String("p2", p2UserID))
	return rm, nil
}

// ─── Lookup ───────────────────────────────────────────────────────────────────

// Get returns a room by ID.
func (m *Manager) Get(roomID string) (*Room, bool) {
	m.mu.RLock()
	defer m.mu.RUnlock()
	rm, ok := m.rooms[roomID]
	return rm, ok
}

// GetByCode returns a room by its 6-character invite code.
func (m *Manager) GetByCode(code string) (*Room, bool) {
	m.mu.RLock()
	defer m.mu.RUnlock()
	id, ok := m.codes[code]
	if !ok {
		return nil, false
	}
	return m.rooms[id], true
}

// ─── Join ─────────────────────────────────────────────────────────────────────

// JoinRoom adds a player to an existing room by ID (used for private rooms via code).
func (m *Manager) JoinRoom(roomID, userID, displayName string) (*Room, error) {
	rm, ok := m.Get(roomID)
	if !ok {
		return nil, fmt.Errorf("room %s not found", roomID)
	}
	p := &models.Player{UserID: userID, DisplayName: displayName}
	if err := rm.AddPlayer(p, m.cfg.MaxRoomPlayers); err != nil {
		return nil, err
	}
	return rm, nil
}

// ─── Countdown ────────────────────────────────────────────────────────────────

// RunCountdown broadcasts tick messages then starts the game.
// It is launched as a goroutine when all players are ready.
func (m *Manager) RunCountdown(rm *Room) {
	ctx, cancel := context.WithCancel(context.Background())
	rm.StartCountdown(cancel)

	go func() {
		for i := m.cfg.CountdownSecs; i >= 1; i-- {
			select {
			case <-ctx.Done():
				// A player unreadied — countdown cancelled.
				return
			default:
			}
			m.broadcastFn(rm.ID(), models.OutboundMessage{
				Type:    models.MsgCountdown,
				Payload: models.CountdownPayload{Seconds: i},
			})
			select {
			case <-ctx.Done():
				return
			case <-time.After(time.Second):
			}
		}

		// Countdown finished — start the game.
		rm.StartGame()
		puzzle, difficulty := rm.Puzzle()
		m.broadcastFn(rm.ID(), models.OutboundMessage{
			Type: models.MsgGameStart,
			Payload: models.GameStartPayload{
				Puzzle:     puzzle,
				Difficulty: difficulty,
			},
		})
		m.log.Info("game started", zap.String("room_id", rm.ID()))

		// If this is a bot room, start the bot move loop.
		if rm.Type() == models.RoomTypeBot {
			m.RunBotLoop(rm)
		}
	}()
}

// ─── Reconnect Window ─────────────────────────────────────────────────────────

// StartReconnectTimer waits for ReconnectWindow. If the player hasn't reconnected,
// the opponent wins by disconnect.
func (m *Manager) StartReconnectTimer(rm *Room, disconnectedUserID string) {
	go func() {
		time.Sleep(m.cfg.ReconnectWindow)

		// Check if still disconnected.
		if rm.IsFinished() {
			return
		}
		if rm.DisconnectedAt(disconnectedUserID).IsZero() {
			// Player reconnected — nothing to do.
			metrics.DisconnectsTotal.WithLabelValues("reconnected").Inc()
			return
		}

		// Player never came back — opponent wins.
		winnerID := rm.OpponentID(disconnectedUserID)
		rm.Finish(winnerID, models.EndReasonDisconnect)
		metrics.DisconnectsTotal.WithLabelValues("forfeited").Inc()
		metrics.RoomDuration.Observe(time.Since(rm.CreatedAt()).Seconds())
		metrics.ActiveRooms.Dec()

		m.broadcastFn(rm.ID(), models.OutboundMessage{
			Type: models.MsgGameEnd,
			Payload: models.GameEndPayload{
				WinnerID: winnerID,
				Reason:   models.EndReasonDisconnect,
			},
		})
		m.log.Info("forfeit by disconnect timeout",
			zap.String("room_id", rm.ID()),
			zap.String("disconnected_user", disconnectedUserID),
			zap.String("winner", winnerID))

		m.scheduleCleanup(rm.ID())
	}()
}

// ─── Cleanup ──────────────────────────────────────────────────────────────────

// FinishRoom marks the room finished and schedules its removal.
// For human-vs-human matches it fires a non-blocking POST to game-service to
// record the result and update Elo ratings.
func (m *Manager) FinishRoom(rm *Room, winnerID string, reason models.EndReason) {
	if rm.IsFinished() {
		return
	}
	durationMs := int(time.Since(rm.CreatedAt()).Milliseconds())
	rm.Finish(winnerID, reason)
	metrics.RoomDuration.Observe(time.Since(rm.CreatedAt()).Seconds())
	metrics.ActiveRooms.Dec()
	m.scheduleCleanup(rm.ID())

	// Only record Elo for human-vs-human matches.
	if rm.Type() == models.RoomTypeBot {
		return
	}
	view := rm.View()
	loserID := ""
	for uid := range view.Players {
		if uid != winnerID {
			loserID = uid
			break
		}
	}
	if loserID == "" || m.cfg.GameServiceURL == "" {
		return
	}
	go m.postMatchResult(rm.ID(), winnerID, loserID, string(reason), durationMs, view.Difficulty)
}

// postMatchResult fires a POST to game-service /api/ratings/match-result.
// Runs in a goroutine; failures are logged but do not affect game flow.
func (m *Manager) postMatchResult(
	roomID, winnerID, loserID, endReason string,
	durationMs int,
	difficulty string,
) {
	body, err := json.Marshal(map[string]any{
		"roomId":     roomID,
		"winnerId":   winnerID,
		"loserId":    loserID,
		"endReason":  endReason,
		"durationMs": durationMs,
		"difficulty": difficulty,
	})
	if err != nil {
		m.log.Error("postMatchResult: marshal failed", zap.Error(err))
		return
	}

	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	req, err := http.NewRequestWithContext(ctx, http.MethodPost,
		m.cfg.GameServiceURL+"/api/ratings/match-result", bytes.NewReader(body))
	if err != nil {
		m.log.Error("postMatchResult: build request failed", zap.Error(err))
		return
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Internal-Secret", m.cfg.InternalSecret)

	resp, err := (&http.Client{}).Do(req)
	if err != nil {
		m.log.Warn("postMatchResult: game-service unreachable", zap.Error(err))
		return
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusCreated {
		m.log.Warn("postMatchResult: unexpected status", zap.Int("status", resp.StatusCode))
	}
}

// scheduleCleanup removes the room from the map after a 60s grace period
// (so in-flight clients can still query the final state).
func (m *Manager) scheduleCleanup(roomID string) {
	go func() {
		time.Sleep(60 * time.Second)
		m.mu.Lock()
		rm, ok := m.rooms[roomID]
		if ok {
			code := rm.Code()
			delete(m.rooms, roomID)
			if code != "" {
				delete(m.codes, code)
			}
		}
		m.mu.Unlock()
		m.log.Info("room cleaned up", zap.String("room_id", roomID))
	}()
}

// ─── Bot Rooms ────────────────────────────────────────────────────────────────

// botPlayerID is the fixed userID used for the bot slot in bot rooms.
const botPlayerID = "bot"

// CreateBotRoom creates a private room, adds the human creator, and pre-adds
// a bot player (IsBot=true, Ready=true). The human still needs to press ready
// before the countdown starts.
func (m *Manager) CreateBotRoom(
	ctx context.Context,
	creatorID, creatorName, botTier string,
	req models.CreateRoomRequest,
) (*Room, error) {
	puzzle, solution, err := m.fetchPuzzle(ctx, req.Difficulty)
	if err != nil {
		return nil, fmt.Errorf("fetch puzzle for bot room: %w", err)
	}

	id := uuid.New().String()
	rm := NewRoom(id, "", creatorID, models.RoomTypeBot, req.Difficulty, puzzle, solution, m.broadcastFn)
	rm.data.BotTier = botTier

	human := &models.Player{UserID: creatorID, DisplayName: creatorName}
	bot := &models.Player{UserID: botPlayerID, DisplayName: "Bot (" + botTier + ")", IsBot: true, Ready: true}

	if err := rm.AddPlayer(human, m.cfg.MaxRoomPlayers); err != nil {
		return nil, err
	}
	if err := rm.AddPlayer(bot, m.cfg.MaxRoomPlayers); err != nil {
		return nil, err
	}

	m.mu.Lock()
	m.rooms[id] = rm
	m.mu.Unlock()

	metrics.ActiveRooms.Inc()
	metrics.RoomsCreatedTotal.WithLabelValues("bot").Inc()
	m.log.Info("bot room created",
		zap.String("room_id", id),
		zap.String("creator", creatorID),
		zap.String("tier", botTier),
	)
	return rm, nil
}

// RunBotLoop starts the bot move loop after the game starts.
// Called from RunCountdown once StartGame() has been issued.
// The loop polls the ml-service bot endpoint at tier-specific intervals
// and applies moves until the room finishes.
func (m *Manager) RunBotLoop(rm *Room) {
	tier := rm.BotTier()
	minMs, maxMs := m.cfg.BotDelayRange(tier)

	go func() {
		for {
			if rm.IsFinished() {
				return
			}

			// Randomised delay within tier range.
			delay := time.Duration(minMs+rand.Intn(maxMs-minMs+1)) * time.Millisecond
			time.Sleep(delay)

			if rm.IsFinished() {
				return
			}
			if rm.State() != models.StateInProgress {
				continue
			}

			// Fetch bot's current board and the room solution.
			boardPtr, solutionPtr := rm.BotBoard()
			if boardPtr == nil {
				return // bot player not found
			}
			board, solution := *boardPtr, *solutionPtr
			_ = solution // used in fetchBotMove below

			// Call ml-service for the next move.
			move, err := m.fetchBotMove(tier, board, *solutionPtr)
			if err != nil {
				m.log.Warn("bot move fetch failed", zap.Error(err))
				continue
			}

			// Apply the move as if it came from the bot player.
			correct, complete, err := rm.ApplyCell(botPlayerID, move.CellIndex, move.Digit)
			if err != nil || !correct {
				m.log.Debug("bot applied invalid move", zap.Error(err))
				continue
			}

			// Broadcast opponent-cell to human players.
			m.broadcastFn(rm.ID(), models.OutboundMessage{
				Type: models.MsgOpponentCell,
				Payload: models.OpponentCellPayload{
					UserID:    botPlayerID,
					CellIndex: move.CellIndex,
				},
			})

			// Broadcast bot progress.
			view := rm.View()
			if bp, ok := view.Players[botPlayerID]; ok {
				m.broadcastFn(rm.ID(), models.OutboundMessage{
					Type: models.MsgOpponentProgress,
					Payload: models.OpponentProgressPayload{
						UserID:      botPlayerID,
						CellsFilled: bp.CellsFilled,
					},
				})
			}

			if complete {
				m.FinishRoom(rm, botPlayerID, models.EndReasonCompleted)
				m.broadcastFn(rm.ID(), models.OutboundMessage{
					Type: models.MsgGameEnd,
					Payload: models.GameEndPayload{
						WinnerID: botPlayerID,
						Reason:   models.EndReasonCompleted,
					},
				})
				return
			}
		}
	}()
}

// botMoveResult is the shape returned by POST /api/v1/bot/move.
type botMoveResult struct {
	CellIndex  int     `json:"cell_index"`
	Digit      int     `json:"digit"`
	Confidence float64 `json:"confidence"`
	Source     string  `json:"source"`
}

// fetchBotMove calls the ml-service bot endpoint.
func (m *Manager) fetchBotMove(tier string, board, solution [81]int) (*botMoveResult, error) {
	payload := map[string]any{
		"board":    board[:],
		"solution": solution[:],
		"tier":     tier,
	}
	body, err := json.Marshal(payload)
	if err != nil {
		return nil, err
	}

	url := m.cfg.BotServiceURL + "/api/v1/bot/move"
	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
	defer cancel()

	req, err := http.NewRequestWithContext(ctx, http.MethodPost, url, bytes.NewReader(body))
	if err != nil {
		return nil, err
	}
	req.Header.Set("Content-Type", "application/json")

	resp, err := (&http.Client{}).Do(req)
	if err != nil {
		return nil, fmt.Errorf("bot-service unreachable: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("bot-service returned %d", resp.StatusCode)
	}

	var result botMoveResult
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return nil, fmt.Errorf("decode bot move response: %w", err)
	}
	return &result, nil
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

// fetchPuzzle calls the game-service to retrieve a puzzle for the given difficulty.
func (m *Manager) fetchPuzzle(ctx context.Context, difficulty string) (puzzle, solution [81]int, err error) {
	url := fmt.Sprintf("%s/api/puzzles/random?difficulty=%s", m.cfg.GameServiceURL, difficulty)

	req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
	if err != nil {
		return puzzle, solution, err
	}

	client := &http.Client{Timeout: 5 * time.Second}
	resp, err := client.Do(req)
	if err != nil {
		return puzzle, solution, fmt.Errorf("game-service unreachable: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return puzzle, solution, fmt.Errorf("game-service returned %d", resp.StatusCode)
	}

	var pr models.PuzzleResponse
	if err := json.NewDecoder(resp.Body).Decode(&pr); err != nil {
		return puzzle, solution, fmt.Errorf("decode puzzle response: %w", err)
	}
	return pr.Puzzle, pr.Solution, nil
}

// generateUniqueCode generates a 6-character alphanumeric code not already in use.
func (m *Manager) generateUniqueCode() string {
	const chars = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789" // no ambiguous 0/O/1/I
	for {
		b := make([]byte, 6)
		for i := range b {
			b[i] = chars[rand.Intn(len(chars))]
		}
		code := string(b)
		if _, exists := m.codes[code]; !exists {
			return code
		}
	}
}
