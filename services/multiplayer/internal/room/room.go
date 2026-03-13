package room

import (
	"fmt"
	"sync"
	"time"

	"github.com/sudoku-ultra/multiplayer/internal/models"
)

// Room wraps models.Room with a mutex and the broadcast function needed for
// state-change notifications. All mutations must be made under mu.
type Room struct {
	mu   sync.RWMutex
	data models.Room

	// broadcast sends an OutboundMessage to every connected player in the room.
	// Injected by the Hub when the room is created.
	broadcast func(roomID string, msg models.OutboundMessage)

	// countdownCancel cancels an in-progress countdown if a player unreadies.
	countdownCancel func()
}

// NewRoom constructs a Room and populates it from a CreateRoomRequest.
func NewRoom(
	id, code, creatorID string,
	roomType models.RoomType,
	difficulty string,
	puzzle, solution [81]int,
	broadcast func(string, models.OutboundMessage),
) *Room {
	now := time.Now().UTC()
	return &Room{
		data: models.Room{
			ID:         id,
			Code:       code,
			Type:       roomType,
			State:      models.StateWaiting,
			Difficulty: difficulty,
			Puzzle:     puzzle,
			Solution:   solution,
			Players:    make(map[string]*models.Player),
			CreatorID:  creatorID,
			CreatedAt:  now,
		},
		broadcast: broadcast,
	}
}

// ─── Reads (safe under RLock) ─────────────────────────────────────────────────

func (r *Room) ID() string {
	r.mu.RLock()
	defer r.mu.RUnlock()
	return r.data.ID
}

func (r *Room) Code() string {
	r.mu.RLock()
	defer r.mu.RUnlock()
	return r.data.Code
}

func (r *Room) State() models.RoomState {
	r.mu.RLock()
	defer r.mu.RUnlock()
	return r.data.State
}

func (r *Room) Type() models.RoomType {
	r.mu.RLock()
	defer r.mu.RUnlock()
	return r.data.Type
}

func (r *Room) PlayerCount() int {
	r.mu.RLock()
	defer r.mu.RUnlock()
	return len(r.data.Players)
}

func (r *Room) HasPlayer(userID string) bool {
	r.mu.RLock()
	defer r.mu.RUnlock()
	_, ok := r.data.Players[userID]
	return ok
}

// View returns a safe public projection of the room (no board values).
func (r *Room) View() models.RoomView {
	r.mu.RLock()
	defer r.mu.RUnlock()
	players := make(map[string]*models.PlayerView, len(r.data.Players))
	for uid, p := range r.data.Players {
		players[uid] = &models.PlayerView{
			UserID:      p.UserID,
			DisplayName: p.DisplayName,
			Ready:       p.Ready,
			CellsFilled: p.CellsFilled,
			Connected:   p.Connected,
			IsBot:       p.IsBot,
		}
	}
	return models.RoomView{
		ID:         r.data.ID,
		Code:       r.data.Code,
		Type:       r.data.Type,
		State:      r.data.State,
		Difficulty: r.data.Difficulty,
		Players:    players,
		CreatedAt:  r.data.CreatedAt,
		StartedAt:  r.data.StartedAt,
		FinishedAt: r.data.FinishedAt,
		WinnerID:   r.data.WinnerID,
		EndReason:  r.data.EndReason,
	}
}

// ─── Player Lifecycle ─────────────────────────────────────────────────────────

// ErrRoomFull is returned when a player tries to join a full room.
var ErrRoomFull = fmt.Errorf("room is full")

// ErrRoomNotWaiting is returned when a join is attempted on a non-waiting room.
var ErrRoomNotWaiting = fmt.Errorf("room is not accepting players")

// AddPlayer adds a player to the room. Returns an error if the room is full or not waiting.
func (r *Room) AddPlayer(p *models.Player, maxPlayers int) error {
	r.mu.Lock()
	defer r.mu.Unlock()

	if r.data.State != models.StateWaiting {
		return ErrRoomNotWaiting
	}
	if len(r.data.Players) >= maxPlayers {
		return ErrRoomFull
	}
	p.Connected = true
	r.data.Players[p.UserID] = p
	return nil
}

// RemovePlayer removes a player from a waiting room (never called during in_progress;
// use MarkDisconnected for in-game drops).
func (r *Room) RemovePlayer(userID string) {
	r.mu.Lock()
	defer r.mu.Unlock()
	delete(r.data.Players, userID)
}

// MarkConnected marks a player as reconnected and clears their disconnect timestamp.
func (r *Room) MarkConnected(userID string) {
	r.mu.Lock()
	defer r.mu.Unlock()
	if p, ok := r.data.Players[userID]; ok {
		p.Connected = true
		p.DisconnectedAt = nil
	}
}

// MarkDisconnected marks a player as disconnected and records the time.
func (r *Room) MarkDisconnected(userID string) {
	r.mu.Lock()
	defer r.mu.Unlock()
	if p, ok := r.data.Players[userID]; ok {
		now := time.Now().UTC()
		p.Connected = false
		p.DisconnectedAt = &now
	}
}

// DisconnectedAt returns when the player disconnected, or zero time if connected.
func (r *Room) DisconnectedAt(userID string) time.Time {
	r.mu.RLock()
	defer r.mu.RUnlock()
	if p, ok := r.data.Players[userID]; ok && p.DisconnectedAt != nil {
		return *p.DisconnectedAt
	}
	return time.Time{}
}

// ─── Ready System ─────────────────────────────────────────────────────────────

