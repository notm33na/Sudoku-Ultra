import express from 'express';
import cors from 'cors';
import helmet from 'helmet';
import morgan from 'morgan';
import { errorHandler } from './middleware/errorHandler';
import { authLimiter, apiLimiter, adminLimiter } from './middleware/rateLimiter';
import authRoutes from './routes/auth.routes';
import puzzleRoutes from './routes/puzzle.routes';
import sessionRoutes from './routes/session.routes';
import scoreRoutes from './routes/score.routes';
import dailyRoutes from './routes/daily.routes';
import homeRoutes from './routes/home.routes';
import ratingRoutes from './routes/rating.routes';
import lessonRoutes from './routes/lesson.routes';
import onboardingRoutes from './routes/onboarding.routes';
import friendRoutes from './routes/friend.routes';
import adminRoutes from './routes/admin.routes';
import pactRoutes from './routes/pact.routes';

// ─── Express App Factory ──────────────────────────────────────────────────────

export function createApp() {
    const app = express();

    // ── Global Middleware ─────────────────────────────────────────────────────
    app.use(helmet({
        contentSecurityPolicy: {
            directives: {
                defaultSrc: ["'self'"],
                scriptSrc:  ["'self'"],
                styleSrc:   ["'self'", "'unsafe-inline'"],
                imgSrc:     ["'self'", 'data:'],
                connectSrc: ["'self'"],
                objectSrc:  ["'none'"],
                frameSrc:   ["'none'"],
            },
        },
        hsts: {
            maxAge: 31536000,
            includeSubDomains: true,
            preload: true,
        },
    }));
    app.set('trust proxy', 1);  // trust first proxy (nginx / load balancer)
    app.use(cors());
    app.use(express.json({ limit: '1mb' }));
    app.use('/api/', apiLimiter);

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
    app.use('/api/auth', authLimiter, authRoutes);
    app.use('/api/puzzles', puzzleRoutes);
    app.use('/api/sessions', sessionRoutes);
    app.use('/api/scores', scoreRoutes);
    app.use('/api/daily', dailyRoutes);
    app.use('/api/home', homeRoutes);
    app.use('/api/ratings', ratingRoutes);
    app.use('/api/lessons', lessonRoutes);
    app.use('/api/onboarding', onboardingRoutes);
    app.use('/api/friends', friendRoutes);
    app.use('/api/admin', adminLimiter, adminRoutes);

    // ── Pact provider-state endpoint (test only) ──────────────────────────────
    if (process.env.NODE_ENV === 'test') {
        app.use('/_pact/provider-states', pactRoutes);
    }

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
