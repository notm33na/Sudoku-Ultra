/**
 * Friend routes — social layer.
 *
 * POST /api/friends/request             — send a friend request
 * POST /api/friends/:id/accept          — accept a pending request
 * POST /api/friends/:id/decline         — decline a pending request
 * POST /api/friends/:id/block           — block a user
 * GET  /api/friends                     — list accepted friends
 * GET  /api/friends/pending             — list incoming pending requests
 * GET  /api/friends/feed                — paginated activity feed
 * GET  /api/friends/leaderboard         — friends + self leaderboard (Elo)
 */

import { Router, Request, Response, NextFunction } from 'express';
import { z } from 'zod';
import { authenticate } from '../middleware/auth';
import * as svc from '../services/friend.service';

const router = Router();
router.use(authenticate);

// ── POST /api/friends/request ─────────────────────────────────────────────────

const requestSchema = z.object({ addresseeId: z.string().uuid() });

router.post(
    '/request',
    async (req: Request, res: Response, next: NextFunction): Promise<void> => {
        try {
            const parsed = requestSchema.safeParse(req.body);
            if (!parsed.success) {
                res.status(400).json({ error: parsed.error.flatten() });
                return;
            }
            const requesterId = (req as any).user.id as string;
            const result = await svc.sendFriendRequest(requesterId, parsed.data.addresseeId);
            res.status(201).json(result);
        } catch (err: any) {
            if (err?.statusCode) {
                res.status(err.statusCode).json({ error: err.message });
                return;
            }
            next(err);
        }
    },
);

// ── POST /api/friends/:id/accept ──────────────────────────────────────────────

router.post(
    '/:id/accept',
    async (req: Request, res: Response, next: NextFunction): Promise<void> => {
        try {
            const currentUserId = (req as any).user.id as string;
            await svc.acceptFriendRequest(req.params.id, currentUserId);
            res.json({ message: 'Friend request accepted.' });
        } catch (err: any) {
            if (err?.statusCode) {
                res.status(err.statusCode).json({ error: err.message });
                return;
            }
            next(err);
        }
    },
);

// ── POST /api/friends/:id/decline ─────────────────────────────────────────────

router.post(
    '/:id/decline',
    async (req: Request, res: Response, next: NextFunction): Promise<void> => {
        try {
            const currentUserId = (req as any).user.id as string;
            await svc.declineFriendRequest(req.params.id, currentUserId);
            res.json({ message: 'Friend request declined.' });
        } catch (err: any) {
            if (err?.statusCode) {
                res.status(err.statusCode).json({ error: err.message });
                return;
            }
            next(err);
        }
    },
);

// ── POST /api/friends/:id/block ───────────────────────────────────────────────

router.post(
    '/:id/block',
    async (req: Request, res: Response, next: NextFunction): Promise<void> => {
        try {
            const blockerId = (req as any).user.id as string;
            await svc.blockUser(blockerId, req.params.id);
            res.json({ message: 'User blocked.' });
        } catch (err: any) {
            if (err?.statusCode) {
                res.status(err.statusCode).json({ error: err.message });
                return;
            }
            next(err);
        }
    },
);

// ── GET /api/friends ──────────────────────────────────────────────────────────

router.get(
    '/',
    async (req: Request, res: Response, next: NextFunction): Promise<void> => {
        try {
            const userId = (req as any).user.id as string;
            const friends = await svc.listFriends(userId);
            res.json({ friends, count: friends.length });
        } catch (err) {
            next(err);
        }
    },
);

// ── GET /api/friends/pending ──────────────────────────────────────────────────

router.get(
    '/pending',
    async (req: Request, res: Response, next: NextFunction): Promise<void> => {
        try {
            const userId = (req as any).user.id as string;
            const requests = await svc.listPendingRequests(userId);
            res.json({ requests, count: requests.length });
        } catch (err) {
            next(err);
        }
    },
);

// ── GET /api/friends/feed ─────────────────────────────────────────────────────

const feedQuerySchema = z.object({
    limit: z.coerce.number().int().min(1).max(50).default(30),
    cursor: z.string().optional(),
});

router.get(
    '/feed',
    async (req: Request, res: Response, next: NextFunction): Promise<void> => {
        try {
            const userId = (req as any).user.id as string;
            const parsed = feedQuerySchema.safeParse(req.query);
            if (!parsed.success) {
                res.status(400).json({ error: parsed.error.flatten() });
                return;
            }
            const { limit, cursor } = parsed.data;
            const result = await svc.getActivityFeed(userId, limit, cursor);
            res.json(result);
        } catch (err) {
            next(err);
        }
    },
);

// ── GET /api/friends/leaderboard ──────────────────────────────────────────────

router.get(
    '/leaderboard',
    async (req: Request, res: Response, next: NextFunction): Promise<void> => {
        try {
            const userId = (req as any).user.id as string;
            const entries = await svc.getFriendsLeaderboard(userId);
            res.json({ entries, count: entries.length });
        } catch (err) {
            next(err);
        }
    },
);

export default router;
