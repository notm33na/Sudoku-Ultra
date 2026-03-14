/**
 * rating.service.ts — Multiplayer match recording and leaderboard management.
 *
 * Responsibilities:
 *   1. Upsert PlayerRating rows for winner and loser (default Elo 1200).
 *   2. Compute new Elo ratings.
 *   3. Persist updated ratings + MultiplayerMatch in a single Prisma transaction.
 *   4. Sync Redis global leaderboard (ZADD) for both players.
 *
 * Leaderboard Redis key: `leaderboard:global`
 *   ZADD score = eloRating, member = userId
 *   ZREVRANGE / ZREVRANK for top-N and rank lookups.
 */

import { prisma } from '../prisma/client';
import { getRedis, LEADERBOARD_KEY } from '../lib/redis';
import { computeElo } from './elo.service';

// ── Types ──────────────────────────────────────────────────────────────────────

export interface MatchResultInput {
    roomId: string;
    winnerId: string;
    loserId: string;
    endReason: string; // 'completed' | 'forfeit' | 'timeout'
    durationMs: number;
    difficulty: string;
}

export interface RecordedMatch {
    matchId: string;
    winnerEloBefore: number;
    winnerEloAfter: number;
    loserEloBefore: number;
    loserEloAfter: number;
    delta: number;
}

// ── Record Match ──────────────────────────────────────────────────────────────

const DEFAULT_ELO = 1200;

/**
 * Record the outcome of a completed multiplayer match.
 * Idempotent for a given roomId — if a match for that room already exists,
 * the function returns its stored data without re-applying Elo.
 */
export async function recordMatchResult(input: MatchResultInput): Promise<RecordedMatch> {
    // Idempotency: check if this room was already recorded.
    const existing = await prisma.multiplayerMatch.findFirst({
        where: { roomId: input.roomId },
    });
    if (existing) {
        return {
            matchId: existing.id,
            winnerEloBefore: existing.winnerEloBefore,
            winnerEloAfter: existing.winnerEloAfter,
            loserEloBefore: existing.loserEloBefore,
            loserEloAfter: existing.loserEloAfter,
            delta: existing.winnerEloAfter - existing.winnerEloBefore,
        };
    }

    // Fetch or default current ratings.
    const [winnerRating, loserRating] = await Promise.all([
        prisma.playerRating.upsert({
            where: { userId: input.winnerId },
            create: { userId: input.winnerId, eloRating: DEFAULT_ELO, wins: 0, losses: 0 },
            update: {},
        }),
        prisma.playerRating.upsert({
            where: { userId: input.loserId },
            create: { userId: input.loserId, eloRating: DEFAULT_ELO, wins: 0, losses: 0 },
            update: {},
        }),
    ]);

    const elo = computeElo(winnerRating.eloRating, loserRating.eloRating);
    const now = new Date();

    // Persist everything in a transaction.
    const match = await prisma.$transaction(async (tx) => {
        await tx.playerRating.update({
            where: { userId: input.winnerId },
            data: {
                eloRating: elo.winnerAfter,
                wins: { increment: 1 },
                lastMatchAt: now,
            },
        });

        await tx.playerRating.update({
            where: { userId: input.loserId },
            data: {
                eloRating: elo.loserAfter,
                losses: { increment: 1 },
                lastMatchAt: now,
            },
        });

        return tx.multiplayerMatch.create({
            data: {
                roomId: input.roomId,
                winnerId: input.winnerId,
                loserId: input.loserId,
                winnerEloBefore: elo.winnerBefore,
                winnerEloAfter: elo.winnerAfter,
                loserEloBefore: elo.loserBefore,
                loserEloAfter: elo.loserAfter,
                endReason: input.endReason,
                durationMs: input.durationMs,
                difficulty: input.difficulty,
            },
        });
    });

    // Sync Redis leaderboard (fire-and-forget — non-fatal on failure).
    syncLeaderboard(input.winnerId, elo.winnerAfter).catch(() => null);
    syncLeaderboard(input.loserId, elo.loserAfter).catch(() => null);

    return {
        matchId: match.id,
        winnerEloBefore: elo.winnerBefore,
        winnerEloAfter: elo.winnerAfter,
        loserEloBefore: elo.loserBefore,
        loserEloAfter: elo.loserAfter,
        delta: elo.delta,
    };
}

/** ZADD the player's new Elo to the global leaderboard sorted set. */
async function syncLeaderboard(userId: string, eloRating: number): Promise<void> {
    const redis = getRedis();
    await redis.zadd(LEADERBOARD_KEY, eloRating, userId);
}

// ── Leaderboard Query ─────────────────────────────────────────────────────────

export interface LeaderboardEntry {
    rank: number;
    userId: string;
    username: string;
    avatarUrl: string | null;
    eloRating: number;
    wins: number;
    losses: number;
    winRate: number;
}

export interface LeaderboardResult {
    entries: LeaderboardEntry[];
    total: number;
}

/**
 * Query the global leaderboard from Redis (sorted set) and enrich with
 * user + rating data from Postgres.
 *
 * Falls back to a Postgres-only query if Redis is unavailable.
 */
