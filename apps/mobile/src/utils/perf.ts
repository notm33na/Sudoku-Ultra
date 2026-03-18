/**
 * perf.ts — Performance instrumentation utilities
 *
 * Thin wrapper around React Native Performance API and Flipper.
 * Falls back gracefully when Flipper is not connected (production builds).
 *
 * Usage:
 *   import { perf } from '../utils/perf';
 *
 *   const mark = perf.mark('classifier:inference');
 *   await runInference();
 *   const ms = perf.measure(mark, 'classifier:inference');
 *
 * Flipper integration:
 *   Requires `react-native-flipper` installed and the Hermes debugger open.
 *   Timeline events appear in Flipper → Performance → Timeline.
 */

// ── Types ────────────────────────────────────────────────────────────────────

export interface PerfMark {
    name: string;
    startMs: number;
}

export interface PerfMeasure {
    name: string;
    durationMs: number;
}

// ── Flipper plugin shim ───────────────────────────────────────────────────────
// react-native-flipper is a dev-only dependency and may not be importable
// in production bundles. We attempt a dynamic require and silently fall back.

type FlipperClient = {
    addPlugin: (plugin: {
        getId: () => string;
        onConnect: (connection: FlipperConnection) => void;
        onDisconnect: () => void;
        runInBackground: () => boolean;
    }) => void;
};

type FlipperConnection = {
    send: (method: string, params: Record<string, unknown>) => void;
};

let flipperConnection: FlipperConnection | null = null;

function _initFlipper(): void {
    try {
        // eslint-disable-next-line @typescript-eslint/no-var-requires
        const { addPlugin } = require('react-native-flipper') as FlipperClient;
        addPlugin({
            getId: () => 'sudoku-ultra-perf',
            onConnect(connection) {
                flipperConnection = connection;
            },
            onDisconnect() {
                flipperConnection = null;
            },
            runInBackground: () => true,
        });
    } catch {
        // Flipper not available — no-op
    }
}

// Initialise once at import time; harmless in production
_initFlipper();

// ── React Native Performance API shim ────────────────────────────────────────
// RN 0.72+ exposes `performance` globally on Hermes. Fallback to Date.now().

function _now(): number {
    if (typeof performance !== 'undefined' && typeof performance.now === 'function') {
        return performance.now();
    }
    return Date.now();
}

// ── Service ──────────────────────────────────────────────────────────────────

class PerfService {
    private readonly _measures: PerfMeasure[] = [];

    /**
     * Start timing a named section. Returns an opaque mark handle.
     *
     * @param name  Descriptive label, e.g. "classifier:inference"
     */
    mark(name: string): PerfMark {
        const m: PerfMark = { name, startMs: _now() };

        // Emit to RN performance timeline if available
        if (typeof performance !== 'undefined' && typeof performance.mark === 'function') {
            try {
                performance.mark(`${name}:start`);
            } catch {
                // Some RN versions throw on duplicate mark names
            }
        }

        this._sendFlipper('mark:start', { name, ts: m.startMs });
        return m;
    }

    /**
     * End timing and return the elapsed duration in milliseconds.
     * Also records the measure in the in-memory log.
     *
     * @param mark   Handle returned by perf.mark()
     * @param label  Optional override label for the measure
     */
    measure(mark: PerfMark, label?: string): number {
        const endMs = _now();
        const durationMs = endMs - mark.startMs;
        const name = label ?? mark.name;

        const m: PerfMeasure = { name, durationMs };
        this._measures.push(m);

        // Emit to RN performance timeline
        if (
            typeof performance !== 'undefined' &&
            typeof performance.measure === 'function'
        ) {
            try {
                performance.measure(name, `${mark.name}:start`);
            } catch {
                // Ignore — mark may have been GC'd
            }
        }

        this._sendFlipper('measure', { name, durationMs, startMs: mark.startMs, endMs });
        return durationMs;
    }

    /**
     * Time an async function and return both the result and elapsed ms.
     *
     * @example
     *   const { result, durationMs } = await perf.time('scan:full', () => scanImage(img));
     */
    async time<T>(name: string, fn: () => Promise<T>): Promise<{ result: T; durationMs: number }> {
        const mark = this.mark(name);
        const result = await fn();
        const durationMs = this.measure(mark, name);
        return { result, durationMs };
    }

    /**
     * Return all recorded measures. Useful for test assertions.
     */
    getMeasures(): PerfMeasure[] {
        return [...this._measures];
    }

    /**
     * Clear the in-memory measure log.
     */
    clearMeasures(): void {
        this._measures.length = 0;
    }

    /**
     * Log a custom event to Flipper (no timing).
     */
    event(name: string, payload: Record<string, unknown> = {}): void {
        this._sendFlipper('event', { name, ts: _now(), ...payload });
    }

    private _sendFlipper(method: string, params: Record<string, unknown>): void {
        try {
            flipperConnection?.send(method, params);
        } catch {
            // Never let Flipper crash the app
        }
    }
}

// ── Singleton export ─────────────────────────────────────────────────────────

export const perf = new PerfService();
export default perf;
