/**
 * Sudoku Ultra — Web Admin Dashboard Server
 *
 * Serves:
 *  - Static HTML/JS dashboard at /
 *  - JSON API endpoints consumed by the D3 charts
 *
 * Data sources:
 *  - PostgreSQL (game-service DB) for user/cluster data
 *  - ml-service analytics API for DuckDB metrics
 *
 * PHASE-3-HOOK: Migrate static dashboard to Angular once the project
 * reaches the web-admin dedicated phase.
 */

import express, { Request, Response } from 'express';
import cors from 'cors';
import helmet from 'helmet';
import path from 'path';
import { Pool } from 'pg';

const app = express();
const PORT = Number(process.env.PORT ?? 3005);
const ML_SERVICE_URL = process.env.ML_SERVICE_URL ?? 'http://localhost:3003';

const pool = new Pool({ connectionString: process.env.DATABASE_URL });

// ─── Middleware ────────────────────────────────────────────────────────────────

app.use(helmet({ contentSecurityPolicy: false })); // allow CDN scripts in dashboard
app.use(cors());
app.use(express.json());
app.use(express.static(path.join(__dirname, '../public')));

// ─── Health ───────────────────────────────────────────────────────────────────

app.get('/health', (_req, res) => {
    res.json({ status: 'ok', service: 'web-admin', timestamp: new Date().toISOString() });
});

// ─── API: Skill Cluster Distribution ─────────────────────────────────────────

app.get('/api/clusters', async (_req: Request, res: Response) => {
    try {
        const { rows } = await pool.query<{ cluster: string; count: string }>(`
            SELECT
                COALESCE(skill_cluster, 'Unassigned') AS cluster,
                COUNT(*) AS count
            FROM users
            GROUP BY skill_cluster
            ORDER BY count DESC
        `);
        res.json(rows.map((r) => ({ cluster: r.cluster, count: Number(r.count) })));
    } catch (err) {
        res.status(500).json({ error: String(err) });
    }
});

// ─── API: User Drill-down Table ───────────────────────────────────────────────

app.get('/api/users', async (req: Request, res: Response) => {
    const cluster = req.query.cluster as string | undefined;
    const limit = Math.min(Number(req.query.limit ?? 50), 200);
    const offset = Number(req.query.offset ?? 0);

    try {
        const { rows } = await pool.query(
            `SELECT
                u.id,
                u.username,
                u.email,
                u.skill_cluster,
                u.skill_clustered_at,
                u.created_at,
                COALESCE(s.current_streak, 0) AS current_streak,
                COALESCE(s.longest_streak, 0) AS longest_streak,
                COUNT(gs.id) AS total_games,
                COUNT(gs.id) FILTER (WHERE gs.status = 'completed') AS completed_games
             FROM users u
             LEFT JOIN streaks s ON s.user_id = u.id
             LEFT JOIN game_sessions gs ON gs.user_id = u.id
             WHERE ($1::text IS NULL OR u.skill_cluster = $1)
             GROUP BY u.id, s.current_streak, s.longest_streak
             ORDER BY u.created_at DESC
             LIMIT $2 OFFSET $3`,
            [cluster ?? null, limit, offset],
        );
        res.json(rows);
    } catch (err) {
        res.status(500).json({ error: String(err) });
    }
});

// ─── API: Analytics proxy (DuckDB via ml-service) ────────────────────────────

app.get('/api/analytics/:metric', async (req: Request, res: Response) => {
    try {
        const upstream = await fetch(`${ML_SERVICE_URL}/api/v1/analytics/${req.params.metric}`);
        const data = await upstream.json();
        res.json(data);
    } catch (err) {
        res.status(502).json({ error: 'ml-service unavailable', detail: String(err) });
    }
});

// ─── Catch-all → dashboard SPA ────────────────────────────────────────────────

app.get('*', (_req, res) => {
    res.sendFile(path.join(__dirname, '../public/index.html'));
});

// ─── Start ────────────────────────────────────────────────────────────────────

app.listen(PORT, () => {
    console.info(`[WebAdmin] Running on http://localhost:${PORT}`);
});

export default app;
