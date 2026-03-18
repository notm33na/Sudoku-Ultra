/**
 * rateLimiter.ts — Express rate-limit presets for game-service.
 *
 * Uses `express-rate-limit` (already in package.json).
 * All limits use an in-memory store; swap to RedisStore for multi-replica deployments.
 *
 * Presets:
 *   authLimiter     — 10 req / 15 min per IP  (brute-force protection on /api/auth)
 *   apiLimiter      — 300 req / 1 min per IP  (standard API routes)
 *   adminLimiter    — 30 req / 1 min per IP   (admin / sensitive endpoints)
 */

import rateLimit from 'express-rate-limit';

const IS_TEST = process.env.NODE_ENV === 'test';

/** Brute-force protection for authentication endpoints. */
export const authLimiter = rateLimit({
    windowMs: 15 * 60 * 1000,   // 15 minutes
    max: IS_TEST ? 10_000 : 10,
    standardHeaders: true,        // Return rate limit info in `RateLimit-*` headers
    legacyHeaders: false,
    message: {
        success: false,
        data: null,
        error: 'Too many authentication attempts. Please try again later.',
        timestamp: new Date().toISOString(),
    },
    skipSuccessfulRequests: true, // Only count failed / non-2xx requests
});

/** Standard limit for all API routes. */
export const apiLimiter = rateLimit({
    windowMs: 60 * 1000,          // 1 minute
    max: IS_TEST ? 10_000 : 300,
    standardHeaders: true,
    legacyHeaders: false,
    message: {
        success: false,
        data: null,
        error: 'Too many requests. Please slow down.',
        timestamp: new Date().toISOString(),
    },
});

/** Tighter limit for admin / GDPR endpoints. */
export const adminLimiter = rateLimit({
    windowMs: 60 * 1000,
    max: IS_TEST ? 10_000 : 30,
    standardHeaders: true,
    legacyHeaders: false,
    message: {
        success: false,
        data: null,
        error: 'Rate limit exceeded for admin endpoint.',
        timestamp: new Date().toISOString(),
    },
});
