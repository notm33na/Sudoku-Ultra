/**
 * k6 smoke test — validates all core endpoints are reachable and respond
 * within acceptable latency before a production deployment.
 *
 * Run: k6 run --env BASE_URL=http://localhost:3001 \
 *              --env ML_URL=http://localhost:3003 \
 *              --env AUTH_TOKEN=<jwt> \
 *              k6/scripts/smoke.js
 */

import http from 'k6/http';
import { check, group, sleep } from 'k6';
import { BASE_URL, ML_URL, authHeaders, SMOKE_OPTIONS } from '../config.js';

export const options = SMOKE_OPTIONS;

export default function () {
    // ── Health checks ─────────────────────────────────────────────────────────
    group('health', () => {
        const r = http.get(`${BASE_URL}/health`);
        check(r, {
            'game-service healthy': (res) => res.status === 200,
            'game-service ok body': (res) => res.json('status') === 'ok',
        });

        const ml = http.get(`${ML_URL}/health`);
        check(ml, {
            'ml-service healthy': (res) => res.status === 200,
        });
    });

    sleep(0.5);

    // ── Auth ──────────────────────────────────────────────────────────────────
    group('auth', () => {
        const r = http.post(
            `${BASE_URL}/api/auth/login`,
            JSON.stringify({ email: 'smoke@test.com', password: 'smoketest123' }),
            { headers: { 'Content-Type': 'application/json' } },
        );
        // 200 = success, 401 = wrong creds (test user may not exist — both acceptable for smoke)
        check(r, { 'auth endpoint reachable': (res) => [200, 401, 422].includes(res.status) });
    });

    sleep(0.5);

    // ── Home ──────────────────────────────────────────────────────────────────
    group('home', () => {
        const r = http.get(`${BASE_URL}/api/home`, { headers: authHeaders() });
        check(r, { 'home reachable': (res) => [200, 401].includes(res.status) });
    });

    sleep(1);
}
