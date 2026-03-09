import { Request, Response, NextFunction } from 'express';
import jwt from 'jsonwebtoken';
import { config } from '../config';

export interface AuthenticatedRequest extends Request {
    user?: {
        userId: string;
        email: string;
    };
}

/**
 * JWT authentication middleware.
 * Extracts and verifies the Bearer token from the Authorization header.
 * Attaches decoded user info to `req.user`.
 */
export function authenticate(req: AuthenticatedRequest, res: Response, next: NextFunction): void {
    const authHeader = req.headers.authorization;

    if (!authHeader || !authHeader.startsWith('Bearer ')) {
        res.status(401).json({
            success: false,
            data: null,
            error: 'Missing or invalid authorization header',
            timestamp: new Date().toISOString(),
        });
        return;
    }

    const token = authHeader.split(' ')[1];

    try {
        const decoded = jwt.verify(token, config.JWT_SECRET) as { userId: string; email: string };
        req.user = { userId: decoded.userId, email: decoded.email };
        next();
    } catch {
        res.status(401).json({
            success: false,
            data: null,
            error: 'Invalid or expired token',
            timestamp: new Date().toISOString(),
        });
    }
}
