/**
 * k6 load test — ml-service endpoints.
 *
 * These endpoints are more expensive; run with lower VU counts.
 *
 * Scenario mix:
 *   40 % — POST /api/v1/xai/cell-importance
 *   30 % — POST /api/v1/gan/generate
 *   20 % — POST /api/v1/search/puzzles/similar-features
 *   10 % — POST /api/v1/tutor/hint
 *
 * Run: k6 run --env ML_URL=http://localhost:3003 \
 *              k6/scripts/ml.js
 */

import http from 'k6/http';
import { check, group, sleep } from 'k6';
import { ML_URL, LOAD_OPTIONS } from '../config.js';

// ML endpoints are slower — relax p95 threshold.
export const options = {
    stages: [
        { duration: '1m', target: 10 },
        { duration: '3m', target: 10 },
        { duration: '1m', target: 0  },
    ],
    thresholds: {
        'http_req_failed':   ['rate<0.02'],
        'http_req_duration': ['p(95)<5000'],   // ML can take a while
        'http_req_duration{group:::xai}':   ['p(95)<3000'],
        'http_req_duration{group:::gan}':   ['p(95)<8000'],
        'http_req_duration{group:::search}':['p(95)<2000'],
    },
};

// ── Test boards ───────────────────────────────────────────────────────────────

// Solved board (for XAI — board = puzzle state, puzzle = original)
const SOLVED_BOARD = [
    5,3,4,6,7,8,9,1,2, 6,7,2,1,9,5,3,4,8, 1,9,8,3,4,2,5,6,7,
    8,5,9,7,6,1,4,2,3, 4,2,6,8,5,3,7,9,1, 7,1,3,9,2,4,8,5,6,
    9,6,1,5,3,7,2,8,4, 2,8,7,4,1,9,6,3,5, 3,4,5,2,8,6,1,7,9,
];

const PUZZLE_BOARD = [
    5,3,0,0,7,0,0,0,0, 6,0,0,1,9,5,0,0,0, 0,9,8,0,0,0,0,6,0,
    8,0,0,0,6,0,0,0,3, 4,0,0,8,0,3,0,0,1, 7,0,0,0,2,0,0,0,6,
    0,6,0,0,0,0,2,8,0, 0,0,0,4,1,9,0,0,5, 0,0,0,0,8,0,0,7,9,
];

export default function () {
    const roll = Math.random();
    const headers = { 'Content-Type': 'application/json' };

    if (roll < 0.40) {
        group('xai', () => {
            const r = http.post(
                `${ML_URL}/api/v1/xai/cell-importance`,
                JSON.stringify({ board: SOLVED_BOARD, puzzle: PUZZLE_BOARD }),
                { headers },
            );
            check(r, {
                'xai 200': (res) => res.status === 200,
                'xai has cell_importances': (res) => Array.isArray(res.json('cell_importances')),
            });
        });
    } else if (roll < 0.70) {
        group('gan', () => {
            const r = http.post(
                `${ML_URL}/api/v1/gan/generate`,
                JSON.stringify({ mode: 'puzzle', difficulty: 'medium' }),
                { headers, timeout: '15s' },
            );
            check(r, {
                'gan 200': (res) => res.status === 200,
                'gan has puzzle': (res) => res.json('puzzle') !== null,
            });
        });
    } else if (roll < 0.90) {
        group('search', () => {
            const r = http.post(
                `${ML_URL}/api/v1/search/puzzles/similar-features`,
                JSON.stringify({
                    difficulty: 3,
                    clue_count: 28,
                    techniques: ['naked_singles', 'hidden_singles'],
                    top_k: 5,
                }),
                { headers },
            );
            check(r, {
                'search 200': (res) => res.status === 200,
                'search has results': (res) => Array.isArray(res.json('results')),
            });
        });
    } else {
        group('tutor', () => {
            const r = http.post(
                `${ML_URL}/api/v1/tutor/hint`,
                JSON.stringify({ board: PUZZLE_BOARD, mode: 'quick' }),
                { headers, timeout: '10s' },
            );
            check(r, {
                'tutor reachable': (res) => [200, 422, 503].includes(res.status),
            });
        });
    }

    sleep(Math.random() * 3 + 1);
}
