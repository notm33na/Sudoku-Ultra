import { Response, NextFunction } from 'express';
import { AuthenticatedRequest } from '../middleware/auth';
import * as scoreService from '../services/score.service';
import * as streakService from '../services/streak.service';

function ok(res: Response, data: unknown) {
    res.json({ success: true, data, error: null, timestamp: new Date().toISOString() });
}

export async function getLeaderboard(req: AuthenticatedRequest, res: Response, next: NextFunction) {
    try {
        const result = await scoreService.getLeaderboard(req.query as any);
        ok(res, result);
    } catch (err) {
        next(err);
    }
}

export async function getMyScores(req: AuthenticatedRequest, res: Response, next: NextFunction) {
    try {
        const result = await scoreService.getUserScores(req.user!.userId);
        ok(res, result);
    } catch (err) {
        next(err);
    }
}

export async function getMyStreak(req: AuthenticatedRequest, res: Response, next: NextFunction) {
    try {
        const result = await streakService.getStreak(req.user!.userId);
        ok(res, result);
    } catch (err) {
        next(err);
    }
}
