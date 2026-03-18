/**
 * k6 load test — game-service core flows.
 *
 * Scenario mix:
 *   60 % — GET /api/home + puzzle recommendations
 *   20 % — POST /api/sessions (create) + GET session
 *   15 % — GET /api/scores leaderboard
 *    5 % — GET /api/daily
 *
 * Run: k6 run --env BASE_URL=http://localhost:3001 \
 *              --env AUTH_TOKEN=<jwt> \
 *              k6/scripts/game.js
 */

import http from 'k6/http';
import { check, group, sleep } from 'k6';
import { BASE_URL, authHeaders, LOAD_OPTIONS } from '../config.js';

export const options = {
    ...LOAD_OPTIONS,
    thresholds: {
        'http_req_failed':                     ['rate<0.01'],
        'http_req_duration':                   ['p(95)<500'],
        'http_req_duration{group:::home}':     ['p(95)<300'],
        'http_req_duration{group:::sessions}': ['p(95)<600'],
        'http_req_duration{group:::scores}':   ['p(95)<400'],
    },
};

const PUZZLE_IDS = __ENV.PUZZLE_IDS ? __ENV.PUZZLE_IDS.split(',') : [];

export default function () {
    const roll = Math.random();

    if (roll < 0.60) {
        group('home', () => {
            const r = http.get(`${BASE_URL}/api/home`, { headers: authHeaders() });
            check(r, { 'home 200': (res) => res.status === 200 });
        });
    } else if (roll < 0.80) {
        group('sessions', () => {
            if (PUZZLE_IDS.length === 0) return;
            const puzzleId = PUZZLE_IDS[Math.floor(Math.random() * PUZZLE_IDS.length)];
            const create = http.post(
                `${BASE_URL}/api/sessions`,
                JSON.stringify({ puzzleId }),
                { headers: authHeaders() },
            );
            check(create, { 'session created': (res) => res.status === 201 });

            if (create.status === 201) {
                const sessionId = create.json('id');
                const get = http.get(`${BASE_URL}/api/sessions/${sessionId}`, { headers: authHeaders() });
                check(get, { 'session GET 200': (res) => res.status === 200 });
            }
        });
    } else if (roll < 0.95) {
        group('scores', () => {
            const r = http.get(`${BASE_URL}/api/scores?limit=20`, { headers: authHeaders() });
            check(r, { 'scores 200': (res) => res.status === 200 });
        });
    } else {
        group('daily', () => {
            const r = http.get(`${BASE_URL}/api/daily`, { headers: authHeaders() });
            check(r, { 'daily reachable': (res) => [200, 404].includes(res.status) });
        });
    }

    sleep(Math.random() * 2 + 0.5);  // 0.5–2.5 s think time
}