// SetReady updates a player's ready status and returns whether all players are now ready.
func (r *Room) SetReady(userID string, ready bool) (allReady bool, err error) {
	r.mu.Lock()
	defer r.mu.Unlock()

	p, ok := r.data.Players[userID]
	if !ok {
		return false, fmt.Errorf("player %s not in room", userID)
	}
	p.Ready = ready

	if r.data.State != models.StateWaiting && r.data.State != models.StateCountdown {
		return false, nil
	}

	// All players must be ready and room must have max players.
	if len(r.data.Players) < 2 {
		return false, nil
	}
	for _, pl := range r.data.Players {
		if !pl.Ready {
			return false, nil
		}
	}
	return true, nil
}

// StartCountdown transitions the room to countdown state.
func (r *Room) StartCountdown(cancel func()) {
	r.mu.Lock()
	defer r.mu.Unlock()
	r.data.State = models.StateCountdown
	r.countdownCancel = cancel
}

// CancelCountdown transitions the room back to waiting and cancels the countdown.
func (r *Room) CancelCountdown() {
	r.mu.Lock()
	cancel := r.countdownCancel
	r.countdownCancel = nil
	r.data.State = models.StateWaiting
	r.mu.Unlock()

	if cancel != nil {
		cancel()
	}
}

// StartGame transitions the room to in_progress.
func (r *Room) StartGame() {
	r.mu.Lock()
	defer r.mu.Unlock()
	now := time.Now().UTC()
	r.data.State = models.StateInProgress
	r.data.StartedAt = &now
	r.countdownCancel = nil
}

// ─── Cell Fill ────────────────────────────────────────────────────────────────

// ErrInvalidCell is returned for out-of-bounds cell index.
var ErrInvalidCell = fmt.Errorf("invalid cell index")

// ErrInvalidValue is returned for a digit outside 1–9.
var ErrInvalidValue = fmt.Errorf("invalid digit value")

// ErrWrongState is returned when an action is invalid for the current room state.
var ErrWrongState = fmt.Errorf("action not valid in current room state")

// ApplyCell records a cell fill from a player. Returns whether the move is correct
// and whether the puzzle is now complete.
func (r *Room) ApplyCell(userID string, cellIndex, value int) (correct, complete bool, err error) {
	if cellIndex < 0 || cellIndex >= 81 {
		return false, false, ErrInvalidCell
	}
	if value < 1 || value > 9 {
		return false, false, ErrInvalidValue
	}

	r.mu.Lock()
	defer r.mu.Unlock()

	if r.data.State != models.StateInProgress {
		return false, false, ErrWrongState
	}

	p, ok := r.data.Players[userID]
	if !ok {
		return false, false, fmt.Errorf("player %s not in room", userID)
	}

	correct = r.data.Solution[cellIndex] == value
	if correct {
		p.Board[cellIndex] = value
		p.CellsFilled++

		// Check puzzle completion: all 81 solution cells match.
		complete = p.CellsFilled == r.filledCount()
		if !complete {
			// Count how many non-zero solution cells exist.
			solutionCells := 0
			for _, v := range r.data.Solution {
				if v != 0 {
					solutionCells++
				}
			}
			complete = p.CellsFilled == solutionCells
		}
	}
	return correct, complete, nil
}

// filledCount returns the number of cells in the solution that need to be filled.
// Must be called with mu held.
func (r *Room) filledCount() int {
	count := 0
	for _, v := range r.data.Solution {
		if v != 0 {
			count++
		}
	}
	return count
}

// ─── Game End ─────────────────────────────────────────────────────────────────

// Finish transitions the room to finished state.
func (r *Room) Finish(winnerID string, reason models.EndReason) {
	r.mu.Lock()
	defer r.mu.Unlock()

	if r.data.State == models.StateFinished {
		return // idempotent
	}
	now := time.Now().UTC()
	r.data.State = models.StateFinished
	r.data.FinishedAt = &now
	r.data.WinnerID = winnerID
	r.data.EndReason = reason
}

// IsFinished returns true if the room is in the finished state.
func (r *Room) IsFinished() bool {
	r.mu.RLock()
	defer r.mu.RUnlock()
	return r.data.State == models.StateFinished
}

// CreatedAt returns the room creation timestamp for duration metrics.
func (r *Room) CreatedAt() time.Time {
	r.mu.RLock()
	defer r.mu.RUnlock()
	return r.data.CreatedAt
}

// Puzzle returns the puzzle array for broadcasting at game start.
func (r *Room) Puzzle() ([81]int, string) {
	r.mu.RLock()
	defer r.mu.RUnlock()
	return r.data.Puzzle, r.data.Difficulty
}

// PlayerIDs returns all player user IDs in the room.
func (r *Room) PlayerIDs() []string {
	r.mu.RLock()
	defer r.mu.RUnlock()
	ids := make([]string, 0, len(r.data.Players))
	for id := range r.data.Players {
		ids = append(ids, id)
	}
	return ids
}

// OpponentID returns the userID of the other player (for a 2-player room).
func (r *Room) OpponentID(myUserID string) string {
	r.mu.RLock()
	defer r.mu.RUnlock()
	for id := range r.data.Players {
		if id != myUserID {
			return id
		}
	}
	return ""
}

// BroadcastRoomState sends the current room view to all players.
func (r *Room) BroadcastRoomState() {
	view := r.View()
	r.broadcast(r.data.ID, models.OutboundMessage{
		Type:    models.MsgRoomState,
		Payload: view,
	})
}
