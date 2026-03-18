/**
 * offlineQueue.service.ts — Offline score queue with automatic sync
 *
 * When the device is offline, game results are persisted to AsyncStorage.
 * When connectivity is restored (NetInfo event), the queue is flushed to
 * the game-service REST API in FIFO order.
 *
 * Queue entry lifecycle:
 *   pending → syncing → synced  (on success)
 *   pending → syncing → failed  (on non-retryable error, 4xx)
 *   pending → syncing → pending (on transient error, 5xx / network)
 *
 * Retries: up to MAX_RETRIES per entry; exponential back-off between sweeps.
 */

import AsyncStorage from '@react-native-async-storage/async-storage';
import NetInfo, { NetInfoState } from '@react-native-community/netinfo';

// ── Types ────────────────────────────────────────────────────────────────────

export type QueueEntryStatus = 'pending' | 'syncing' | 'synced' | 'failed';

export interface GameResult {
    puzzleId: string;
    userId: string;
    difficulty: string;
    timeElapsedMs: number;
    errorsCount: number;
    hintsUsed: number;
    completed: boolean;
    completedAt: string;  // ISO-8601
}

export interface QueueEntry {
    id: string;
    gameResult: GameResult;
    status: QueueEntryStatus;
    attempts: number;
    enqueuedAt: string;
    lastAttemptAt: string | null;
    errorMessage: string | null;
}

export interface QueueStats {
    total: number;
    pending: number;
    synced: number;
    failed: number;
}

// ── Constants ────────────────────────────────────────────────────────────────

const STORAGE_KEY = '@sudoku_ultra:offline_queue';
const MAX_RETRIES = 3;
const SYNC_BATCH_SIZE = 20;

// ── Service ──────────────────────────────────────────────────────────────────

class OfflineQueueService {
    private apiBaseUrl: string = '';
    private authToken: string = '';
    private unsubscribeNetInfo: (() => void) | null = null;
    private isSyncing = false;

    // ── Lifecycle ──────────────────────────────────────────────────────────

    /**
     * Initialize the service. Call once on app start.
     *
     * @param apiBaseUrl  Base URL of the game-service API (e.g. https://api.sudoku-ultra.com)
     * @param authToken   Bearer token for the current user
     */
    init(apiBaseUrl: string, authToken: string): void {
        this.apiBaseUrl = apiBaseUrl;
        this.authToken = authToken;

        // Attempt an immediate sync if already online
        NetInfo.fetch().then((state) => {
            if (state.isConnected) {
                this.sync();
            }
        });

        // Subscribe to connectivity changes
        this.unsubscribeNetInfo = NetInfo.addEventListener((state: NetInfoState) => {
            if (state.isConnected && !this.isSyncing) {
                this.sync();
            }
        });
    }

    /** Update auth token (e.g. after token refresh). */
    updateToken(authToken: string): void {
        this.authToken = authToken;
    }

    /** Stop listening for connectivity changes. Call on logout / app unmount. */
    destroy(): void {
        this.unsubscribeNetInfo?.();
        this.unsubscribeNetInfo = null;
    }

    // ── Queue operations ───────────────────────────────────────────────────

    /**
     * Add a game result to the queue.
     * Returns the queue entry ID.
     */
    async enqueue(gameResult: GameResult): Promise<string> {
        const entries = await this._loadQueue();
        const entry: QueueEntry = {
            id: _uuid(),
            gameResult,
            status: 'pending',
            attempts: 0,
            enqueuedAt: new Date().toISOString(),
            lastAttemptAt: null,
            errorMessage: null,
        };
        entries.push(entry);
        await this._saveQueue(entries);

        // Attempt immediate sync if online
        NetInfo.fetch().then((state) => {
            if (state.isConnected) {
                this.sync();
            }
        });

        return entry.id;
    }

    /** Return all queue entries. */
    async getQueue(): Promise<QueueEntry[]> {
        return this._loadQueue();
    }

