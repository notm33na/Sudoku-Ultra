/**
 * pact.routes.ts — Provider state setup endpoint for Pact contract testing.
 *
 * Registered in app.ts ONLY when NODE_ENV=test.
 * The Pact Verifier POSTs to /_pact/provider-states before each interaction
 * to ensure the required DB state exists.
 *
 * Body: { state: string; params?: Record<string, unknown> }
 */

import { Router, Request, Response } from 'express';
import bcrypt from 'bcryptjs';
import { prisma } from '../prisma/client';

const router = Router();

// ─── Seed helpers ─────────────────────────────────────────────────────────────

const TEST_PASSWORD_HASH = bcrypt.hashSync('password123', 8);

/** Upsert the canonical test user. Returns the user record. */
async function seedTestUser() {
    return prisma.user.upsert({
        where: { email: 'test@example.com' },
        update: {},
        create: {
            email: 'test@example.com',
            username: 'testuser',
            passwordHash: TEST_PASSWORD_HASH,
            skillCluster: 'Intermediate',
        },
    });
}

/** Upsert a secondary user used as friend/actor. Returns the user record. */
async function seedFriendUser(index: number) {
    return prisma.user.upsert({
        where: { email: `friend${index}@example.com` },
        update: {},
        create: {
            email: `friend${index}@example.com`,
            username: `frienduser${index}`,
            passwordHash: TEST_PASSWORD_HASH,
        },
    });
}

// ─── State handlers ───────────────────────────────────────────────────────────

const stateHandlers: Record<string, () => Promise<void>> = {
    /**
     * No-op: the service is always running when this endpoint is reachable.
     */
    'game-service is running': async () => {
        // Nothing to seed.
    },

    /**
     * Ensure a user with email test@example.com exists in the database so that
     * the login interaction can succeed or return 401 as expected.
     */
    'a user exists with email test@example.com': async () => {
        await seedTestUser();
    },

    /**
     * Ensure a user exists and has a non-zero streak so that GET /api/home
     * returns streak data.
     */
    'an authenticated user with a streak': async () => {
        const user = await seedTestUser();
        await prisma.streak.upsert({
            where: { userId: user.id },
            update: { currentStreak: 3, longestStreak: 7, freezeCount: 0 },
            create: {
                userId: user.id,
                currentStreak: 3,
                longestStreak: 7,
                freezeCount: 0,
                lastPlayedDate: new Date(),
            },
        });
        // Ensure PlayerRating exists (home route may query it).
        await prisma.playerRating.upsert({
            where: { userId: user.id },
            update: {},
            create: { userId: user.id, eloRating: 1200 },
        });
    },

    /**
     * Ensure a user exists with two accepted friendships so that
     * GET /api/friends returns a non-empty list.
     */
    'an authenticated user with two friends': async () => {
        const user = await seedTestUser();
        const friend1 = await seedFriendUser(1);
        const friend2 = await seedFriendUser(2);

        // Ensure PlayerRating rows exist for all three users (leaderboard queries).
        for (const u of [user, friend1, friend2]) {
            await prisma.playerRating.upsert({
                where: { userId: u.id },
                update: {},
                create: { userId: u.id, eloRating: 1200 },
            });
        }

        // Upsert accepted friendships (both directions handled by unique constraint).
        await prisma.friendship.upsert({
            where: { requesterId_addresseeId: { requesterId: user.id, addresseeId: friend1.id } },
            update: { status: 'accepted' },
            create: { requesterId: user.id, addresseeId: friend1.id, status: 'accepted' },
        });
        await prisma.friendship.upsert({
            where: { requesterId_addresseeId: { requesterId: user.id, addresseeId: friend2.id } },
            update: { status: 'accepted' },
            create: { requesterId: user.id, addresseeId: friend2.id, status: 'accepted' },
        });
    },

    /**
     * Ensure a user exists with at least one activity feed entry so that
     * GET /api/friends/feed returns a non-empty entries array.
     */
    'an authenticated user with activity in their feed': async () => {
        const user = await seedTestUser();
        const actor = await seedFriendUser(1);

        // One puzzle_completed activity owned by the test user, actor = friend.
        await prisma.activityFeed.create({
            data: {
                userId: user.id,
                actorId: actor.id,
                type: 'puzzle_completed',
                payload: { difficulty: 'medium', score: 850, timeElapsedMs: 120000 },
            },
        });
    },
};

// ─── Route ────────────────────────────────────────────────────────────────────

router.post('/', async (req: Request, res: Response) => {
    const { state } = req.body as { state?: string };

    if (!state) {
        res.status(400).json({ error: 'Missing state in request body' });
        return;
    }

    const handler = stateHandlers[state];
    if (!handler) {
        // Unknown states are silently accepted so unknown interactions don't
        // hard-fail the entire verification run.
        res.status(200).json({ state, status: 'unhandled' });
        return;
    }

    try {
        await handler();
        res.status(200).json({ state, status: 'ok' });
    } catch (err) {
        const message = err instanceof Error ? err.message : String(err);
        res.status(500).json({ state, error: message });
    }
});

export default router;
