import { Request, Response, NextFunction } from 'express';

export class AppError extends Error {
    constructor(
        public statusCode: number,
        message: string,
    ) {
        super(message);
        this.name = 'AppError';
    }
}

/**
 * Global error handler — catches all unhandled errors and formats
 * them as ApiResponse objects.
 */
export function errorHandler(err: Error, _req: Request, res: Response, _next: NextFunction): void {
    console.error('Unhandled error:', err);

    if (err instanceof AppError) {
        res.status(err.statusCode).json({
            success: false,
            data: null,
            error: err.message,
            timestamp: new Date().toISOString(),
        });
        return;
    }

    res.status(500).json({
        success: false,
        data: null,
        error: process.env.NODE_ENV === 'production' ? 'Internal server error' : err.message,
        timestamp: new Date().toISOString(),
    });
}
