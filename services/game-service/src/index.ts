import express from 'express';
import cors from 'cors';
import helmet from 'helmet';
import morgan from 'morgan';

const app = express();
const PORT = process.env.PORT || 3001;

// ─── Middleware ────────────────────────────────────────────────────────────────

app.use(helmet());
app.use(cors());
app.use(express.json());
app.use(morgan('combined'));

// ─── Health Check ─────────────────────────────────────────────────────────────

app.get('/health', (_req, res) => {
    res.json({
        status: 'ok',
        service: 'game-service',
        version: '0.0.1',
        timestamp: new Date().toISOString(),
    });
});

// ─── Start Server ─────────────────────────────────────────────────────────────

app.listen(PORT, () => {
    console.info(`🎮 Game Service running on port ${PORT}`);
});

export default app;
