import { prisma } from '../prisma/client';
import { LeaderboardQuery } from '../schemas';

// ─── Leaderboard ──────────────────────────────────────────────────────────────

export async function getLeaderboard(query: LeaderboardQuery) {
    const where = query.difficulty ? { difficulty: query.difficulty } : {};
    const skip = (query.page - 1) * query.limit;

    const [scores, totalCount] = await Promise.all([
        prisma.score.findMany({
            where,
            orderBy: { points: 'desc' },
            take: query.limit,
            skip,
            include: {
                user: { select: { id: true, username: true, avatarUrl: true } },
            },
        }),
        prisma.score.count({ where }),
    ]);

    return {
        scores: scores.map((s) => ({
            id: s.id,
            userId: s.userId,
            username: s.user.username,
            avatarUrl: s.user.avatarUrl,
            points: s.points,
            timeMs: s.timeMs,
            difficulty: s.difficulty,
            completedAt: s.completedAt.toISOString(),
        })),
        page: query.page,
        pageSize: query.limit,
        totalCount,
        totalPages: Math.ceil(totalCount / query.limit),
    };
}

// ─── User Scores ──────────────────────────────────────────────────────────────

export async function getUserScores(userId: string) {
    const scores = await prisma.score.findMany({
        where: { userId },
        orderBy: { completedAt: 'desc' },
        take: 50,
    });

    return scores.map((s) => ({
        id: s.id,
        puzzleId: s.puzzleId,
        points: s.points,
        timeMs: s.timeMs,
        difficulty: s.difficulty,
        completedAt: s.completedAt.toISOString(),
    }));
}
