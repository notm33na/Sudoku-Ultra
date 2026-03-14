package main

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/go-chi/chi/v5"
	"github.com/gorilla/websocket"
	"go.uber.org/zap"

	"github.com/sudoku-ultra/multiplayer/internal/config"
	"github.com/sudoku-ultra/multiplayer/internal/handlers"
	"github.com/sudoku-ultra/multiplayer/internal/hub"
	"github.com/sudoku-ultra/multiplayer/internal/models"
	"github.com/sudoku-ultra/multiplayer/internal/room"
)

// ─── Fixtures ─────────────────────────────────────────────────────────────────

func testConfig() *config.Config {
	return &config.Config{
		Port:            "3002",
		GameServiceURL:  "http://localhost:9999",
		JWTSecret:       "dev-secret-change-in-production",
		MaxRoomPlayers:  2,
		CountdownSecs:   1,
		ReconnectWindow: 2 * time.Second,
	}
}

func testLogger() *zap.Logger {
	l, _ := zap.NewDevelopment()
	return l
}

func noopBroadcast(string, models.OutboundMessage) {}

// buildTestServer wires all components into a test HTTP server.
func buildTestServer(t *testing.T, cfg *config.Config) (*httptest.Server, *room.Manager) {
	t.Helper()
	m := room.NewManager(cfg, testLogger())

	var wsH *handlers.WS
	h := hub.New(
		testLogger(),
		func(rID, uID string) {
			if wsH != nil {
				wsH.OnDisconnect(rID, uID)
			}
		},
		func(rID, uID string, msg models.InboundMessage) {
			if wsH != nil {
				wsH.OnMessage(rID, uID, msg)
			}
		},
	)
	m.SetBroadcastFn(h.Broadcast)

	httpH := handlers.NewHTTP(m, cfg.JWTSecret, testLogger())
	wsH = handlers.NewWS(h, m, cfg.JWTSecret, testLogger())

	r := chi.NewRouter()
	r.Get("/health", healthHandler())
	r.Post("/rooms", httpH.CreateRoom)
	r.Get("/rooms/{id}", httpH.GetRoom)
	r.Post("/rooms/{id}/join", httpH.JoinRoom)
	r.Get("/rooms/{id}/ws", wsH.ServeWS)

	return httptest.NewServer(r), m
}

// ─── Room Unit Tests ──────────────────────────────────────────────────────────

func TestRoom_AddPlayer_UpToMax(t *testing.T) {
	r := room.NewRoom("r1", "", "u1", models.RoomTypePrivate, "medium",
		[81]int{}, [81]int{}, noopBroadcast)

	p1 := &models.Player{UserID: "u1", DisplayName: "Alice"}
	p2 := &models.Player{UserID: "u2", DisplayName: "Bob"}
	p3 := &models.Player{UserID: "u3", DisplayName: "Carol"}

	if err := r.AddPlayer(p1, 2); err != nil {
		t.Fatalf("add p1: %v", err)
	}
	if err := r.AddPlayer(p2, 2); err != nil {
		t.Fatalf("add p2: %v", err)
	}
	if err := r.AddPlayer(p3, 2); err == nil {
		t.Fatal("expected error adding 3rd player")
	}
}

func TestRoom_AddPlayer_RejectsNonWaiting(t *testing.T) {
	r := room.NewRoom("r1", "", "u1", models.RoomTypePrivate, "easy",
		[81]int{}, [81]int{}, noopBroadcast)

	r.StartGame()
	if err := r.AddPlayer(&models.Player{UserID: "u1"}, 2); err != room.ErrRoomNotWaiting {
		t.Fatalf("expected ErrRoomNotWaiting, got %v", err)
	}
}

func TestRoom_SetReady_AllReady(t *testing.T) {
	r := room.NewRoom("r1", "", "u1", models.RoomTypePrivate, "easy",
		[81]int{}, [81]int{}, noopBroadcast)
	r.AddPlayer(&models.Player{UserID: "u1"}, 2)
	r.AddPlayer(&models.Player{UserID: "u2"}, 2)

	allReady, _ := r.SetReady("u1", true)
	if allReady {
		t.Fatal("should not be allReady with only one player ready")
	}

	allReady, err := r.SetReady("u2", true)
	if err != nil || !allReady {
		t.Fatalf("expected allReady=true, got %v err=%v", allReady, err)
	}
}

