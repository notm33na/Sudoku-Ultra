/**
 * redis.ts — ioredis client singleton.
 *
 * Connects once at module load; all services import this instance.
 * In tests, the REDIS_URL defaults to redis://localhost:6379 which can be
 * overridden with an env var or mocked via jest.mock.
 */

import Redis from 'ioredis';
import { config } from '../config';

// ── Leaderboard Redis key helpers ──────────────────────────────────────────────

export const LEADERBOARD_KEY = 'leaderboard:global' as const;

// ── Client ────────────────────────────────────────────────────────────────────

let _redis: Redis | null = null;

export function getRedis(): Redis {
    if (!_redis) {
        _redis = new Redis(config.REDIS_URL, {
            maxRetriesPerRequest: 3,
            enableReadyCheck: true,
            lazyConnect: true,
        });

        _redis.on('error', (err: Error) => {
            // Log but don't crash — leaderboard is non-critical.
            console.error('[redis] connection error:', err.message);
        });
    }
    return _redis;
}

/** Close the connection. Call in tests or during graceful shutdown. */
export async function closeRedis(): Promise<void> {
    if (_redis) {
        await _redis.quit();
        _redis = null;
    }
}
