import express from 'express';
import cors from 'cors';
import helmet from 'helmet';
import morgan from 'morgan';
import { errorHandler } from './middleware/errorHandler';
import authRoutes from './routes/auth.routes';
import puzzleRoutes from './routes/puzzle.routes';
import sessionRoutes from './routes/session.routes';
import scoreRoutes from './routes/score.routes';
import dailyRoutes from './routes/daily.routes';

// ─── Express App Factory ──────────────────────────────────────────────────────

export function createApp() {
    const app = express();

    // ── Global Middleware ─────────────────────────────────────────────────────
    app.use(helmet());
    app.use(cors());
    app.use(express.json({ limit: '1mb' }));

    if (process.env.NODE_ENV !== 'test') {
        app.use(morgan('combined'));
    }

    // ── Health Check ──────────────────────────────────────────────────────────
    app.get('/health', (_req, res) => {
        res.json({
            status: 'ok',
            service: 'game-service',
            version: '0.0.1',
            timestamp: new Date().toISOString(),
        });
    });

    // ── API Routes ────────────────────────────────────────────────────────────
    app.use('/api/auth', authRoutes);
    app.use('/api/puzzles', puzzleRoutes);
    app.use('/api/sessions', sessionRoutes);
    app.use('/api/scores', scoreRoutes);
    app.use('/api/daily', dailyRoutes);

    // ── 404 Handler ───────────────────────────────────────────────────────────
    app.use((_req, res) => {
        res.status(404).json({
            success: false,
            data: null,
            error: 'Endpoint not found',
            timestamp: new Date().toISOString(),
        });
    });

    // ── Global Error Handler ──────────────────────────────────────────────────
    app.use(errorHandler);

    return app;
}
