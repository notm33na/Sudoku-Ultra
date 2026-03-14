/**
 * rating.routes.ts — Service-to-service REST endpoint for recording match results.
 *
 * Route:
 *   POST /api/ratings/match-result
 *
 * Authentication:
 *   Requires `X-Internal-Secret` header matching config.INTERNAL_SECRET.
 *   This endpoint is NOT exposed to the public internet — it is called only
 *   by the Go multiplayer service after a game ends.
 *
 * Body: MatchResultInput (JSON)
 * Response: 201 with RecordedMatch data.
 */

import { Router, Request, Response, NextFunction } from 'express';
import { z } from 'zod';
import { config } from '../config';
import { recordMatchResult, getPlayerRating } from '../services/rating.service';

const router = Router();

// ── Internal auth middleware ──────────────────────────────────────────────────

function requireInternalSecret(req: Request, res: Response, next: NextFunction): void {
    const secret = req.headers['x-internal-secret'];
    if (!secret || secret !== config.INTERNAL_SECRET) {
        res.status(401).json({ error: 'Unauthorized' });
        return;
    }
    next();
}

// ── Validation schema ─────────────────────────────────────────────────────────

const matchResultSchema = z.object({
    roomId: z.string().min(1),
    winnerId: z.string().min(1),
    loserId: z.string().min(1),
    endReason: z.enum(['completed', 'forfeit', 'timeout']),
    durationMs: z.number().int().nonnegative(),
    difficulty: z.string().min(1),
});

// ── POST /api/ratings/match-result ───────────────────────────────────────────

router.post(
    '/match-result',
    requireInternalSecret,
    async (req: Request, res: Response, next: NextFunction): Promise<void> => {
        try {
            const parsed = matchResultSchema.safeParse(req.body);
            if (!parsed.success) {
                res.status(400).json({ error: parsed.error.flatten() });
                return;
            }

            const result = await recordMatchResult(parsed.data);
            res.status(201).json(result);
        } catch (err) {
            next(err);
        }
    },
);

// ── GET /api/ratings/:userId ──────────────────────────────────────────────────

router.get(
    '/:userId',
    async (req: Request, res: Response, next: NextFunction): Promise<void> => {
        try {
            const rating = await getPlayerRating(req.params.userId);
            if (!rating) {
                res.status(404).json({ error: 'Player rating not found' });
                return;
            }
            res.json(rating);
        } catch (err) {
            next(err);
        }
    },
);

export default router;