func TestRoom_SetReady_SinglePlayer_NeverAllReady(t *testing.T) {
	r := room.NewRoom("r1", "", "u1", models.RoomTypePrivate, "easy",
		[81]int{}, [81]int{}, noopBroadcast)
	r.AddPlayer(&models.Player{UserID: "u1"}, 2)

	allReady, err := r.SetReady("u1", true)
	if err != nil {
		t.Fatalf("set ready: %v", err)
	}
	if allReady {
		t.Fatal("single player must never trigger allReady")
	}
}

func TestRoom_ApplyCell_CorrectValue(t *testing.T) {
	solution := [81]int{}
	for i := range solution {
		solution[i] = (i%9 + 1)
	}

	r := room.NewRoom("r1", "", "u1", models.RoomTypePrivate, "easy",
		[81]int{}, solution, noopBroadcast)
	r.AddPlayer(&models.Player{UserID: "u1"}, 2)
	r.StartGame()

	correct, complete, err := r.ApplyCell("u1", 0, solution[0])
	if err != nil || !correct || complete {
		t.Fatalf("correct=%v complete=%v err=%v", correct, complete, err)
	}
}

func TestRoom_ApplyCell_WrongValue(t *testing.T) {
	solution := [81]int{}
	solution[0] = 5

	r := room.NewRoom("r1", "", "u1", models.RoomTypePrivate, "easy",
		[81]int{}, solution, noopBroadcast)
	r.AddPlayer(&models.Player{UserID: "u1"}, 2)
	r.StartGame()

	correct, _, err := r.ApplyCell("u1", 0, 9)
	if err != nil || correct {
		t.Fatalf("expected correct=false, got %v err=%v", correct, err)
	}
}

func TestRoom_ApplyCell_InvalidIndex(t *testing.T) {
	r := room.NewRoom("r1", "", "u1", models.RoomTypePrivate, "easy",
		[81]int{}, [81]int{}, noopBroadcast)
	r.AddPlayer(&models.Player{UserID: "u1"}, 2)
	r.StartGame()

	_, _, err := r.ApplyCell("u1", 99, 5)
	if err != room.ErrInvalidCell {
		t.Fatalf("expected ErrInvalidCell, got %v", err)
	}
}

func TestRoom_ApplyCell_NotInProgress(t *testing.T) {
	r := room.NewRoom("r1", "", "u1", models.RoomTypePrivate, "easy",
		[81]int{}, [81]int{}, noopBroadcast)
	r.AddPlayer(&models.Player{UserID: "u1"}, 2)

	_, _, err := r.ApplyCell("u1", 0, 5)
	if err != room.ErrWrongState {
		t.Fatalf("expected ErrWrongState, got %v", err)
	}
}

func TestRoom_Finish_Idempotent(t *testing.T) {
	r := room.NewRoom("r1", "", "u1", models.RoomTypePrivate, "easy",
		[81]int{}, [81]int{}, noopBroadcast)
	r.Finish("u1", models.EndReasonCompleted)
	r.Finish("u2", models.EndReasonForfeit) // second call must be ignored

	if r.View().WinnerID != "u1" {
		t.Fatalf("expected winner u1, got %s", r.View().WinnerID)
	}
}

func TestRoom_DisconnectAndReconnect(t *testing.T) {
	r := room.NewRoom("r1", "", "u1", models.RoomTypePrivate, "easy",
		[81]int{}, [81]int{}, noopBroadcast)
	r.AddPlayer(&models.Player{UserID: "u1"}, 2)

	r.MarkDisconnected("u1")
	if r.DisconnectedAt("u1").IsZero() {
		t.Fatal("expected disconnect timestamp to be set")
	}

	r.MarkConnected("u1")
	if !r.DisconnectedAt("u1").IsZero() {
		t.Fatal("expected disconnect timestamp cleared after reconnect")
	}
}

func TestRoom_View_OnlyExposesPlayerView(t *testing.T) {
	solution := [81]int{}
	for i := range solution {
		solution[i] = (i%9 + 1)
	}
	r := room.NewRoom("r1", "", "u1", models.RoomTypePrivate, "easy",
		[81]int{}, solution, noopBroadcast)
	r.AddPlayer(&models.Player{UserID: "u1"}, 2)
	r.StartGame()
	r.ApplyCell("u1", 0, solution[0])

	pv, ok := r.View().Players["u1"]
	if !ok {
		t.Fatal("player not in view")
	}
	if pv.CellsFilled != 1 {
		t.Fatalf("expected CellsFilled=1, got %d", pv.CellsFilled)
	}
}

