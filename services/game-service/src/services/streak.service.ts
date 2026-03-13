import { prisma } from '../prisma/client';

// ─── Constants ────────────────────────────────────────────────────────────────

const STREAK_MILESTONES = [7, 30, 100, 365] as const;
type Milestone = (typeof STREAK_MILESTONES)[number];

// 23-25 hour window prevents same-session double-count (min) and gives grace
// past midnight (max). Calendar-day fallback handles players who play at
// different times each day (e.g. 8am Mon → 10pm Tue = 38h but still day+1).
const CONSECUTIVE_MIN_MS = 23 * 60 * 60 * 1000;
const CONSECUTIVE_MAX_MS = 25 * 60 * 60 * 1000;

// One freeze granted per 7 days; max 1 held at a time.
const FREEZE_GRANT_INTERVAL_MS = 7 * 24 * 60 * 60 * 1000;

// ─── Types ────────────────────────────────────────────────────────────────────

export interface StreakState {
    currentStreak: number;
    longestStreak: number;
    lastPlayedDate: string | null;
    freezeCount: number;
    milestonesAwarded: number[];
    /** Non-null when a milestone was reached on this update. */
    newMilestone: Milestone | null;
    /** True if a freeze token was consumed to save the streak. */
    freezeConsumed: boolean;
    /** True if the streak was broken and reset to 1 (no freeze available). */
    streakBroken: boolean;
}

// ─── Get Streak ───────────────────────────────────────────────────────────────

export async function getStreak(userId: string): Promise<StreakState> {
    const streak = await prisma.streak.findUnique({ where: { userId } });
    if (!streak) {
        return {
            currentStreak: 0,
            longestStreak: 0,
            lastPlayedDate: null,
            freezeCount: 0,
            milestonesAwarded: [],
            newMilestone: null,
            freezeConsumed: false,
            streakBroken: false,
        };
    }
    return _buildState(streak, null, false, false);
}

// ─── Update Streak ────────────────────────────────────────────────────────────
// Called by session.service on every completed game session.

export async function updateStreak(userId: string): Promise<StreakState> {
    const now = new Date();
    const existing = await prisma.streak.findUnique({ where: { userId } });

    // ── First ever completion ─────────────────────────────────────────────────
    if (!existing) {
        const created = await prisma.streak.create({
            data: {
                userId,
                currentStreak: 1,
                longestStreak: 1,
                lastPlayedDate: now,
                freezeCount: 0,
                milestonesAwarded: [],
            },
        });
        return _buildState(created, _checkMilestone([], 1).newMilestone, false, false);
    }

    // ── Weekly freeze grant ───────────────────────────────────────────────────
    const grantFreeze = _shouldGrantFreeze(existing, now);
    const baseFreeze = grantFreeze ? Math.min(existing.freezeCount + 1, 1) : existing.freezeCount;
    const newLastGranted = grantFreeze ? now : (existing.lastFreezeGrantedAt ?? undefined);

    const lastPlayed = existing.lastPlayedDate;

    if (!lastPlayed) {
        const updated = await prisma.streak.update({
            where: { userId },
            data: {
                currentStreak: 1,
                longestStreak: Math.max(existing.longestStreak, 1),
                lastPlayedDate: now,
                freezeCount: baseFreeze,
                lastFreezeGrantedAt: newLastGranted,
            },
        });
        return _buildState(updated, null, false, false);
    }

    const msSinceLast = now.getTime() - lastPlayed.getTime();
    const calDayDiff = _utcDayDiff(lastPlayed, now);

    // ── Already played very recently — idempotent, no streak change ───────────
    if (msSinceLast < CONSECUTIVE_MIN_MS) {
        if (grantFreeze) {
            await prisma.streak.update({
                where: { userId },
                data: { freezeCount: baseFreeze, lastFreezeGrantedAt: now },
            });
        }
        return _buildState({ ...existing, freezeCount: baseFreeze }, null, false, false);
    }

    // ── Consecutive: within grace window OR next calendar day ─────────────────
    if (msSinceLast <= CONSECUTIVE_MAX_MS || calDayDiff === 1) {
        const newStreak = existing.currentStreak + 1;
        const { milestonesAwarded, newMilestone } = _checkMilestone(
            existing.milestonesAwarded as number[],
            newStreak,
        );
        const updated = await prisma.streak.update({
            where: { userId },
            data: {
                currentStreak: newStreak,
                longestStreak: Math.max(existing.longestStreak, newStreak),
                lastPlayedDate: now,
                freezeCount: baseFreeze,
                lastFreezeGrantedAt: newLastGranted,
                milestonesAwarded,
            },
        });
        return _buildState(updated, newMilestone, false, false);
    }

    // ── Missed — consume freeze if available ──────────────────────────────────
    if (baseFreeze > 0) {
        const newStreak = existing.currentStreak + 1;
        const { milestonesAwarded, newMilestone } = _checkMilestone(
            existing.milestonesAwarded as number[],
            newStreak,
        );
        const updated = await prisma.streak.update({
            where: { userId },
            data: {
                currentStreak: newStreak,
                longestStreak: Math.max(existing.longestStreak, newStreak),
                lastPlayedDate: now,
                freezeCount: baseFreeze - 1,
                lastFreezeGrantedAt: newLastGranted,
                milestonesAwarded,
            },
        });
        return _buildState(updated, newMilestone, true, false);
    }

    // ── Streak broken — reset to 1 ────────────────────────────────────────────
    const updated = await prisma.streak.update({
        where: { userId },
        data: {
            currentStreak: 1,
            lastPlayedDate: now,
            freezeCount: baseFreeze,
            lastFreezeGrantedAt: newLastGranted,
            // longestStreak is preserved
        },
    });
    return _buildState(updated, null, false, true);
}

