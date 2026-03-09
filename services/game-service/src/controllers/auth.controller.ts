import { Request, Response, NextFunction } from 'express';
import { AuthenticatedRequest } from '../middleware/auth';
import * as authService from '../services/auth.service';

function ok(res: Response, data: unknown) {
    res.json({ success: true, data, error: null, timestamp: new Date().toISOString() });
}

export async function register(req: Request, res: Response, next: NextFunction) {
    try {
        const result = await authService.register(req.body);
        res.status(201);
        ok(res, result);
    } catch (err) {
        next(err);
    }
}

export async function login(req: Request, res: Response, next: NextFunction) {
    try {
        const result = await authService.login(req.body);
        ok(res, result);
    } catch (err) {
        next(err);
    }
}

export async function refresh(req: Request, res: Response, next: NextFunction) {
    try {
        const tokens = await authService.refreshToken(req.body.refreshToken);
        ok(res, tokens);
    } catch (err) {
        next(err);
    }
}

export async function me(req: AuthenticatedRequest, res: Response, next: NextFunction) {
    try {
        const user = await authService.getProfile(req.user!.userId);
        ok(res, user);
    } catch (err) {
        next(err);
    }
}
