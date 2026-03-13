/**
 * Re-engagement queue poller.
 *
 * Polls re_engagement_queue (populated nightly by the churn_risk_scorer
 * Airflow DAG) and sends FCM push notifications to high-risk users.
 * Runs every POLL_INTERVAL_MS. Marks entries as notified after send.
 */

import { Pool } from 'pg';
import { sendPush, isFcmAvailable } from './fcm.service';

const POLL_INTERVAL_MS = 5 * 60 * 1000; // 5 minutes
const BATCH_SIZE = 100;

interface QueueRow {
    id: string;
    userId: string;
    churnProb: number;
    riskLevel: string;
    fcmToken: string | null;
}

let pool: Pool | null = null;

function getPool(): Pool {
    if (!pool) {
        pool = new Pool({
            connectionString: process.env.DATABASE_URL,
            max: 5,
        });
    }
    return pool;
}

// ─── Messages by risk level ───────────────────────────────────────────────────

const MESSAGES: Record<string, { title: string; body: string }> = {
    medium: {
        title: "Your puzzles miss you 🧩",
        body: "It's been a few days. Keep your streak alive with today's challenge!",
    },
    high: {
        title: "Don't let your streak slip! ⚡",
        body: "A quick puzzle is all it takes. Come back and keep your skills sharp.",
    },
    critical: {
        title: "We haven't seen you in a while 👋",
        body: "Your progress is waiting. Jump back in — today's puzzle takes under 5 minutes!",
    },
};

function buildMessage(riskLevel: string): { title: string; body: string } {
    return MESSAGES[riskLevel] ?? MESSAGES['high'];
}

// ─── Core processor ──────────────────────────────────────────────────────────

async function processQueue(): Promise<void> {
    if (!isFcmAvailable()) {
        // FCM not configured — skip silently
        return;
    }

    const db = getPool();

    const { rows } = await db.query<QueueRow>(
        `SELECT
            q.id,
            q.user_id      AS "userId",
            q.churn_prob   AS "churnProb",
            q.risk_level   AS "riskLevel",
            u.fcm_token    AS "fcmToken"
         FROM re_engagement_queue q
         JOIN users u ON u.id = q.user_id
         WHERE q.notified = false
           AND u.fcm_token IS NOT NULL
         ORDER BY q.churn_prob DESC, q.created_at ASC
         LIMIT $1`,
        [BATCH_SIZE],
    );

    if (rows.length === 0) return;

    console.info(`[QueuePoller] Processing ${rows.length} re-engagement notifications`);

    for (const row of rows) {
        if (!row.fcmToken) continue;

        const { title, body } = buildMessage(row.riskLevel);
        const msgId = await sendPush(row.fcmToken, title, body, {
            type: 're_engagement',
            risk_level: row.riskLevel,
            churn_prob: String(row.churnProb),
        });

        if (msgId !== null) {
            await db.query(
                `UPDATE re_engagement_queue
                 SET notified = true, notified_at = NOW()
                 WHERE id = $1`,
                [row.id],
            );
        }
    }

    console.info(`[QueuePoller] Batch done`);
}

// ─── Exported controls ────────────────────────────────────────────────────────

let pollTimer: NodeJS.Timeout | null = null;

export function startQueuePoller(): void {
    // Run once immediately, then on interval
    processQueue().catch((err) => console.error('[QueuePoller] Initial tick error:', err));
    pollTimer = setInterval(() => {
        processQueue().catch((err) => console.error('[QueuePoller] Tick error:', err));
    }, POLL_INTERVAL_MS);
    console.info(`[QueuePoller] Started — polling every ${POLL_INTERVAL_MS / 60_000} min`);
}

export function stopQueuePoller(): void {
    if (pollTimer) {
        clearInterval(pollTimer);
        pollTimer = null;
    }
    if (pool) {
        pool.end().catch(() => {});
        pool = null;
    }
}
