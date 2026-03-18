/**
 * k6 load test — multiplayer WebSocket service.
 *
 * Models a realistic player session:
 *   1. HTTP: POST /rooms  (create or join a room)
 *   2. WS:   connect to /rooms/:id/ws
 *   3. WS:   send cell_update messages every 2–5 s
 *   4. WS:   receive and check server messages
 *   5. WS:   disconnect after 30–90 s
 *
 * Run:
 *   k6 run \
 *     --env MULTIPLAYER_URL=http://localhost:3002 \
 *     --env MULTIPLAYER_WS=ws://localhost:3002 \
 *     --env AUTH_TOKEN=<jwt> \
 *     k6/scripts/multiplayer.js
 */

import http          from 'k6/http';
import ws            from 'k6/ws';
import { check, sleep } from 'k6';
import { Counter, Trend } from 'k6/metrics';
import { MULTIPLAYER_URL, MULTIPLAYER_WS, AUTH_TOKEN, WS_OPTIONS } from '../config.js';

// ── Custom metrics ─────────────────────────────────────────────────────────────
const wsMessagesReceived = new Counter('ws_msgs_received');
const wsMessagesSent     = new Counter('ws_msgs_sent');
const wsErrors           = new Counter('ws_errors');
const roomCreateDuration = new Trend('room_create_duration', true);

export const options = {
    ...WS_OPTIONS,
    thresholds: {
        ...WS_OPTIONS.thresholds,
        ws_errors:         ['count<10'],   // allow a few connection errors in load
        room_create_duration: ['p(95)<800'],
    },
};

const authHeaders = {
    'Content-Type':  'application/json',
    'Authorization': `Bearer ${AUTH_TOKEN}`,
};

const PUZZLES = [
    // Minimal valid puzzle for room creation
    Array(81).fill(0).map((_, i) => (i % 9 === i % 3 ? 1 : 0)),
];

// ── Room creation ──────────────────────────────────────────────────────────────
function createRoom() {
    const start = Date.now();
    const res = http.post(
        `${MULTIPLAYER_URL}/rooms`,
        JSON.stringify({
            puzzleId:   `load-test-puzzle-${__VU}`,
            difficulty: 'medium',
            mode:       'private',
        }),
        { headers: authHeaders, timeout: '10s' },
    );
    roomCreateDuration.add(Date.now() - start);

    check(res, {
        'room created (201) or exists (200/409)': (r) =>
            [200, 201, 409].includes(r.status),
    });

    if (res.status === 201 || res.status === 200) {
        try {
            return res.json('id') || res.json('roomId');
        } catch {
            return null;
        }
    }
    return null;
}

// ── WebSocket session ──────────────────────────────────────────────────────────
function runWsSession(roomId) {
    if (!roomId) return;

    const wsUrl = `${MULTIPLAYER_WS}/rooms/${roomId}/ws?token=${AUTH_TOKEN}`;
    const sessionDuration = Math.random() * 60_000 + 30_000;  // 30–90 s
    const startedAt = Date.now();

    const res = ws.connect(wsUrl, {}, function (socket) {
        socket.on('open', () => {
            // Send initial join message
            socket.send(JSON.stringify({ type: 'join', roomId }));
            wsMessagesSent.add(1);
        });

        socket.on('message', (data) => {
            wsMessagesReceived.add(1);
            try {
                const msg = JSON.parse(data);
                check(msg, {
                    'ws message has type': (m) => typeof m.type === 'string',
                });
            } catch {
                wsErrors.add(1);
            }
        });

        socket.on('error', () => {
            wsErrors.add(1);
        });

        // Send periodic cell updates
        socket.setInterval(() => {
            if (Date.now() - startedAt >= sessionDuration) {
                socket.close();
                return;
            }
            const row  = Math.floor(Math.random() * 9);
            const col  = Math.floor(Math.random() * 9);
            const val  = Math.floor(Math.random() * 9) + 1;
            socket.send(JSON.stringify({
                type:  'cell_update',
                roomId,
                row,
                col,
                value: val,
            }));
            wsMessagesSent.add(1);
        }, Math.random() * 3000 + 2000);   // every 2–5 s

        socket.setTimeout(() => {
            socket.close();
        }, sessionDuration);
    });

    check(res, {
        'ws connected successfully': (r) => r && r.status === 101,
    });
}

// ── Main ───────────────────────────────────────────────────────────────────────
export default function () {
    const roomId = createRoom();
    sleep(0.5);
    runWsSession(roomId);
    sleep(Math.random() * 2 + 1);  // cool-down before next iteration
}
