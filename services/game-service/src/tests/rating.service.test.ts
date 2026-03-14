/**
 * rating.service.test.ts — Tests for rating service with mocked Prisma and Redis.
 */

// ── Mocks ──────────────────────────────────────────────────────────────────────

// Mock Prisma client.
jest.mock('../prisma/client', () => ({
    prisma: {
        multiplayerMatch: {
            findFirst: jest.fn(),
            create: jest.fn(),
        },
        playerRating: {
            upsert: jest.fn(),
            update: jest.fn(),
            findUnique: jest.fn(),
            findMany: jest.fn(),
            count: jest.fn(),
        },
        user: {
            findMany: jest.fn(),
        },
        $transaction: jest.fn(),
    },
}));

// Mock Redis.
jest.mock('../lib/redis', () => ({
    LEADERBOARD_KEY: 'leaderboard:global',
    getRedis: jest.fn(() => ({
        zadd: jest.fn().mockResolvedValue(1),
        zrevrange: jest.fn().mockResolvedValue([]),
        zcard: jest.fn().mockResolvedValue(0),
        zrevrank: jest.fn().mockResolvedValue(null),
    })),
}));

import { prisma } from '../prisma/client';
import { recordMatchResult, getPlayerRating } from '../services/rating.service';

// Cast to any: new Prisma models (playerRating, multiplayerMatch) are not yet
// in the generated client types — they'll appear after `prisma generate`.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const mockPrisma = prisma as any;

// ── recordMatchResult ──────────────────────────────────────────────────────────

describe('recordMatchResult', () => {
    const validInput = {
        roomId: 'room-1',
        winnerId: 'user-winner',
        loserId: 'user-loser',
        endReason: 'completed' as const,
        durationMs: 120000,
        difficulty: 'easy',
    };

    beforeEach(() => {
        jest.clearAllMocks();
    });

    it('returns existing match data for duplicate roomId (idempotent)', async () => {
        const existing = {
            id: 'match-existing',
            roomId: 'room-1',
            winnerId: 'user-winner',
            loserId: 'user-loser',
            winnerEloBefore: 1200,
            winnerEloAfter: 1216,
            loserEloBefore: 1200,
            loserEloAfter: 1184,
            endReason: 'completed',
            durationMs: 120000,
            difficulty: 'easy',
            createdAt: new Date(),
        };

        (mockPrisma.multiplayerMatch.findFirst as jest.Mock).mockResolvedValue(existing);

        const result = await recordMatchResult(validInput);
        expect(result.matchId).toBe('match-existing');
        expect(result.winnerEloAfter).toBe(1216);
        // Transaction must NOT be called for a duplicate.
        expect(mockPrisma.$transaction).not.toHaveBeenCalled();
    });

    it('upserts ratings and creates match for a new room', async () => {
        (mockPrisma.multiplayerMatch.findFirst as jest.Mock).mockResolvedValue(null);

        const winnerRating = { userId: 'user-winner', eloRating: 1200, wins: 5, losses: 3 };
        const loserRating = { userId: 'user-loser', eloRating: 1200, wins: 2, losses: 4 };

        (mockPrisma.playerRating.upsert as jest.Mock)
            .mockResolvedValueOnce(winnerRating)
            .mockResolvedValueOnce(loserRating);

        const createdMatch = {
            id: 'match-new',
            winnerEloBefore: 1200,
            winnerEloAfter: 1216,
            loserEloBefore: 1200,
            loserEloAfter: 1184,
        };

        (mockPrisma.$transaction as jest.Mock).mockImplementation(async (fn: Function) => {
            const txMock = {
                playerRating: { update: jest.fn().mockResolvedValue({}) },
                multiplayerMatch: { create: jest.fn().mockResolvedValue(createdMatch) },
            };
            return fn(txMock);
        });

        const result = await recordMatchResult(validInput);
        expect(result.matchId).toBe('match-new');
        expect(result.winnerEloAfter).toBeGreaterThan(result.winnerEloBefore);
        expect(result.loserEloAfter).toBeLessThan(result.loserEloBefore);
        expect(result.delta).toBeGreaterThan(0);
    });

    it('delta equals winnerEloAfter - winnerEloBefore', async () => {
        (mockPrisma.multiplayerMatch.findFirst as jest.Mock).mockResolvedValue(null);
        (mockPrisma.playerRating.upsert as jest.Mock)
            .mockResolvedValueOnce({ userId: 'u1', eloRating: 1300, wins: 0, losses: 0 })
            .mockResolvedValueOnce({ userId: 'u2', eloRating: 1400, wins: 0, losses: 0 });

        let capturedMatch: any;
        (mockPrisma.$transaction as jest.Mock).mockImplementation(async (fn: Function) => {
            const txMock = {
                playerRating: { update: jest.fn().mockResolvedValue({}) },
                multiplayerMatch: {
                    create: jest.fn().mockImplementation(async ({ data }: any) => {
                        capturedMatch = {
                            id: 'm1',
                            winnerEloBefore: data.winnerEloBefore,
                            winnerEloAfter: data.winnerEloAfter,
                            loserEloBefore: data.loserEloBefore,
                            loserEloAfter: data.loserEloAfter,
                        };
                        return capturedMatch;
                    }),
                },
            };
            return fn(txMock);
        });

        const result = await recordMatchResult(validInput);
        expect(result.delta).toBe(result.winnerEloAfter - result.winnerEloBefore);
    });
});