// ─── Manager Tests ────────────────────────────────────────────────────────────

func TestManager_GetRoom_NotFound(t *testing.T) {
	m := room.NewManager(testConfig(), testLogger())
	m.SetBroadcastFn(noopBroadcast)

	_, ok := m.Get("nonexistent")
	if ok {
		t.Fatal("expected false for nonexistent room")
	}
}

func TestManager_GetByCode_NotFound(t *testing.T) {
	m := room.NewManager(testConfig(), testLogger())
	m.SetBroadcastFn(noopBroadcast)

	_, ok := m.GetByCode("AAAAAA")
	if ok {
		t.Fatal("expected false for unknown code")
	}
}

func TestManager_JoinRoom_NotFound(t *testing.T) {
	m := room.NewManager(testConfig(), testLogger())
	m.SetBroadcastFn(noopBroadcast)

	_, err := m.JoinRoom("bad-id", "u1", "Alice")
	if err == nil {
		t.Fatal("expected error joining nonexistent room")
	}
}

func TestManager_Enqueue_SameDifficulty_Pairs(t *testing.T) {
	mockPuzzle := models.PuzzleResponse{Difficulty: "easy"}
	mockSrv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		json.NewEncoder(w).Encode(mockPuzzle)
	}))
	defer mockSrv.Close()

	cfg := testConfig()
	cfg.GameServiceURL = mockSrv.URL
	m := room.NewManager(cfg, testLogger())
	m.SetBroadcastFn(noopBroadcast)

	ctx := context.Background()

	rm1, err := m.Enqueue(ctx, "u1", "Alice", "easy")
	if err != nil || rm1 != nil {
		t.Fatalf("first enqueue: rm=%v err=%v", rm1, err)
	}

	rm2, err := m.Enqueue(ctx, "u2", "Bob", "easy")
	if err != nil {
		t.Fatalf("second enqueue: %v", err)
	}
	if rm2 == nil {
		t.Fatal("expected matched room on second enqueue")
	}
	if rm2.PlayerCount() != 2 {
		t.Fatalf("expected 2 players, got %d", rm2.PlayerCount())
	}
}

func TestManager_Enqueue_DifferentDifficulty_NoMatch(t *testing.T) {
	m := room.NewManager(testConfig(), testLogger())
	m.SetBroadcastFn(noopBroadcast)

	ctx := context.Background()
	m.Enqueue(ctx, "u1", "Alice", "easy")

	rm, err := m.Enqueue(ctx, "u2", "Bob", "hard")
	if err != nil || rm != nil {
		t.Fatalf("expected no match across difficulties: rm=%v err=%v", rm, err)
	}
}

func TestManager_DequeuePlayer_RemovesFromQueue(t *testing.T) {
	m := room.NewManager(testConfig(), testLogger())
	m.SetBroadcastFn(noopBroadcast)

	ctx := context.Background()
	m.Enqueue(ctx, "u1", "Alice", "easy")
	m.DequeuePlayer("u1")

	// A new player with same difficulty must not find a match.
	rm, err := m.Enqueue(ctx, "u2", "Bob", "easy")
	if err != nil || rm != nil {
		t.Fatalf("expected no match after dequeue: rm=%v err=%v", rm, err)
	}
}

// ─── HTTP Integration Tests ───────────────────────────────────────────────────

func TestHTTP_Health(t *testing.T) {
	srv, _ := buildTestServer(t, testConfig())
	defer srv.Close()

	resp, err := http.Get(srv.URL + "/health")
	if err != nil {
		t.Fatal(err)
	}
	if resp.StatusCode != http.StatusOK {
		t.Fatalf("expected 200, got %d", resp.StatusCode)
	}
}

func TestHTTP_GetRoom_NotFound(t *testing.T) {
	srv, _ := buildTestServer(t, testConfig())
	defer srv.Close()

	resp, err := http.Get(srv.URL + "/rooms/no-such-room")
	if err != nil {
		t.Fatal(err)
	}
	if resp.StatusCode != http.StatusNotFound {
		t.Fatalf("expected 404, got %d", resp.StatusCode)
	}
}

