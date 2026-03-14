/**
 * anomaly.service.ts — Client wrapper for the ml-service anomaly endpoint.
 *
 * Sends completed session stats to ml-service /api/v1/anomaly/score.
 * Called fire-and-forget from completeSession; failures are logged but
 * never block the user or their score.
 *
 * If the response indicates an anomaly, the finding is logged for review.
 * Future: write an AnomalyFlag record to Postgres + alert ops via Slack.
 */

import { config } from '../config';

interface AnomalyCheckInput {
    sessionId: string;
    userId: string;
    difficulty: string;
    timeElapsedMs: number;
    cellsFilled: number;
    errorsCount: number;
    hintsUsed: number;
}

interface AnomalyResult {
    session_id: string;
    user_id: string;
    anomaly_score: number;
    reconstruction_error: number;
    threshold: number;
    is_anomalous: boolean;
}

const ANOMALY_ENDPOINT = '/api/v1/anomaly/score';
const TIMEOUT_MS = 5_000;

/**
 * Post session stats to the ml-service and log anomalies.
 * Always resolves; never throws.
 */
export async function checkSessionAnomaly(input: AnomalyCheckInput): Promise<void> {
    const url = config.ML_SERVICE_URL + ANOMALY_ENDPOINT;

    const body = JSON.stringify({
        session_id: input.sessionId,
        user_id: input.userId,
        difficulty: input.difficulty,
        time_elapsed_ms: input.timeElapsedMs,
        cells_filled: input.cellsFilled,
        errors_count: input.errorsCount,
        hints_used: input.hintsUsed,
    });

    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);

    try {
        const resp = await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body,
            signal: controller.signal,
        });

        if (!resp.ok) {
            console.warn('[anomaly] ml-service returned', resp.status, 'for session', input.sessionId);
            return;
        }

        const result: AnomalyResult = await resp.json();

        if (result.is_anomalous) {
            console.warn(
                '[anomaly] FLAGGED session=%s user=%s score=%.4f',
                input.sessionId,
                input.userId,
                result.anomaly_score,
            );
            // TODO D8+: persist AnomalyFlag to Postgres and notify ops.
        }
    } catch (err) {
        // ml-service unreachable — log quietly, never surface to user.
        console.debug('[anomaly] check skipped (ml-service unreachable):', (err as Error).message);
    } finally {
        clearTimeout(timer);
    }
}
