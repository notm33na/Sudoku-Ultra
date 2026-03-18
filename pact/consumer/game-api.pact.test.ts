/**
 * Pact consumer contract — mobile app → game-service
 *
 * Defines the contract that the mobile consumer expects from the game-service
 * provider. The generated pact file at pact/pacts/ is verified by the provider
 * in the CI pipeline.
 *
 * Run consumer tests:  npx jest pact/consumer/game-api.pact.test.ts
 * Verify (provider):   npx jest pact/provider/game-service.verify.test.ts
 */

import { PactV3, MatchersV3 } from '@pact-foundation/pact';
import path from 'path';

const { like, eachLike, integer, string, boolean, timestamp } = MatchersV3;

const provider = new PactV3({
    consumer: 'mobile-app',
    provider: 'game-service',
    dir: path.resolve(__dirname, '../pacts'),
    logLevel: 'warn',
});

// ── GET /health ───────────────────────────────────────────────────────────────

describe('GET /health', () => {
    it('returns ok status', async () => {
        await provider
            .given('game-service is running')
            .uponReceiving('a health check request')
            .withRequest({ method: 'GET', path: '/health' })
            .willRespondWith({
                status: 200,
                headers: { 'Content-Type': 'application/json' },
                body: {
                    status: 'ok',
                    service: 'game-service',
                },
            })
            .executeTest(async (mockServer) => {
                const res = await fetch(`${mockServer.url}/health`);
                expect(res.status).toBe(200);
                const body = await res.json();
                expect(body.status).toBe('ok');
            });
    });
});

// ── POST /api/auth/login ──────────────────────────────────────────────────────

describe('POST /api/auth/login', () => {
    it('returns token on valid credentials', async () => {
        await provider
            .given('a user exists with email test@example.com')
            .uponReceiving('a login request with valid credentials')
            .withRequest({
                method: 'POST',
                path: '/api/auth/login',
                headers: { 'Content-Type': 'application/json' },
                body: { email: 'test@example.com', password: 'password123' },
            })
            .willRespondWith({
                status: 200,
                headers: { 'Content-Type': 'application/json' },
                body: {
                    token: string('eyJhbGciOiJIUzI1NiJ9.test'),
                    user: like({
                        id: string('uuid'),
                        email: 'test@example.com',
                        username: string('testuser'),
                    }),
                },
            })
            .executeTest(async (mockServer) => {
                const res = await fetch(`${mockServer.url}/api/auth/login`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ email: 'test@example.com', password: 'password123' }),
                });
                expect(res.status).toBe(200);
                const body = await res.json();
                expect(body).toHaveProperty('token');
                expect(body).toHaveProperty('user');
            });
    });

    it('returns 401 on invalid credentials', async () => {
        await provider
            .given('a user exists with email test@example.com')
            .uponReceiving('a login request with wrong password')
            .withRequest({
                method: 'POST',
                path: '/api/auth/login',
                headers: { 'Content-Type': 'application/json' },
                body: { email: 'test@example.com', password: 'wrongpassword' },
            })
            .willRespondWith({
                status: 401,
                headers: { 'Content-Type': 'application/json' },
                body: like({ error: string() }),
            })
            .executeTest(async (mockServer) => {
                const res = await fetch(`${mockServer.url}/api/auth/login`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ email: 'test@example.com', password: 'wrongpassword' }),
                });
                expect(res.status).toBe(401);
            });
    });
});

// ── GET /api/home ─────────────────────────────────────────────────────────────

describe('GET /api/home', () => {
    it('returns home data for an authenticated user', async () => {
        await provider
            .given('an authenticated user with a streak')
            .uponReceiving('a request for home data')
            .withRequest({
                method: 'GET',
                path: '/api/home',
                headers: { Authorization: like('Bearer token') },
            })
            .willRespondWith({
                status: 200,
                headers: { 'Content-Type': 'application/json' },
                body: {
                    data: like({
                        skillCluster: string('Intermediate'),
                        recommendedDifficulties: eachLike('medium'),
                        recommendations: eachLike({
                            id: string('uuid'),
                            difficulty: string('medium'),
                            clueCount: integer(30),
                            createdAt: string('2026-01-01T00:00:00.000Z'),
                        }),
                        streak: like({
                            currentStreak: integer(3),
                            longestStreak: integer(7),
                            freezeCount: integer(0),
                        }),
                    }),
                },
            })
            .executeTest(async (mockServer) => {
                const res = await fetch(`${mockServer.url}/api/home`, {
                    headers: { Authorization: 'Bearer test-token' },
                });
                expect(res.status).toBe(200);
                const body = await res.json();
                expect(body).toHaveProperty('data');
            });
    });
});

// ── GET /api/friends ──────────────────────────────────────────────────────────

describe('GET /api/friends', () => {
    it('returns friend list for authenticated user', async () => {
        await provider
            .given('an authenticated user with two friends')
            .uponReceiving('a request for friends list')
            .withRequest({
                method: 'GET',
                path: '/api/friends',
                headers: { Authorization: like('Bearer token') },
            })
            .willRespondWith({
                status: 200,
                headers: { 'Content-Type': 'application/json' },
                body: {
                    friends: eachLike({
                        userId: string('uuid'),
                        username: string('frienduser'),
                        avatarUrl: null,
                        friendshipId: string('uuid'),
                        since: string('2026-01-01T00:00:00.000Z'),
                        eloRating: integer(1200),
                    }),
                    count: integer(2),
                },
            })
            .executeTest(async (mockServer) => {
                const res = await fetch(`${mockServer.url}/api/friends`, {
                    headers: { Authorization: 'Bearer test-token' },
                });
                expect(res.status).toBe(200);
                const body = await res.json();
                expect(body).toHaveProperty('friends');
                expect(body).toHaveProperty('count');
            });
    });
});

// ── GET /api/friends/feed ─────────────────────────────────────────────────────

describe('GET /api/friends/feed', () => {
    it('returns paginated activity feed', async () => {
        await provider
            .given('an authenticated user with activity in their feed')
            .uponReceiving('a request for the activity feed')
            .withRequest({
                method: 'GET',
                path: '/api/friends/feed',
                query: { limit: '20' },
                headers: { Authorization: like('Bearer token') },
            })
            .willRespondWith({
                status: 200,
                headers: { 'Content-Type': 'application/json' },
                body: {
                    entries: eachLike({
                        id: string('uuid'),
                        actorId: string('uuid'),
                        actorUsername: string('testuser'),
                        actorAvatarUrl: null,
                        type: string('puzzle_completed'),
                        payload: like({}),
                        createdAt: string('2026-01-01T00:00:00.000Z'),
                    }),
                    nextCursor: null,
                },
            })
            .executeTest(async (mockServer) => {
                const res = await fetch(`${mockServer.url}/api/friends/feed?limit=20`, {
                    headers: { Authorization: 'Bearer test-token' },
                });
                expect(res.status).toBe(200);
                const body = await res.json();
                expect(body).toHaveProperty('entries');
                expect(Array.isArray(body.entries)).toBe(true);
            });
    });
});
