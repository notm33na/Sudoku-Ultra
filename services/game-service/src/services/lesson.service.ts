/**
 * Lesson service — progress tracking, XP, and badge awarding.
 *
 * Lessons and steps are defined statically in data/lessons.ts.
 * Progress is persisted in lesson_progress and user_badges tables.
 */

import { prisma } from '../prisma/client';
import {
    LESSONS,
    LESSON_MAP,
    LESSONS_BY_DIFFICULTY,
    type LessonDefinition,
} from '../data/lessons';
import { emitActivity } from './friend.service';

// ── Badge definitions ─────────────────────────────────────────────────────────

export interface BadgeDefinition {
    id: string;
    title: string;
    description: string;
    icon: string;
}

export const BADGES: BadgeDefinition[] = [
    {
        id: 'first-step',
        title: 'First Step',
        description: 'Completed your first lesson.',
        icon: '🎓',
    },
    {
        id: 'solid-foundation',
        title: 'Solid Foundation',
        description: 'Completed all beginner (difficulty 1) lessons.',
        icon: '🏗️',
    },
    {
        id: 'intermediate',
        title: 'Intermediate',
        description: 'Completed all difficulty-2 lessons.',
        icon: '⚡',
    },
    {
        id: 'advanced',
        title: 'Advanced',
        description: 'Completed all difficulty-3 lessons.',
        icon: '🔥',
    },
    {
        id: 'expert',
        title: 'Expert',
        description: 'Completed all difficulty-4 lessons.',
        icon: '💎',
    },
    {
        id: 'master',
        title: 'Master',
        description: 'Completed all 15 lessons.',
        icon: '👑',
    },
    {
        id: 'speed-learner',
        title: 'Speed Learner',
        description: 'Completed a lesson in under 3 minutes.',
        icon: '⚡',
    },
];

export const BADGE_MAP = new Map<string, BadgeDefinition>(
    BADGES.map((b) => [b.id, b]),
);

// ── Types ──────────────────────────────────────────────────────────────────────

export interface LessonWithProgress {
    lesson: LessonDefinition;
    progress: {
        stepsComplete: number;
        completed: boolean;
        completedAt: Date | null;
        xpAwarded: number;
    } | null;
}

export interface StepCompleteResult {
    lessonId: string;
    stepsComplete: number;
    totalSteps: number;
    lessonCompleted: boolean;
    xpAwarded: number;
    totalXp: number;
    newBadges: BadgeDefinition[];
}

// ── Service functions ──────────────────────────────────────────────────────────

/** List all lessons with the user's progress attached. */
export async function listLessons(userId: string): Promise<LessonWithProgress[]> {
    const progresses = await prisma.lessonProgress.findMany({
        where: { userId },
    });
    const progressMap = new Map(progresses.map((p) => [p.lessonId, p]));

    return LESSONS.map((lesson) => {
        const p = progressMap.get(lesson.id);
        return {
            lesson,
            progress: p
                ? {
                      stepsComplete: p.stepsComplete,
                      completed: p.completed,
                      completedAt: p.completedAt,
                      xpAwarded: p.xpAwarded,
                  }
                : null,
        };
    });
}

/** Get a single lesson with the user's progress. */
export async function getLesson(
    userId: string,
    lessonId: string,
): Promise<LessonWithProgress | null> {
    const lesson = LESSON_MAP.get(lessonId);
    if (!lesson) return null;

    const p = await prisma.lessonProgress.findUnique({
        where: { userId_lessonId: { userId, lessonId } },
    });

    return {
        lesson,
        progress: p
            ? {
                  stepsComplete: p.stepsComplete,
                  completed: p.completed,
                  completedAt: p.completedAt,
                  xpAwarded: p.xpAwarded,
              }
            : null,
    };
}

/**
 * Mark a step as complete.  Awards XP and badges when the lesson finishes.
 */
