/**
 * k6 load test — end-to-end user journey.
 *
 * Simulates a complete realistic session:
 *   1. Register a unique test user (once per VU)
 *   2. Login → receive JWT
 *   3. GET /api/home
 *   4. GET /api/puzzles?difficulty=medium → pick a puzzle
 *   5. POST /api/sessions (start game)
 *   6. PATCH /api/sessions/:id  (3 moves)
 *   7. POST /api/sessions/:id/complete
 *   8. GET /api/scores?limit=10 (check leaderboard)
 *   9. POST /api/v1/xai/cell-importance (optional — 30% probability)
 *
 * Each VU represents one real user. The test verifies the critical path
 * works under concurrent load and that per-stage latencies meet SLOs.
 *
 * Run:
 *   k6 run \
 *     --env BASE_URL=http://localhost:3001 \
 *     --env ML_URL=http://localhost:3003 \
 *     k6/scripts/full-journey.js
 */

import http from 'k6/http';
import { check, group, sleep, fail } from 'k6';
import { Counter, Trend } from 'k6/metrics';
import { BASE_URL, ML_URL, LOAD_OPTIONS } from '../config.js';

// ── Custom metrics ─────────────────────────────────────────────────────────────
const journeyCompleted  = new Counter('journey_completed');
const journeyFailed     = new Counter('journey_failed');
const gameCompletionMs  = new Trend('game_completion_duration', true);

export const options = {
    ...LOAD_OPTIONS,
    thresholds: {
        'http_req_failed':                      ['rate<0.01'],
        'http_req_duration':                    ['p(95)<800'],
        'http_req_duration{group:::register}':  ['p(95)<600'],
        'http_req_duration{group:::login}':     ['p(95)<300'],
        'http_req_duration{group:::home}':      ['p(95)<300'],
        'http_req_duration{group:::puzzles}':   ['p(95)<400'],
        'http_req_duration{group:::session}':   ['p(95)<600'],
        'http_req_duration{group:::complete}':  ['p(95)<600'],
        'http_req_duration{group:::scores}':    ['p(95)<400'],
        journey_failed:                         ['count<5'],
    },
};

const BASE_HEADERS = { 'Content-Type': 'application/json' };

// ── Per-VU state ───────────────────────────────────────────────────────────────
let token    = null;
let userId   = null;
let email    = null;
let password = null;

function registerAndLogin() {
    // Each VU gets a unique account
    email    = `load-vu${__VU}-iter${__ITER}@test.invalid`;
    password = `Load_Test_Pass_${__VU}_${Date.now()}`;

    let jwt = null;

    group('register', () => {
        const res = http.post(
            `${BASE_URL}/api/auth/register`,
            JSON.stringify({ email, password, username: `loadvu${__VU}i${__ITER}` }),
            { headers: BASE_HEADERS },
        );
        const ok = check(res, {
            'register 201': (r) => r.status === 201,
            'register has token': (r) => r.json('data.token') !== undefined,
        });
        if (ok && res.status === 201) {
            jwt    = res.json('data.token');
            userId = res.json('data.user.id');
        }
    });

    if (!jwt) {
        // Fall back to login in case account already exists from a previous iteration
        group('login', () => {
            const res = http.post(
                `${BASE_URL}/api/auth/login`,
                JSON.stringify({ email, password }),
                { headers: BASE_HEADERS },
            );
            check(res, { 'login 200': (r) => r.status === 200 });
            if (res.status === 200) {
                jwt    = res.json('data.token');
                userId = res.json('data.user.id');
            }
        });
    }

    return jwt;
}

function authHeaders(jwt) {
    return { ...BASE_HEADERS, Authorization: `Bearer ${jwt}` };
}

// ── Journey ────────────────────────────────────────────────────────────────────
export default function () {
    const journeyStart = Date.now();

    // ── 1. Auth ────────────────────────────────────────────────────────────────
    token = registerAndLogin();
    if (!token) {
        journeyFailed.add(1);
        return;
    }
    const headers = authHeaders(token);
    sleep(0.5);

    // ── 2. Home ────────────────────────────────────────────────────────────────
    let puzzleId = null;
    group('home', () => {
        const res = http.get(`${BASE_URL}/api/home`, { headers });
        check(res, { 'home 200': (r) => r.status === 200 });
    });
    sleep(Math.random() * 1 + 0.3);

    // ── 3. Browse puzzles ──────────────────────────────────────────────────────
    group('puzzles', () => {
        const res = http.get(`${BASE_URL}/api/puzzles?difficulty=medium&limit=5`, { headers });
        const ok = check(res, {
            'puzzles 200': (r) => r.status === 200,
            'puzzles array': (r) => Array.isArray(r.json('data')),
        });
        if (ok) {
            const puzzles = res.json('data');
            if (puzzles && puzzles.length > 0) {
                puzzleId = puzzles[Math.floor(Math.random() * puzzles.length)].id;
            }
        }
    });

    if (!puzzleId) {
        journeyFailed.add(1);
        return;
    }
    sleep(Math.random() * 2 + 1);  // think time (user reads puzzle)

    // ── 4. Start game ──────────────────────────────────────────────────────────
    let sessionId = null;
    group('session', () => {
        const res = http.post(
            `${BASE_URL}/api/sessions`,
            JSON.stringify({ puzzleId }),
            { headers },
        );
        const ok = check(res, {
            'session created 201': (r) => r.status === 201,
            'session has id': (r) => r.json('id') !== undefined || r.json('data.id') !== undefined,
        });
        if (ok) {
            sessionId = res.json('id') || res.json('data.id');
        }
    });

    if (!sessionId) {
        journeyFailed.add(1);
        return;
    }

    // ── 5. Make moves (simulate 5–10 cell fills) ───────────────────────────────
    const moves = Math.floor(Math.random() * 6) + 5;
    for (let i = 0; i < moves; i++) {
        sleep(Math.random() * 3 + 1);   // 1–4 s between moves
        group('session', () => {
            http.patch(
                `${BASE_URL}/api/sessions/${sessionId}`,
                JSON.stringify({
                    row:   Math.floor(Math.random() * 9),
                    col:   Math.floor(Math.random() * 9),
                    value: Math.floor(Math.random() * 9) + 1,
                }),
                { headers },
            );
        });
    }

    // ── 6. Complete game ───────────────────────────────────────────────────────
    group('complete', () => {
        const res = http.post(
            `${BASE_URL}/api/sessions/${sessionId}/complete`,
            JSON.stringify({ timeMs: Date.now() - journeyStart }),
            { headers },
        );
        check(res, {
            'complete 200': (r) => [200, 201].includes(r.status),
        });
    });
    gameCompletionMs.add(Date.now() - journeyStart);
    sleep(0.5);

    // ── 7. Check leaderboard ───────────────────────────────────────────────────
    group('scores', () => {
        const res = http.get(`${BASE_URL}/api/scores?limit=10`, { headers });
        check(res, { 'scores 200': (r) => r.status === 200 });
    });
    sleep(0.5);

    // ── 8. Optional: XAI cell importance (30% of users) ───────────────────────
    if (Math.random() < 0.30) {
        group('xai', () => {
            http.post(
                `${ML_URL}/api/v1/xai/cell-importance`,
                JSON.stringify({
                    board:  Array(81).fill(1),
                    puzzle: Array(81).fill(0),
                }),
                { headers: BASE_HEADERS, timeout: '5s' },
            );
        });
    }

    journeyCompleted.add(1);
    sleep(Math.random() * 2 + 1);
}