export async function getLeaderboard(
    limit = 20,
    offset = 0,
): Promise<LeaderboardResult> {
    const redis = getRedis();

    let userIds: string[];
    let total: number;

    try {
        // ZREVRANGE returns highest scores first.
        const start = offset;
        const stop = offset + limit - 1;
        [userIds, total] = await Promise.all([
            redis.zrevrange(LEADERBOARD_KEY, start, stop),
            redis.zcard(LEADERBOARD_KEY),
        ]);
    } catch {
        // Redis unavailable — fall back to Postgres.
        return getLeaderboardFromDb(limit, offset);
    }

    if (userIds.length === 0 && total === 0) {
        // Redis empty (e.g. first boot) — seed from Postgres.
        await seedLeaderboardFromDb();
        return getLeaderboardFromDb(limit, offset);
    }

    // Enrich with user + rating data.
    const [users, ratings] = await Promise.all([
        prisma.user.findMany({
            where: { id: { in: userIds } },
            select: { id: true, username: true, avatarUrl: true },
        }),
        prisma.playerRating.findMany({
            where: { userId: { in: userIds } },
            select: { userId: true, eloRating: true, wins: true, losses: true },
        }),
    ]);

    const userMap = new Map(users.map((u) => [u.id, u]));
    const ratingMap = new Map(ratings.map((r) => [r.userId, r]));

    const entries: LeaderboardEntry[] = userIds
        .map((uid, i) => {
            const user = userMap.get(uid);
            const rating = ratingMap.get(uid);
            if (!user || !rating) return null;
            const total_ = rating.wins + rating.losses;
            return {
                rank: offset + i + 1,
                userId: uid,
                username: user.username,
                avatarUrl: user.avatarUrl,
                eloRating: rating.eloRating,
                wins: rating.wins,
                losses: rating.losses,
                winRate: total_ > 0 ? rating.wins / total_ : 0,
            };
        })
        .filter((e): e is LeaderboardEntry => e !== null);

    return { entries, total };
}

/** Postgres-only leaderboard fallback. */
async function getLeaderboardFromDb(limit: number, offset: number): Promise<LeaderboardResult> {
    const [ratings, total] = await Promise.all([
        prisma.playerRating.findMany({
            orderBy: { eloRating: 'desc' },
            take: limit,
            skip: offset,
            include: { user: { select: { username: true, avatarUrl: true } } },
        }),
        prisma.playerRating.count(),
    ]);

    const entries: LeaderboardEntry[] = ratings.map((r, i) => {
        const total_ = r.wins + r.losses;
        return {
            rank: offset + i + 1,
            userId: r.userId,
            username: r.user.username,
            avatarUrl: r.user.avatarUrl,
            eloRating: r.eloRating,
            wins: r.wins,
            losses: r.losses,
            winRate: total_ > 0 ? r.wins / total_ : 0,
        };
    });

    return { entries, total };
}

/** Seed Redis from Postgres for warm-up after restart. */
async function seedLeaderboardFromDb(): Promise<void> {
    const ratings = await prisma.playerRating.findMany({
        select: { userId: true, eloRating: true },
    });
    if (ratings.length === 0) return;

    const redis = getRedis();
    const args: (string | number)[] = [];
    for (const r of ratings) {
        args.push(r.eloRating, r.userId);
    }
    await redis.zadd(LEADERBOARD_KEY, ...args);
}

// ── Player Rating Query ───────────────────────────────────────────────────────

export interface PlayerRatingView {
    userId: string;
    username: string;
    avatarUrl: string | null;
    eloRating: number;
    wins: number;
    losses: number;
    winRate: number;
    rank: number | null;
    lastMatchAt: string | null;
}

export async function getPlayerRating(userId: string): Promise<PlayerRatingView | null> {
    const rating = await prisma.playerRating.findUnique({
        where: { userId },
        include: { user: { select: { username: true, avatarUrl: true } } },
    });
    if (!rating) return null;

    // Get rank from Redis (0-indexed → add 1; null if not in leaderboard).
    let rank: number | null = null;
    try {
        const redis = getRedis();
        const revRank = await redis.zrevrank(LEADERBOARD_KEY, userId);
        rank = revRank !== null ? revRank + 1 : null;
    } catch {
        // Non-fatal.
    }

    const total = rating.wins + rating.losses;
    return {
        userId,
        username: rating.user.username,
        avatarUrl: rating.user.avatarUrl,
        eloRating: rating.eloRating,
        wins: rating.wins,
        losses: rating.losses,
        winRate: total > 0 ? rating.wins / total : 0,
        rank,
        lastMatchAt: rating.lastMatchAt?.toISOString() ?? null,
    };
}

// ── Match History ─────────────────────────────────────────────────────────────

export interface MatchHistoryEntry {
    id: string;
    roomId: string;
    winnerId: string;
    loserId: string;
    winnerEloBefore: number;
    winnerEloAfter: number;
    loserEloBefore: number;
    loserEloAfter: number;
    eloDelta: number;
    endReason: string;
    durationMs: number;
    difficulty: string;
    createdAt: string;
}

export async function getMatchHistory(
    userId: string,
    limit = 20,
): Promise<MatchHistoryEntry[]> {
    const matches = await prisma.multiplayerMatch.findMany({
        where: { OR: [{ winnerId: userId }, { loserId: userId }] },
        orderBy: { createdAt: 'desc' },
        take: Math.min(limit, 100),
    });

    return matches.map((m) => ({
        id: m.id,
        roomId: m.roomId,
        winnerId: m.winnerId,
        loserId: m.loserId,
        winnerEloBefore: m.winnerEloBefore,
        winnerEloAfter: m.winnerEloAfter,
        loserEloBefore: m.loserEloBefore,
        loserEloAfter: m.loserEloAfter,
        eloDelta: m.winnerEloAfter - m.winnerEloBefore,
        endReason: m.endReason,
        durationMs: m.durationMs,
        difficulty: m.difficulty,
        createdAt: m.createdAt.toISOString(),
    }));
}
