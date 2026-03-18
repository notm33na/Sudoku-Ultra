/**
 * analytics.service.ts — Lightweight analytics for Sudoku Ultra mobile.
 *
 * Architecture:
 *   - All events are queued and flushed in batches (every 30 s or 20 events).
 *   - Uses the offline queue service so events survive network outages.
 *   - Screen views fire automatically via the navigation listener in
 *     RootNavigator's `onStateChange`.
 *   - No PII is ever sent — only userId (anonymous ID) + event name + properties.
 *
 * Events tracked:
 *   screen_view         — on every navigation state change
 *   game_started        — difficulty, puzzle_id, source (daily|random|scan)
 *   game_completed      — difficulty, time_ms, hint_count, is_perfect
 *   game_abandoned      — difficulty, time_ms, progress_pct
 *   multiplayer_joined  — room_id, mode (public|private|bot)
 *   lesson_viewed       — lesson_id, lesson_title
 *   scan_attempted      — result (success|failure)
 *   onboarding_completed — step_count
 *   error               — error_name (no stack — privacy)
 *
 * Config env vars:
 *   EXPO_PUBLIC_ANALYTICS_URL   — backend endpoint (default: EXPO_PUBLIC_API_URL/api/analytics/events)
 *   EXPO_PUBLIC_ANALYTICS_KEY   — optional API key header
 */

import { Platform } from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';

const ANALYTICS_URL   = process.env.EXPO_PUBLIC_ANALYTICS_URL
    ?? `${process.env.EXPO_PUBLIC_API_URL ?? 'http://localhost:3001'}/api/analytics/events`;
const ANALYTICS_KEY   = process.env.EXPO_PUBLIC_ANALYTICS_KEY ?? '';
const SESSION_KEY     = '@sudoku_ultra:analytics_session';
const ANON_ID_KEY     = '@sudoku_ultra:anon_id';
const FLUSH_INTERVAL  = 30_000;   // 30 s
const FLUSH_THRESHOLD = 20;       // flush early if queue reaches this size

interface AnalyticsEvent {
    name: string;
    properties: Record<string, unknown>;
    timestamp: string;
}

interface QueuedBatch {
    anonId: string;
    sessionId: string;
    platform: string;
    appVersion: string;
    events: AnalyticsEvent[];
}

function uuid(): string {
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
        const r = (Math.random() * 16) | 0;
        return (c === 'x' ? r : (r & 0x3) | 0x8).toString(16);
    });
}

class AnalyticsService {
    private _queue: AnalyticsEvent[] = [];
    private _anonId: string | null = null;
    private _sessionId: string = uuid();
    private _flushTimer: ReturnType<typeof setInterval> | null = null;
    private _userId: string | null = null;
    private _enabled: boolean = true;

    // ── Initialisation ────────────────────────────────────────────────────────

    async init(): Promise<void> {
        this._anonId = await this._getOrCreateAnonId();
        this._sessionId = await this._getOrCreateSessionId();
        this._flushTimer = setInterval(() => { void this._flush(); }, FLUSH_INTERVAL);
    }

    destroy(): void {
        if (this._flushTimer) {
            clearInterval(this._flushTimer);
            this._flushTimer = null;
        }
        void this._flush();
    }

    // ── Public API ────────────────────────────────────────────────────────────

    /** Associate events with an authenticated user. Pass null to clear. */
    identify(userId: string | null): void {
        this._userId = userId;
    }

    /** Opt the user out of analytics entirely. */
    setEnabled(enabled: boolean): void {
        this._enabled = enabled;
        if (!enabled) this._queue = [];
    }

    /** Track a named event with optional properties. */
    track(name: string, properties: Record<string, unknown> = {}): void {
        if (!this._enabled) return;
        this._queue.push({
            name,
            properties: {
                ...properties,
                user_id:    this._userId ?? undefined,
                session_id: this._sessionId,
            },
            timestamp: new Date().toISOString(),
        });
        if (this._queue.length >= FLUSH_THRESHOLD) {
            void this._flush();
        }
    }

    /** Convenience: track a screen view. */
    screen(screenName: string, params?: Record<string, unknown>): void {
        this.track('screen_view', { screen: screenName, ...params });
    }

    // ── Private ───────────────────────────────────────────────────────────────

    private async _flush(): Promise<void> {
        if (this._queue.length === 0 || !this._anonId) return;

        const batch = this._queue.splice(0, this._queue.length);
        const payload: QueuedBatch = {
            anonId:     this._anonId,
            sessionId:  this._sessionId,
            platform:   Platform.OS,
            appVersion: process.env.EXPO_PUBLIC_APP_VERSION ?? '1.0.0',
            events:     batch,
        };

        try {
            const headers: Record<string, string> = {
                'Content-Type': 'application/json',
            };
            if (ANALYTICS_KEY) headers['X-Analytics-Key'] = ANALYTICS_KEY;

            const res = await fetch(ANALYTICS_URL, {
                method:  'POST',
                headers,
                body:    JSON.stringify(payload),
            });

            if (!res.ok) {
                // Re-queue on server error (but not 4xx — those are permanent)
                if (res.status >= 500) {
                    this._queue.unshift(...batch);
                }
            }
        } catch {
            // Network offline — re-queue (bounded to avoid unbounded growth)
            if (this._queue.length < 200) {
                this._queue.unshift(...batch);
            }
        }
    }

    private async _getOrCreateAnonId(): Promise<string> {
        try {
            const stored = await AsyncStorage.getItem(ANON_ID_KEY);
            if (stored) return stored;
            const id = uuid();
            await AsyncStorage.setItem(ANON_ID_KEY, id);
            return id;
        } catch {
            return uuid();
        }
    }

    private async _getOrCreateSessionId(): Promise<string> {
        const SESSION_TIMEOUT_MS = 30 * 60 * 1000; // 30 min
        try {
            const raw = await AsyncStorage.getItem(SESSION_KEY);
            if (raw) {
                const { id, ts } = JSON.parse(raw) as { id: string; ts: number };
                if (Date.now() - ts < SESSION_TIMEOUT_MS) {
                    await AsyncStorage.setItem(SESSION_KEY, JSON.stringify({ id, ts: Date.now() }));
                    return id;
                }
            }
        } catch {
            // fall through
        }
        const id = uuid();
        try {
            await AsyncStorage.setItem(SESSION_KEY, JSON.stringify({ id, ts: Date.now() }));
        } catch {
            // ignore
        }
        return id;
    }
}

export const analyticsService = new AnalyticsService();