func TestHTTP_CreateRoom_MissingAuth(t *testing.T) {
	srv, _ := buildTestServer(t, testConfig())
	defer srv.Close()

	body := strings.NewReader(`{"difficulty":"easy","type":"private"}`)
	resp, err := http.Post(srv.URL+"/rooms", "application/json", body)
	if err != nil {
		t.Fatal(err)
	}
	if resp.StatusCode != http.StatusUnauthorized {
		t.Fatalf("expected 401, got %d", resp.StatusCode)
	}
}

func TestHTTP_CreateRoom_InvalidDifficulty(t *testing.T) {
	srv, _ := buildTestServer(t, testConfig())
	defer srv.Close()

	req, _ := http.NewRequest(http.MethodPost, srv.URL+"/rooms",
		strings.NewReader(`{"difficulty":"impossible","type":"private"}`))
	req.Header.Set("Authorization", "Bearer u1:Alice")
	req.Header.Set("Content-Type", "application/json")

	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		t.Fatal(err)
	}
	if resp.StatusCode != http.StatusBadRequest {
		t.Fatalf("expected 400, got %d", resp.StatusCode)
	}
}

func TestHTTP_JoinRoom_NotFound(t *testing.T) {
	srv, _ := buildTestServer(t, testConfig())
	defer srv.Close()

	req, _ := http.NewRequest(http.MethodPost, srv.URL+"/rooms/bad-id/join",
		strings.NewReader(`{}`))
	req.Header.Set("Authorization", "Bearer u1:Alice")
	req.Header.Set("Content-Type", "application/json")

	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		t.Fatal(err)
	}
	if resp.StatusCode != http.StatusNotFound {
		t.Fatalf("expected 404, got %d", resp.StatusCode)
	}
}

// ─── WebSocket Tests ──────────────────────────────────────────────────────────

func TestWS_NonexistentRoom_Returns404(t *testing.T) {
	srv, _ := buildTestServer(t, testConfig())
	defer srv.Close()

	wsURL := "ws" + strings.TrimPrefix(srv.URL, "http") + "/rooms/no-such-room/ws?token=u1:Alice"
	_, resp, err := websocket.DefaultDialer.Dial(wsURL, nil)
	if err == nil {
		t.Fatal("expected dial error for nonexistent room")
	}
	if resp != nil && resp.StatusCode != http.StatusNotFound {
		t.Fatalf("expected 404, got %d", resp.StatusCode)
	}
}

func TestWS_PingPong(t *testing.T) {
	// Set up a mock game-service so CreateRoom can fetch a puzzle.
	mockPuzzle := models.PuzzleResponse{Difficulty: "easy"}
	mockGameSrv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		json.NewEncoder(w).Encode(mockPuzzle)
	}))
	defer mockGameSrv.Close()

	cfg := testConfig()
	cfg.GameServiceURL = mockGameSrv.URL
	srv, m := buildTestServer(t, cfg)
	defer srv.Close()

	// Create a private room so we can connect to it.
	ctx := context.Background()
	rm, err := m.CreateRoom(ctx, "u1", models.CreateRoomRequest{
		Type:       models.RoomTypePrivate,
		Difficulty: "easy",
	})
	if err != nil {
		t.Fatalf("create room: %v", err)
	}

	wsURL := "ws" + strings.TrimPrefix(srv.URL, "http") +
		"/rooms/" + rm.ID() + "/ws?token=u1:Alice"

	conn, _, err := websocket.DefaultDialer.Dial(wsURL, nil)
	if err != nil {
		t.Fatalf("dial ws: %v", err)
	}
	defer conn.Close()

	// Send ping and expect pong.
	ping := models.OutboundMessage{Type: models.MsgPing}
	data, _ := json.Marshal(models.InboundMessage{Type: models.MsgPing})
	if err := conn.WriteMessage(websocket.TextMessage, data); err != nil {
		t.Fatalf("write ping: %v", err)
	}

	conn.SetReadDeadline(time.Now().Add(3 * time.Second))
	// Read messages until we see pong (first may be room_state).
	for i := 0; i < 3; i++ {
		_, raw, err := conn.ReadMessage()
		if err != nil {
			t.Fatalf("read: %v", err)
		}
		var out models.OutboundMessage
		json.Unmarshal(raw, &out)
		if out.Type == models.MsgPong {
			return // success
		}
	}
	_ = ping
	t.Fatal("did not receive pong within 3 messages")
}