// ─── FCM Token Registration ───────────────────────────────────────────────────

export async function registerFcmToken(userId: string, fcmToken: string): Promise<void> {
    await prisma.user.update({ where: { id: userId }, data: { fcmToken } });
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function _utcDayDiff(from: Date, to: Date): number {
    const a = Date.UTC(from.getUTCFullYear(), from.getUTCMonth(), from.getUTCDate());
    const b = Date.UTC(to.getUTCFullYear(), to.getUTCMonth(), to.getUTCDate());
    return Math.round((b - a) / (24 * 60 * 60 * 1000));
}

function _shouldGrantFreeze(
    s: { lastFreezeGrantedAt: Date | null; freezeCount: number },
    now: Date,
): boolean {
    if (s.freezeCount >= 1) return false;
    if (!s.lastFreezeGrantedAt) return true;
    return now.getTime() - s.lastFreezeGrantedAt.getTime() >= FREEZE_GRANT_INTERVAL_MS;
}

function _checkMilestone(
    awarded: number[],
    newStreak: number,
): { milestonesAwarded: number[]; newMilestone: Milestone | null } {
    // Find the largest milestone that was just reached (handles backfill)
    const hit = STREAK_MILESTONES.slice()
        .reverse()
        .find((m) => newStreak >= m && !awarded.includes(m)) ?? null;
    return {
        milestonesAwarded: hit ? [...awarded, hit] : awarded,
        newMilestone: hit,
    };
}

function _buildState(
    s: {
        currentStreak: number;
        longestStreak: number;
        lastPlayedDate: Date | null;
        freezeCount: number;
        milestonesAwarded: unknown;
    },
    newMilestone: Milestone | null,
    freezeConsumed: boolean,
    streakBroken: boolean,
): StreakState {
    return {
        currentStreak: s.currentStreak,
        longestStreak: s.longestStreak,
        lastPlayedDate: s.lastPlayedDate?.toISOString() ?? null,
        freezeCount: s.freezeCount,
        milestonesAwarded: (s.milestonesAwarded as number[]) ?? [],
        newMilestone,
        freezeConsumed,
        streakBroken,
    };
}