// ── getPlayerRating ───────────────────────────────────────────────────────────

describe('getPlayerRating', () => {
    beforeEach(() => {
        jest.clearAllMocks();
    });

    it('returns null when player has no rating row', async () => {
        (mockPrisma.playerRating.findUnique as jest.Mock).mockResolvedValue(null);
        const result = await getPlayerRating('unknown-user');
        expect(result).toBeNull();
    });

    it('returns full profile when rating exists', async () => {
        (mockPrisma.playerRating.findUnique as jest.Mock).mockResolvedValue({
            userId: 'u1',
            eloRating: 1450,
            wins: 10,
            losses: 4,
            lastMatchAt: new Date('2026-01-01T12:00:00Z'),
            user: { username: 'Alice', avatarUrl: null },
        });

        const result = await getPlayerRating('u1');
        expect(result).not.toBeNull();
        expect(result!.username).toBe('Alice');
        expect(result!.eloRating).toBe(1450);
        expect(result!.wins).toBe(10);
        expect(result!.losses).toBe(4);
    });

    it('computes winRate correctly', async () => {
        (mockPrisma.playerRating.findUnique as jest.Mock).mockResolvedValue({
            userId: 'u1',
            eloRating: 1200,
            wins: 3,
            losses: 1,
            lastMatchAt: null,
            user: { username: 'Bob', avatarUrl: null },
        });

        const result = await getPlayerRating('u1');
        expect(result!.winRate).toBeCloseTo(0.75);
    });

    it('returns winRate=0 for player with no matches', async () => {
        (mockPrisma.playerRating.findUnique as jest.Mock).mockResolvedValue({
            userId: 'u1',
            eloRating: 1200,
            wins: 0,
            losses: 0,
            lastMatchAt: null,
            user: { username: 'New', avatarUrl: null },
        });

        const result = await getPlayerRating('u1');
        expect(result!.winRate).toBe(0);
    });

    it('returns lastMatchAt as ISO string when set', async () => {
        const date = new Date('2026-03-14T10:00:00Z');
        (mockPrisma.playerRating.findUnique as jest.Mock).mockResolvedValue({
            userId: 'u1',
            eloRating: 1200,
            wins: 1,
            losses: 0,
            lastMatchAt: date,
            user: { username: 'Alice', avatarUrl: null },
        });

        const result = await getPlayerRating('u1');
        expect(result!.lastMatchAt).toBe(date.toISOString());
    });
});
