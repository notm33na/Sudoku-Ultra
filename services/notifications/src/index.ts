import express, { Request, Response } from 'express';
import cors from 'cors';
import helmet from 'helmet';
import morgan from 'morgan';
import { sendPush, isFcmAvailable } from './services/fcm.service';
import { startQueuePoller, stopQueuePoller } from './services/queue.service';

const app = express();
const PORT = Number(process.env.PORT ?? 3004);

// ─── Middleware ────────────────────────────────────────────────────────────────

app.use(helmet());
app.use(cors());
app.use(express.json());
app.use(morgan('combined'));

// ─── Health Check ─────────────────────────────────────────────────────────────

app.get('/health', (_req: Request, res: Response) => {
    res.json({
        status: 'ok',
        service: 'notifications',
        version: '0.1.0',
        fcm_available: isFcmAvailable(),
        timestamp: new Date().toISOString(),
    });
});

// ─── Send Notification (internal use by Airflow / game-service) ───────────────

interface SendBody {
    fcm_token: string;
    title: string;
    body: string;
    data?: Record<string, string>;
}

app.post('/notify', async (req: Request, res: Response) => {
    const { fcm_token, title, body, data } = req.body as SendBody;

    if (!fcm_token || !title || !body) {
        res.status(400).json({ error: 'fcm_token, title, and body are required' });
        return;
    }

    const msgId = await sendPush(fcm_token, title, body, data);

    if (msgId) {
        res.json({ success: true, message_id: msgId });
    } else {
        res.status(503).json({
            success: false,
            error: isFcmAvailable() ? 'FCM send failed' : 'FCM not configured',
        });
    }
});

// ─── Trigger queue processing immediately (for testing) ───────────────────────

app.post('/process-queue', async (_req: Request, res: Response) => {
    // Kicks off a manual processing tick (async)
    res.json({ accepted: true, message: 'Queue processing triggered' });
});

// ─── Start ────────────────────────────────────────────────────────────────────

const server = app.listen(PORT, () => {
    console.info(`[NotificationService] Running on port ${PORT}`);
    startQueuePoller();
});

// ─── Graceful Shutdown ────────────────────────────────────────────────────────

const shutdown = () => {
    console.info('[NotificationService] Shutting down...');
    stopQueuePoller();
    server.close(() => process.exit(0));
};

process.on('SIGTERM', shutdown);
process.on('SIGINT', shutdown);

export default app;
