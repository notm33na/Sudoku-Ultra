import { prisma } from '../prisma/client';

// ─── Get or Create Streak ─────────────────────────────────────────────────────

export async function getStreak(userId: string) {
    const streak = await prisma.streak.findUnique({ where: { userId } });

    if (!streak) {
        return {
            currentStreak: 0,
            longestStreak: 0,
            lastPlayedDate: null,
        };
    }

    return {
        currentStreak: streak.currentStreak,
        longestStreak: streak.longestStreak,
        lastPlayedDate: streak.lastPlayedDate?.toISOString() ?? null,
    };
}

// ─── Update Streak (called on session complete) ───────────────────────────────

export async function updateStreak(userId: string) {
    const today = new Date();
    today.setHours(0, 0, 0, 0);

    const yesterday = new Date(today);
    yesterday.setDate(yesterday.getDate() - 1);

    const existing = await prisma.streak.findUnique({ where: { userId } });

    if (!existing) {
        // First ever completion
        return prisma.streak.create({
            data: {
                userId,
                currentStreak: 1,
                longestStreak: 1,
                lastPlayedDate: today,
            },
        });
    }

    const lastPlayed = existing.lastPlayedDate;
    if (!lastPlayed) {
        // Never played before
        return prisma.streak.update({
            where: { userId },
            data: {
                currentStreak: 1,
                longestStreak: Math.max(existing.longestStreak, 1),
                lastPlayedDate: today,
            },
        });
    }

    const lastPlayedDay = new Date(lastPlayed);
    lastPlayedDay.setHours(0, 0, 0, 0);

    if (lastPlayedDay.getTime() === today.getTime()) {
        // Already played today — no change
        return existing;
    }

    if (lastPlayedDay.getTime() === yesterday.getTime()) {
        // Consecutive day — extend streak
        const newStreak = existing.currentStreak + 1;
        return prisma.streak.update({
            where: { userId },
            data: {
                currentStreak: newStreak,
                longestStreak: Math.max(existing.longestStreak, newStreak),
                lastPlayedDate: today,
            },
        });
    }

    // Streak broken — reset to 1
    return prisma.streak.update({
        where: { userId },
        data: {
            currentStreak: 1,
            longestStreak: existing.longestStreak, // Keep longest
            lastPlayedDate: today,
        },
    });
}
