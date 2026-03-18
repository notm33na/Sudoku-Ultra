// ─────────────────────────────────────────────────────────────────────────────
// k6 shared config — Sudoku Ultra load tests
// ─────────────────────────────────────────────────────────────────────────────

export const BASE_URL = __ENV.BASE_URL || 'http://localhost:3001';
export const ML_URL   = __ENV.ML_URL   || 'http://localhost:3003';

// A pre-issued JWT for a seeded test user (set via CI secret / --env flag).
export const AUTH_TOKEN = __ENV.AUTH_TOKEN || '';

export function authHeaders() {
    return {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${AUTH_TOKEN}`,
    };
}

// ── Thresholds (shared defaults — override per script) ────────────────────────
export const DEFAULT_THRESHOLDS = {
    http_req_failed:   ['rate<0.01'],      // <1% error rate
    http_req_duration: ['p(95)<500'],      // 95th percentile <500 ms
};

// ── Smoke scenario — 1 VU, 30 s, sanity check ────────────────────────────────
export const SMOKE_OPTIONS = {
    vus: 1,
    duration: '30s',
    thresholds: DEFAULT_THRESHOLDS,
};

// ── Load scenario — ramp to 50 VUs over 2 min, hold 3 min, ramp down ─────────
export const LOAD_OPTIONS = {
    stages: [
        { duration: '2m', target: 50 },
        { duration: '3m', target: 50 },
        { duration: '1m', target: 0  },
    ],
    thresholds: DEFAULT_THRESHOLDS,
};

// ── Soak scenario — 20 VUs for 30 min ────────────────────────────────────────
export const SOAK_OPTIONS = {
    stages: [
        { duration: '2m', target: 20 },
        { duration: '28m', target: 20 },
        { duration: '1m', target: 0 },
    ],
    thresholds: {
        http_req_failed:   ['rate<0.01'],
        http_req_duration: ['p(95)<800'],   // slightly relaxed for soak
    },
};

// ── Stress scenario — ramp until breaking ────────────────────────────────────
export const STRESS_OPTIONS = {
    stages: [
        { duration: '2m', target: 50  },
        { duration: '2m', target: 100 },
        { duration: '2m', target: 150 },
        { duration: '2m', target: 200 },
        { duration: '2m', target: 0   },
    ],
    thresholds: {
        http_req_failed:   ['rate<0.05'],   // allow up to 5% errors under stress
        http_req_duration: ['p(95)<2000'],
    },
};