// ─── Bot Room Tests ───────────────────────────────────────────────────────────

func TestRoom_BotTier_StoredAndRetrieved(t *testing.T) {
	r := room.NewRoom("r1", "", "u1", models.RoomTypeBot, "hard",
		[81]int{}, [81]int{}, noopBroadcast)
	r.SetBotTier("hard")
	if r.BotTier() != "hard" {
		t.Fatalf("expected BotTier=hard, got %q", r.BotTier())
	}
}

func TestRoom_BotBoard_ReturnsNilWithNoBot(t *testing.T) {
	r := room.NewRoom("r1", "", "u1", models.RoomTypePrivate, "easy",
		[81]int{}, [81]int{}, noopBroadcast)
	r.AddPlayer(&models.Player{UserID: "u1"}, 2)

	board, sol := r.BotBoard()
	if board != nil || sol != nil {
		t.Fatal("expected nil board and solution when no bot player")
	}
}

func TestRoom_BotBoard_ReturnsBotPlayerBoard(t *testing.T) {
	r := room.NewRoom("r1", "", "u1", models.RoomTypeBot, "easy",
		[81]int{}, [81]int{1: 5}, noopBroadcast)
	r.AddPlayer(&models.Player{UserID: "u1"}, 2)
	r.AddPlayer(&models.Player{UserID: "bot", IsBot: true}, 2)

	board, _ := r.BotBoard()
	if board == nil {
		t.Fatal("expected non-nil board for bot player")
	}
}

func TestManager_CreateBotRoom_HasTwoPlayers(t *testing.T) {
	mockPuzzle := models.PuzzleResponse{Difficulty: "easy"}
	mockSrv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		json.NewEncoder(w).Encode(mockPuzzle)
	}))
	defer mockSrv.Close()

	cfg := testConfig()
	cfg.GameServiceURL = mockSrv.URL
	m := room.NewManager(cfg, testLogger())
	m.SetBroadcastFn(noopBroadcast)

	rm, err := m.CreateBotRoom(
		context.Background(),
		"u1", "Alice", "medium",
		models.CreateRoomRequest{Type: models.RoomTypeBot, Difficulty: "easy"},
	)
	if err != nil {
		t.Fatalf("CreateBotRoom: %v", err)
	}
	if rm.PlayerCount() != 2 {
		t.Fatalf("expected 2 players (human + bot), got %d", rm.PlayerCount())
	}
}

func TestManager_CreateBotRoom_BotIsReadyHumanIsNot(t *testing.T) {
	mockSrv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		json.NewEncoder(w).Encode(models.PuzzleResponse{Difficulty: "medium"})
	}))
	defer mockSrv.Close()

	cfg := testConfig()
	cfg.GameServiceURL = mockSrv.URL
	m := room.NewManager(cfg, testLogger())
	m.SetBroadcastFn(noopBroadcast)

	rm, err := m.CreateBotRoom(
		context.Background(),
		"u1", "Alice", "easy",
		models.CreateRoomRequest{Type: models.RoomTypeBot, Difficulty: "medium"},
	)
	if err != nil {
		t.Fatalf("CreateBotRoom: %v", err)
	}

	view := rm.View()
	botReady, humanReady := false, false
	for _, p := range view.Players {
		if p.IsBot {
			botReady = p.Ready
		} else {
			humanReady = p.Ready
		}
	}
	if !botReady {
		t.Fatal("bot player must be ready immediately")
	}
	if humanReady {
		t.Fatal("human player must not be auto-ready")
	}
}

func TestConfig_BotDelayRange(t *testing.T) {
	cfg := testConfig()
	cases := []struct {
		tier   string
		minExp int
		maxExp int
	}{
		{"easy", 500, 2000},
		{"medium", 200, 500},
		{"hard", 100, 300},
		{"unknown", 500, 2000}, // defaults to easy range
	}
	for _, tc := range cases {
		min, max := cfg.BotDelayRange(tc.tier)
		if min != tc.minExp || max != tc.maxExp {
			t.Errorf("tier=%s: got [%d,%d], want [%d,%d]", tc.tier, min, max, tc.minExp, tc.maxExp)
		}
	}
}
