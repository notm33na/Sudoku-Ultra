import { Response, NextFunction } from 'express';
import { AuthenticatedRequest } from '../middleware/auth';
import * as dailyService from '../services/daily.service';

function ok(res: Response, data: unknown) {
    res.json({ success: true, data, error: null, timestamp: new Date().toISOString() });
}

export async function getDailyPuzzle(req: AuthenticatedRequest, res: Response, next: NextFunction) {
    try {
        const result = await dailyService.getDailyPuzzle();
        ok(res, result);
    } catch (err) {
        next(err);
    }
}
