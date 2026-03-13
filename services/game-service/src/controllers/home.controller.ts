import { Request, Response, NextFunction } from 'express';
import { getHomeScreen } from '../services/recommendation.service';

export async function home(req: Request, res: Response, next: NextFunction) {
    try {
        const userId = (req as Request & { userId: string }).userId;
        const data = await getHomeScreen(userId);
        res.json({ success: true, data });
    } catch (err) {
        next(err);
    }
}
