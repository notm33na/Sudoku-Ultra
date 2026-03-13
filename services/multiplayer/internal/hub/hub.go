package hub

import (
	"encoding/json"
	"sync"
	"time"

	"github.com/gorilla/websocket"
	"go.uber.org/zap"

	"github.com/sudoku-ultra/multiplayer/internal/metrics"
	"github.com/sudoku-ultra/multiplayer/internal/models"
)

const (
	writeWait      = 10 * time.Second
	pongWait       = 60 * time.Second
	pingPeriod     = (pongWait * 9) / 10
	maxMessageSize = 4096
)

// Client represents a single WebSocket connection.
type Client struct {
	hub    *Hub
	conn   *websocket.Conn
	send   chan []byte
	UserID string
	RoomID string
}

// Hub manages all WebSocket clients grouped by room.
type Hub struct {
	mu      sync.RWMutex
	clients map[string]*Client            // userID → Client
	rooms   map[string]map[string]*Client // roomID → userID → Client

	register   chan *Client
	unregister chan *Client
	broadcast  chan roomMsg

	log *zap.Logger

	// onDisconnect is called when a client drops. Injected by main.
	onDisconnect func(roomID, userID string)

	// onMessage is the inbound message dispatcher. Injected by main.
	onMessage func(roomID, userID string, msg models.InboundMessage)
}

type roomMsg struct {
	roomID string
	data   []byte
}

// New creates a Hub and starts its run loop.
func New(
	log *zap.Logger,
	onDisconnect func(roomID, userID string),
	onMessage func(roomID, userID string, msg models.InboundMessage),
) *Hub {
	h := &Hub{
		clients:      make(map[string]*Client),
		rooms:        make(map[string]map[string]*Client),
		register:     make(chan *Client, 64),
		unregister:   make(chan *Client, 64),
		broadcast:    make(chan roomMsg, 512),
		log:          log,
		onDisconnect: onDisconnect,
		onMessage:    onMessage,
	}
	go h.run()
	return h
}

// run is the Hub's main event loop — all channel operations happen here.
func (h *Hub) run() {
	for {
		select {

		case c := <-h.register:
			h.mu.Lock()
			h.clients[c.UserID] = c
			if h.rooms[c.RoomID] == nil {
				h.rooms[c.RoomID] = make(map[string]*Client)
			}
			h.rooms[c.RoomID][c.UserID] = c
			h.mu.Unlock()
			metrics.ConnectedPlayers.Inc()
			h.log.Info("client registered", zap.String("user_id", c.UserID), zap.String("room_id", c.RoomID))

		case c := <-h.unregister:
			h.mu.Lock()
			if _, ok := h.clients[c.UserID]; ok {
				delete(h.clients, c.UserID)
				if roomClients, ok := h.rooms[c.RoomID]; ok {
					delete(roomClients, c.UserID)
					if len(roomClients) == 0 {
						delete(h.rooms, c.RoomID)
					}
				}
				close(c.send)
			}
			h.mu.Unlock()
			metrics.ConnectedPlayers.Dec()
			h.log.Info("client unregistered", zap.String("user_id", c.UserID), zap.String("room_id", c.RoomID))
			h.onDisconnect(c.RoomID, c.UserID)

		case msg := <-h.broadcast:
			h.mu.RLock()
			roomClients := h.rooms[msg.roomID]
			h.mu.RUnlock()
			for _, c := range roomClients {
				select {
				case c.send <- msg.data:
				default:
					// Buffer full — client is too slow; drop the connection.
					h.log.Warn("client send buffer full, dropping", zap.String("user_id", c.UserID))
					close(c.send)
					h.mu.Lock()
					delete(h.clients, c.UserID)
					delete(h.rooms[c.RoomID], c.UserID)
					h.mu.Unlock()
					metrics.ConnectedPlayers.Dec()
				}
			}
		}
	}
}

// Broadcast sends a message to all clients in a room.
func (h *Hub) Broadcast(roomID string, msg models.OutboundMessage) {
	data, err := json.Marshal(msg)
	if err != nil {
		h.log.Error("failed to marshal broadcast message", zap.Error(err))
		return
	}
	metrics.MessagesTotal.WithLabelValues("outbound", string(msg.Type)).Inc()
	h.broadcast <- roomMsg{roomID: roomID, data: data}
}

// Send sends a message to a single client by userID.
func (h *Hub) Send(userID string, msg models.OutboundMessage) {
	data, err := json.Marshal(msg)
	if err != nil {
		h.log.Error("failed to marshal message", zap.Error(err))
		return
	}
	h.mu.RLock()
	c, ok := h.clients[userID]
	h.mu.RUnlock()
	if !ok {
		return
	}
	metrics.MessagesTotal.WithLabelValues("outbound", string(msg.Type)).Inc()
	select {
	case c.send <- data:
	default:
		h.log.Warn("send buffer full for user", zap.String("user_id", userID))
	}
}

// Register adds a new client to the hub.
func (h *Hub) Register(c *Client) {
	h.register <- c
}

// Unregister removes a client from the hub.
func (h *Hub) Unregister(c *Client) {
	h.unregister <- c
}

// NewClient creates a Client and wires it to this hub.
func (h *Hub) NewClient(conn *websocket.Conn, userID, roomID string) *Client {
	return &Client{
		hub:    h,
		conn:   conn,
		send:   make(chan []byte, 256),
		UserID: userID,
		RoomID: roomID,
	}
}

// ─── Client I/O Pumps ────────────────────────────────────────────────────────

// ReadPump reads messages from the WebSocket and dispatches them.
// Must be run in its own goroutine.
func (c *Client) ReadPump() {
	defer func() {
		c.hub.Unregister(c)
		c.conn.Close()
	}()

	c.conn.SetReadLimit(maxMessageSize)
	c.conn.SetReadDeadline(time.Now().Add(pongWait))
	c.conn.SetPongHandler(func(string) error {
		c.conn.SetReadDeadline(time.Now().Add(pongWait))
		return nil
	})

	for {
		_, data, err := c.conn.ReadMessage()
		if err != nil {
			if websocket.IsUnexpectedCloseError(err, websocket.CloseGoingAway, websocket.CloseAbnormalClosure) {
				c.hub.log.Warn("websocket read error", zap.String("user_id", c.UserID), zap.Error(err))
			}
			return
		}

		var msg models.InboundMessage
		if err := json.Unmarshal(data, &msg); err != nil {
			c.hub.log.Warn("malformed inbound message", zap.String("user_id", c.UserID), zap.Error(err))
			continue
		}
		metrics.MessagesTotal.WithLabelValues("inbound", string(msg.Type)).Inc()
		c.hub.onMessage(c.RoomID, c.UserID, msg)
	}
}

// WritePump drains the send channel to the WebSocket connection.
// Must be run in its own goroutine.
func (c *Client) WritePump() {
	ticker := time.NewTicker(pingPeriod)
	defer func() {
		ticker.Stop()
		c.conn.Close()
	}()

	for {
		select {
		case msg, ok := <-c.send:
			c.conn.SetWriteDeadline(time.Now().Add(writeWait))
			if !ok {
				// Hub closed the channel.
				c.conn.WriteMessage(websocket.CloseMessage, []byte{})
				return
			}
			if err := c.conn.WriteMessage(websocket.TextMessage, msg); err != nil {
				return
			}

		case <-ticker.C:
			c.conn.SetWriteDeadline(time.Now().Add(writeWait))
			if err := c.conn.WriteMessage(websocket.PingMessage, nil); err != nil {
				return
			}
		}
	}
}
