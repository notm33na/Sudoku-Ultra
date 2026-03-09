import { Response, NextFunction } from 'express';
import { AuthenticatedRequest } from '../middleware/auth';
import * as sessionService from '../services/session.service';

function ok(res: Response, data: unknown) {
    res.json({ success: true, data, error: null, timestamp: new Date().toISOString() });
}

export async function create(req: AuthenticatedRequest, res: Response, next: NextFunction) {
    try {
        const result = await sessionService.createSession(req.user!.userId, req.body);
        res.status(201);
        ok(res, result);
    } catch (err) {
        next(err);
    }
}

export async function getById(req: AuthenticatedRequest, res: Response, next: NextFunction) {
    try {
        const result = await sessionService.getSession(req.params.id, req.user!.userId);
        ok(res, result);
    } catch (err) {
        next(err);
    }
}

export async function update(req: AuthenticatedRequest, res: Response, next: NextFunction) {
    try {
        const result = await sessionService.updateSession(req.params.id, req.user!.userId, req.body);
        ok(res, result);
    } catch (err) {
        next(err);
    }
}

export async function getHint(req: AuthenticatedRequest, res: Response, next: NextFunction) {
    try {
        const result = await sessionService.getSessionHint(req.params.id, req.user!.userId);
        ok(res, result);
    } catch (err) {
        next(err);
    }
}

export async function validate(req: AuthenticatedRequest, res: Response, next: NextFunction) {
    try {
        const result = await sessionService.validateSession(req.params.id, req.user!.userId);
        ok(res, result);
    } catch (err) {
        next(err);
    }
}

export async function complete(req: AuthenticatedRequest, res: Response, next: NextFunction) {
    try {
        const result = await sessionService.completeSession(req.params.id, req.user!.userId, req.body);
        ok(res, result);
    } catch (err) {
        next(err);
    }
}
