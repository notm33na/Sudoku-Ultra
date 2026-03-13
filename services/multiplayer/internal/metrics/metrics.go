package metrics

import (
	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promauto"
)

var (
	// ActiveRooms tracks the current number of open rooms (any state).
	ActiveRooms = promauto.NewGauge(prometheus.GaugeOpts{
		Namespace: "multiplayer",
		Name:      "active_rooms",
		Help:      "Number of rooms currently open (waiting, countdown, or in_progress).",
	})

	// ConnectedPlayers tracks the current number of live WebSocket connections.
	ConnectedPlayers = promauto.NewGauge(prometheus.GaugeOpts{
		Namespace: "multiplayer",
		Name:      "connected_players",
		Help:      "Number of players with an active WebSocket connection.",
	})

	// MatchmakingQueueSize tracks how many players are waiting for a public match.
	MatchmakingQueueSize = promauto.NewGauge(prometheus.GaugeOpts{
		Namespace: "multiplayer",
		Name:      "matchmaking_queue_size",
		Help:      "Number of players currently in the public matchmaking queue.",
	})

	// MessagesTotal counts WebSocket messages by direction and type.
	MessagesTotal = promauto.NewCounterVec(prometheus.CounterOpts{
		Namespace: "multiplayer",
		Name:      "messages_total",
		Help:      "Total WebSocket messages processed, by direction (inbound|outbound) and type.",
	}, []string{"direction", "type"})

	// RoomDuration records how long rooms last from creation to finish.
	RoomDuration = promauto.NewHistogram(prometheus.HistogramOpts{
		Namespace: "multiplayer",
		Name:      "room_duration_seconds",
		Help:      "Duration of completed game rooms from creation to finish.",
		Buckets:   prometheus.DefBuckets,
	})

	// RoomsCreatedTotal counts rooms created by type.
	RoomsCreatedTotal = promauto.NewCounterVec(prometheus.CounterOpts{
		Namespace: "multiplayer",
		Name:      "rooms_created_total",
		Help:      "Total rooms created, by type (public|private|bot).",
	}, []string{"type"})

	// DisconnectsTotal counts player disconnects and whether they reconnected.
	DisconnectsTotal = promauto.NewCounterVec(prometheus.CounterOpts{
		Namespace: "multiplayer",
		Name:      "disconnects_total",
		Help:      "Total player disconnects, by outcome (reconnected|forfeited).",
	}, []string{"outcome"})
)