export async function completeStep(
    userId: string,
    lessonId: string,
    stepNumber: number,
): Promise<StepCompleteResult> {
    const lesson = LESSON_MAP.get(lessonId);
    if (!lesson) throw new Error(`Lesson '${lessonId}' not found.`);

    const totalSteps = lesson.steps.length;
    if (stepNumber < 1 || stepNumber > totalSteps) {
        throw new Error(`Step ${stepNumber} is out of range for lesson '${lessonId}'.`);
    }

    // Upsert progress row
    const existing = await prisma.lessonProgress.findUnique({
        where: { userId_lessonId: { userId, lessonId } },
    });

    const nowStepsComplete = Math.max(existing?.stepsComplete ?? 0, stepNumber);
    const lessonCompleted = nowStepsComplete >= totalSteps;
    const alreadyCompleted = existing?.completed ?? false;

    let xpAwarded = existing?.xpAwarded ?? 0;
    const newBadges: BadgeDefinition[] = [];

    if (lessonCompleted && !alreadyCompleted) {
        xpAwarded = lesson.xpReward;
    }

    // Calculate elapsed time for speed-learner badge
    const startedAt = existing?.startedAt ?? new Date();
    const elapsedMs = Date.now() - startedAt.getTime();
    const fastLesson = elapsedMs < 3 * 60 * 1000; // < 3 minutes

    const progress = await prisma.lessonProgress.upsert({
        where: { userId_lessonId: { userId, lessonId } },
        create: {
            userId,
            lessonId,
            stepsComplete: nowStepsComplete,
            completed: lessonCompleted,
            completedAt: lessonCompleted ? new Date() : null,
            xpAwarded,
        },
        update: {
            stepsComplete: nowStepsComplete,
            completed: lessonCompleted,
            completedAt: lessonCompleted ? new Date() : undefined,
            xpAwarded,
        },
    });

    // Badge evaluation (only on fresh lesson completion)
    if (lessonCompleted && !alreadyCompleted) {
        const earned = await _evaluateBadges(userId, lessonId, fastLesson);
        newBadges.push(...earned);

        // Emit social activities — fire-and-forget.
        emitActivity(userId, userId, 'lesson_completed', {
            lessonId,
            lessonTitle: lesson.title,
            xpAwarded,
        }).catch(() => null);

        for (const badge of earned) {
            emitActivity(userId, userId, 'badge_earned', {
                badgeId: badge.id,
                badgeTitle: badge.title,
                badgeIcon: badge.icon,
            }).catch(() => null);
        }
    }

    // Total XP
    const totalXp = await _totalXp(userId);

    return {
        lessonId,
        stepsComplete: progress.stepsComplete,
        totalSteps,
        lessonCompleted: progress.completed,
        xpAwarded: progress.xpAwarded,
        totalXp,
        newBadges,
    };
}

/** List all badges a user has earned. */
export async function getUserBadges(
    userId: string,
): Promise<Array<BadgeDefinition & { awardedAt: Date }>> {
    const rows = await prisma.userBadge.findMany({ where: { userId } });
    return rows
        .map((row) => {
            const def = BADGE_MAP.get(row.badgeId);
            if (!def) return null;
            return { ...def, awardedAt: row.awardedAt };
        })
        .filter((b): b is BadgeDefinition & { awardedAt: Date } => b !== null);
}

// ── Private helpers ────────────────────────────────────────────────────────────

async function _totalXp(userId: string): Promise<number> {
    const result = await prisma.lessonProgress.aggregate({
        where: { userId },
        _sum: { xpAwarded: true },
    });
    return result._sum.xpAwarded ?? 0;
}

async function _awardBadge(userId: string, badgeId: string): Promise<boolean> {
    try {
        await prisma.userBadge.create({ data: { userId, badgeId } });
        return true;
    } catch {
        // Unique constraint violation → already awarded
        return false;
    }
}

async function _evaluateBadges(
    userId: string,
    completedLessonId: string,
    fastLesson: boolean,
): Promise<BadgeDefinition[]> {
    const awarded: BadgeDefinition[] = [];

    const completedProgresses = await prisma.lessonProgress.findMany({
        where: { userId, completed: true },
    });
    const completedIds = new Set(completedProgresses.map((p) => p.lessonId));

    // first-step
    if (completedIds.size === 1) {
        if (await _awardBadge(userId, 'first-step')) {
            awarded.push(BADGE_MAP.get('first-step')!);
        }
    }

    // difficulty-based badges
    const diffBadges: Array<[number, string]> = [
        [1, 'solid-foundation'],
        [2, 'intermediate'],
        [3, 'advanced'],
        [4, 'expert'],
    ];
    for (const [diff, badgeId] of diffBadges) {
        const needed = (LESSONS_BY_DIFFICULTY[diff] ?? []).map((l) => l.id);
        if (needed.length > 0 && needed.every((id) => completedIds.has(id))) {
            if (await _awardBadge(userId, badgeId)) {
                awarded.push(BADGE_MAP.get(badgeId)!);
            }
        }
    }

    // master — all 15 lessons
    if (LESSONS.every((l) => completedIds.has(l.id))) {
        if (await _awardBadge(userId, 'master')) {
            awarded.push(BADGE_MAP.get('master')!);
        }
    }

    // speed-learner
    if (fastLesson) {
        if (await _awardBadge(userId, 'speed-learner')) {
            awarded.push(BADGE_MAP.get('speed-learner')!);
        }
    }

    return awarded;
}