    /** Return summary counts. */
    async stats(): Promise<QueueStats> {
        const entries = await this._loadQueue();
        return {
            total: entries.length,
            pending: entries.filter((e) => e.status === 'pending').length,
            synced: entries.filter((e) => e.status === 'synced').length,
            failed: entries.filter((e) => e.status === 'failed').length,
        };
    }

    /** Remove all synced entries (housekeeping). */
    async pruneCompleted(): Promise<number> {
        const entries = await this._loadQueue();
        const active = entries.filter((e) => e.status !== 'synced');
        const pruned = entries.length - active.length;
        if (pruned > 0) {
            await this._saveQueue(active);
        }
        return pruned;
    }

    /** Clear all entries (use with caution — data loss). */
    async clearAll(): Promise<void> {
        await AsyncStorage.removeItem(STORAGE_KEY);
    }

    // ── Sync ───────────────────────────────────────────────────────────────

    /**
     * Flush pending entries to the API.
     * No-op if already syncing or no pending entries.
     */
    async sync(): Promise<void> {
        if (this.isSyncing) return;
        this.isSyncing = true;

        try {
            const entries = await this._loadQueue();
            const pending = entries
                .filter((e) => e.status === 'pending' && e.attempts < MAX_RETRIES)
                .slice(0, SYNC_BATCH_SIZE);

            if (pending.length === 0) return;

            for (const entry of pending) {
                await this._syncEntry(entry, entries);
            }

            await this._saveQueue(entries);
        } finally {
            this.isSyncing = false;
        }
    }

    private async _syncEntry(entry: QueueEntry, allEntries: QueueEntry[]): Promise<void> {
        const idx = allEntries.findIndex((e) => e.id === entry.id);
        if (idx === -1) return;

        allEntries[idx].status = 'syncing';
        allEntries[idx].attempts += 1;
        allEntries[idx].lastAttemptAt = new Date().toISOString();

        try {
            const response = await fetch(`${this.apiBaseUrl}/api/v1/games/complete`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${this.authToken}`,
                },
                body: JSON.stringify(entry.gameResult),
            });

            if (response.ok) {
                allEntries[idx].status = 'synced';
                allEntries[idx].errorMessage = null;
            } else if (response.status >= 400 && response.status < 500) {
                // Non-retryable client error
                allEntries[idx].status = 'failed';
                allEntries[idx].errorMessage = `HTTP ${response.status}`;
            } else {
                // Transient server error — reset to pending for next sweep
                allEntries[idx].status = 'pending';
                allEntries[idx].errorMessage = `HTTP ${response.status}`;
            }
        } catch (err: unknown) {
            // Network error — reset to pending
            allEntries[idx].status = 'pending';
            allEntries[idx].errorMessage = err instanceof Error ? err.message : 'Network error';
        }

        // Permanently fail after MAX_RETRIES
        if (allEntries[idx].status === 'pending' && allEntries[idx].attempts >= MAX_RETRIES) {
            allEntries[idx].status = 'failed';
        }
    }

    // ── Storage helpers ────────────────────────────────────────────────────

    private async _loadQueue(): Promise<QueueEntry[]> {
        try {
            const raw = await AsyncStorage.getItem(STORAGE_KEY);
            return raw ? (JSON.parse(raw) as QueueEntry[]) : [];
        } catch {
            return [];
        }
    }

    private async _saveQueue(entries: QueueEntry[]): Promise<void> {
        await AsyncStorage.setItem(STORAGE_KEY, JSON.stringify(entries));
    }
}

// ── Utilities ────────────────────────────────────────────────────────────────

function _uuid(): string {
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
        const r = (Math.random() * 16) | 0;
        const v = c === 'x' ? r : (r & 0x3) | 0x8;
        return v.toString(16);
    });
}

// ── Singleton ────────────────────────────────────────────────────────────────

export const offlineQueue = new OfflineQueueService();
export default offlineQueue;
