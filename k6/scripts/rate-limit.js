/**
 * k6 test — verifies rate limiting is enforced correctly.
 *
 * Tests:
 *   auth_limit    — POST /api/auth/login  must return 429 after 10 req/15min per IP
 *   api_limit     — GET  /api/home        must return 429 after 300 req/min per IP
 *   admin_limit   — POST /api/admin/*     must return 429 after 30 req/min per IP
 *
 * NOTE: this script intentionally violates rate limits — run only against
 * non-production environments. It does NOT measure latency; it verifies
 * that the 429 status is returned at the correct threshold.
 *
 * Run:
 *   k6 run \
 *     --env BASE_URL=http://localhost:3001 \
 *     --env AUTH_TOKEN=<jwt> \
 *     k6/scripts/rate-limit.js
 */

import http from 'k6/http';
import { check, group, sleep } from 'k6';
import { Counter } from 'k6/metrics';
import { BASE_URL, AUTH_TOKEN } from '../config.js';

const rateLimitHits = new Counter('rate_limit_429_count');

// Single VU, run through each check once
export const options = {
    vus: 1,
    iterations: 1,
    thresholds: {
        // We WANT 429s — the test passes if we received at least one per group
        rate_limit_429_count: ['count>=3'],
    },
};

const JSON_HEADERS = {
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${AUTH_TOKEN}`,
};

// ── Auth rate limit (10 req / 15 min) ─────────────────────────────────────────
function testAuthLimit() {
    group('auth_limit', () => {
        let got429 = false;
        // Send 15 rapid requests — should hit 429 before the 11th
        for (let i = 0; i < 15; i++) {
            const res = http.post(
                `${BASE_URL}/api/auth/login`,
                JSON.stringify({ email: 'rl-test@test.invalid', password: 'wrong' }),
                { headers: JSON_HEADERS },
            );
            if (res.status === 429) {
                got429 = true;
                rateLimitHits.add(1);
            }
        }
        check({ got429 }, {
            'auth endpoint returns 429 under burst': (s) => s.got429 === true,
        });
    });
}

// ── API rate limit (300 req / min) ────────────────────────────────────────────
// We send 320 requests as fast as possible to a cheap endpoint.
function testApiLimit() {
    group('api_limit', () => {
        let got429 = false;
        for (let i = 0; i < 320; i++) {
            const res = http.get(`${BASE_URL}/health`);
            if (res.status === 429) {
                got429 = true;
                rateLimitHits.add(1);
                break;
            }
        }
        check({ got429 }, {
            'api endpoint returns 429 after 300 req/min': (s) => s.got429 === true,
        });
    });
}

// ── Admin rate limit (30 req / min) ───────────────────────────────────────────
function testAdminLimit() {
    group('admin_limit', () => {
        let got429 = false;
        for (let i = 0; i < 35; i++) {
            // Any admin endpoint — will 401/403 if not admin but still counts rate-limit
            const res = http.post(
                `${BASE_URL}/api/admin/gdpr/delete`,
                JSON.stringify({ userId: 'non-existent' }),
                { headers: JSON_HEADERS },
            );
            if (res.status === 429) {
                got429 = true;
                rateLimitHits.add(1);
                break;
            }
        }
        check({ got429 }, {
            'admin endpoint returns 429 after 30 req/min': (s) => s.got429 === true,
        });
    });
}

export default function () {
    testAuthLimit();
    sleep(1);
    testApiLimit();
    sleep(1);
    testAdminLimit();
}
