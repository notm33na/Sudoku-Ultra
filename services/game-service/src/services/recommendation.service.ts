/**
 * Cluster-personalized puzzle recommendation service.
 *
 * Uses the user's skill cluster (assigned weekly by the skill_clustering
 * Airflow DAG) to select appropriate difficulty tiers and surface
 * relevant puzzles on the home screen.
 */

import { prisma } from '../prisma/client';

// ─── Cluster → Difficulty mapping ────────────────────────────────────────────

const CLUSTER_DIFFICULTIES: Record<string, string[]> = {
    Beginner:     ['super_easy', 'easy'],
    Casual:       ['easy', 'medium'],
    Intermediate: ['medium', 'hard'],
    Advanced:     ['hard', 'super_hard'],
    Expert:       ['super_hard', 'extreme'],
};

const DEFAULT_DIFFICULTIES = ['easy', 'medium', 'hard'];

const CLUSTER_MESSAGES: Record<string, string> = {
    Beginner:     'Start with confidence — these puzzles are perfect for building your skills.',
    Casual:       'A great mix to keep things fun and challenging.',
    Intermediate: 'You\'re making great progress. Ready to push your limits?',
    Advanced:     'Hard puzzles await. You\'ve earned this.',
    Expert:       'Elite-level challenges for elite players.',
};

// ─── Types ────────────────────────────────────────────────────────────────────

export interface PuzzleRecommendation {
    id: string;
    difficulty: string;
    clueCount: number;
    createdAt: string;
}

export interface HomeScreenData {
    skillCluster: string | null;
    clusterMessage: string;
    recommendedDifficulties: string[];
    recommendations: PuzzleRecommendation[];
    dailyPuzzle: {
        id: string;
        puzzleId: string;
        date: string;
        difficulty: string;
    } | null;
    streak: {
        currentStreak: number;
        longestStreak: number;
        freezeCount: number;
        newMilestone: number | null;
    } | null;
}

// ─── Main function ────────────────────────────────────────────────────────────

export async function getHomeScreen(userId: string): Promise<HomeScreenData> {
    const [user, streakRow, todayDaily] = await Promise.all([
        prisma.user.findUnique({
            where: { id: userId },
            select: { skillCluster: true, skillClusteredAt: true },
        }),
        prisma.streak.findUnique({ where: { userId } }),
        _getTodayDailyPuzzle(),
    ]);

    const cluster = user?.skillCluster ?? null;
    const difficulties = cluster
        ? (CLUSTER_DIFFICULTIES[cluster] ?? DEFAULT_DIFFICULTIES)
        : DEFAULT_DIFFICULTIES;

    // Fetch a handful of recent puzzles matching the recommended difficulties
    const recommendations = await prisma.puzzle.findMany({
        where: { difficulty: { in: difficulties } },
        orderBy: { createdAt: 'desc' },
        take: 6,
        select: { id: true, difficulty: true, clueCount: true, createdAt: true },
    });

    return {
        skillCluster: cluster,
        clusterMessage: cluster
            ? (CLUSTER_MESSAGES[cluster] ?? 'Here are some puzzles for you.')
            : 'Complete a few games to unlock personalised recommendations.',
        recommendedDifficulties: difficulties,
        recommendations: recommendations.map((p) => ({
            id: p.id,
            difficulty: p.difficulty,
            clueCount: p.clueCount,
            createdAt: p.createdAt.toISOString(),
        })),
        dailyPuzzle: todayDaily,
        streak: streakRow
            ? {
                currentStreak: streakRow.currentStreak,
                longestStreak: streakRow.longestStreak,
                freezeCount: streakRow.freezeCount,
                newMilestone: null,
            }
            : null,
    };
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

async function _getTodayDailyPuzzle() {
    const today = new Date();
    today.setUTCHours(0, 0, 0, 0);

    const daily = await prisma.dailyPuzzle.findUnique({
        where: { date: today },
        select: { id: true, puzzleId: true, date: true, difficulty: true },
    });

    if (!daily) return null;

    return {
        id: daily.id,
        puzzleId: daily.puzzleId,
        date: daily.date.toISOString().split('T')[0],
        difficulty: daily.difficulty,
    };
}
