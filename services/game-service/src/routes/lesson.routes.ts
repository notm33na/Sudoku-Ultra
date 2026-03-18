/**
 * Lesson routes — gamified technique learning.
 *
 * GET  /api/lessons              — list all 15 lessons with user progress
 * GET  /api/lessons/badges       — current user's earned badges
 * GET  /api/lessons/:id          — single lesson with steps + progress
 * POST /api/lessons/:id/steps/:step/complete — mark a step done, award XP
 */

import { Router, Request, Response, NextFunction } from 'express';
import { z } from 'zod';
import { authenticate } from '../middleware/auth';
import * as svc from '../services/lesson.service';

const router = Router();

// All lesson routes require authentication
router.use(authenticate);

// ── GET /api/lessons ──────────────────────────────────────────────────────────

router.get(
    '/',
    async (req: Request, res: Response, next: NextFunction): Promise<void> => {
        try {
            const userId = (req as any).user.id as string;
            const lessons = await svc.listLessons(userId);

            res.json({
                lessons: lessons.map(({ lesson, progress }) => ({
                    id: lesson.id,
                    title: lesson.title,
                    difficulty: lesson.difficulty,
                    xpReward: lesson.xpReward,
                    estimatedMinutes: lesson.estimatedMinutes,
                    description: lesson.description,
                    tags: lesson.tags,
                    prerequisiteIds: lesson.prerequisiteIds,
                    totalSteps: lesson.steps.length,
                    progress,
                })),
            });
        } catch (err) {
            next(err);
        }
    },
);

// ── GET /api/lessons/badges ───────────────────────────────────────────────────

router.get(
    '/badges',
    async (req: Request, res: Response, next: NextFunction): Promise<void> => {
        try {
            const userId = (req as any).user.id as string;
            const [earned, all] = await Promise.all([
                svc.getUserBadges(userId),
                Promise.resolve(svc.BADGES),
            ]);
            const earnedIds = new Set(earned.map((b) => b.id));
            res.json({
                earned,
                available: all.filter((b) => !earnedIds.has(b.id)),
            });
        } catch (err) {
            next(err);
        }
    },
);

// ── GET /api/lessons/:id ──────────────────────────────────────────────────────

router.get(
    '/:id',
    async (req: Request, res: Response, next: NextFunction): Promise<void> => {
        try {
            const userId = (req as any).user.id as string;
            const result = await svc.getLesson(userId, req.params.id);
            if (!result) {
                res.status(404).json({ error: 'Lesson not found.' });
                return;
            }
            res.json(result);
        } catch (err) {
            next(err);
        }
    },
);

// ── POST /api/lessons/:id/steps/:step/complete ────────────────────────────────

const stepSchema = z.object({
    /** For practice steps: the value the user entered (validated server-side) */
    answer: z.number().int().min(1).max(9).optional(),
});

router.post(
    '/:id/steps/:step/complete',
    async (req: Request, res: Response, next: NextFunction): Promise<void> => {
        try {
            const userId = (req as any).user.id as string;
            const lessonId = req.params.id;
            const stepNumber = parseInt(req.params.step, 10);

            if (isNaN(stepNumber) || stepNumber < 1) {
                res.status(400).json({ error: 'Invalid step number.' });
                return;
            }

            const parsed = stepSchema.safeParse(req.body);
            if (!parsed.success) {
                res.status(400).json({ error: parsed.error.flatten() });
                return;
            }

            const result = await svc.completeStep(userId, lessonId, stepNumber);
            res.status(200).json(result);
        } catch (err: any) {
            if (err?.message?.includes('not found') || err?.message?.includes('out of range')) {
                res.status(400).json({ error: err.message });
                return;
            }
            next(err);
        }
    },
);

export default router;
