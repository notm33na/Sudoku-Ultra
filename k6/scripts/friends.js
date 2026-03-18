/**
 * k6 load test — friends & social layer.
 *
 * Scenario mix:
 *   50 % — GET /api/friends (list)
 *   25 % — GET /api/friends/feed
 *   15 % — GET /api/friends/leaderboard
 *   10 % — GET /api/friends/pending
 *
 * Run: k6 run --env BASE_URL=http://localhost:3001 \
 *              --env AUTH_TOKEN=<jwt> \
 *              k6/scripts/friends.js
 */

import http from 'k6/http';
import { check, group, sleep } from 'k6';
import { BASE_URL, authHeaders, LOAD_OPTIONS } from '../config.js';

export const options = {
    ...LOAD_OPTIONS,
    thresholds: {
        'http_req_failed':   ['rate<0.01'],
        'http_req_duration': ['p(95)<400'],
        'http_req_duration{group:::feed}': ['p(95)<600'],
    },
};

export default function () {
    const roll = Math.random();

    if (roll < 0.50) {
        group('friends-list', () => {
            const r = http.get(`${BASE_URL}/api/friends`, { headers: authHeaders() });
            check(r, { 'friends list 200': (res) => res.status === 200 });
        });
    } else if (roll < 0.75) {
        group('feed', () => {
            const r = http.get(`${BASE_URL}/api/friends/feed?limit=20`, { headers: authHeaders() });
            check(r, {
                'feed 200': (res) => res.status === 200,
                'feed has entries key': (res) => Array.isArray(res.json('entries')),
            });
        });
    } else if (roll < 0.90) {
        group('leaderboard', () => {
            const r = http.get(`${BASE_URL}/api/friends/leaderboard`, { headers: authHeaders() });
            check(r, {
                'leaderboard 200': (res) => res.status === 200,
                'leaderboard has entries': (res) => Array.isArray(res.json('entries')),
            });
        });
    } else {
        group('pending', () => {
            const r = http.get(`${BASE_URL}/api/friends/pending`, { headers: authHeaders() });
            check(r, { 'pending 200': (res) => res.status === 200 });
        });
    }

    sleep(Math.random() * 1.5 + 0.5);
}
