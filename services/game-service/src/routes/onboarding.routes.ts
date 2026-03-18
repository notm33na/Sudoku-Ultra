/**
 * Onboarding routes.
 *
 * GET  /api/onboarding/status          — user's onboarding state
 * POST /api/onboarding/steps/:idx/complete — mark step done
 * POST /api/onboarding/skip            — mark tutorial skipped
 */

import { Router, Request, Response, NextFunction } from 'express';
import { authenticate } from '../middleware/auth';
import * as svc from '../services/onboarding.service';

const router = Router();
router.use(authenticate);

router.get(
    '/status',
    async (req: Request, res: Response, next: NextFunction): Promise<void> => {
        try {
            const userId = (req as any).user.id as string;
            res.json(await svc.getStatus(userId));
        } catch (err) {
            next(err);
        }
    },
);

router.post(
    '/steps/:idx/complete',
    async (req: Request, res: Response, next: NextFunction): Promise<void> => {
        try {
            const userId = (req as any).user.id as string;
            const idx = parseInt(req.params.idx, 10);
            if (isNaN(idx)) {
                res.status(400).json({ error: 'Invalid step index.' });
                return;
            }
            res.json(await svc.completeStep(userId, idx));
        } catch (err: any) {
            if (err?.message?.includes('out of range')) {
                res.status(400).json({ error: err.message });
                return;
            }
            next(err);
        }
    },
);

router.post(
    '/skip',
    async (req: Request, res: Response, next: NextFunction): Promise<void> => {
        try {
            const userId = (req as any).user.id as string;
            res.json(await svc.skipOnboarding(userId));
        } catch (err) {
            next(err);
        }
    },
);

export default router;
