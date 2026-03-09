import { Request, Response, NextFunction } from 'express';
import { AuthenticatedRequest } from '../middleware/auth';
import * as puzzleService from '../services/puzzle.service';

function ok(res: Response, data: unknown) {
    res.json({ success: true, data, error: null, timestamp: new Date().toISOString() });
}

export async function generate(req: AuthenticatedRequest, res: Response, next: NextFunction) {
    try {
        const result = await puzzleService.generatePuzzle(req.body.difficulty);
        res.status(201);
        ok(res, result);
    } catch (err) {
        next(err);
    }
}

export async function getById(req: Request, res: Response, next: NextFunction) {
    try {
        const result = await puzzleService.getPuzzle(req.params.id);
        ok(res, result);
    } catch (err) {
        next(err);
    }
}
