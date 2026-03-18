/**
 * edgeAI.benchmark.ts — On-device Edge AI latency benchmarks
 *
 * Measures inference latency for 3 ONNX models across 3 simulated device tiers:
 *   - classifier   (difficulty-classifier.onnx  — 10 features)
 *   - clustering   (clustering.onnx             — 8 features)
 *   - scanner      (scanner.onnx                — 64×64 image tensor)
 *
 * Device profiles (simulated inference overhead):
 *   - high-end    : Pixel 8 / iPhone 15 — target ≤30ms
 *   - mid-range   : Pixel 6a / iPhone 12 mini — target ≤80ms
 *   - low-end     : Android Go / 2 GB RAM device — target ≤200ms (hard limit)
 *
 * Run via: npx ts-node apps/mobile/src/benchmarks/edgeAI.benchmark.ts
 * Or in Jest: import and call runBenchmarks()
 */

export interface DeviceProfile {
    name: string;
    classifierMs: number;  // simulated inference duration
    clusteringMs: number;
    scannerMs: number;
    hardLimitMs: number;   // fail if inference exceeds this
}

export interface BenchmarkResult {
    model: string;
    device: string;
    inferenceMs: number;
    withinBudget: boolean;
    hardLimitMs: number;
}

export interface BenchmarkSummary {
    totalRuns: number;
    passed: number;
    failed: number;
    results: BenchmarkResult[];
}

// ── Device profiles ──────────────────────────────────────────────────────────

export const DEVICE_PROFILES: DeviceProfile[] = [
    {
        name: 'high-end',
        classifierMs: 18,
        clusteringMs: 12,
        scannerMs: 25,
        hardLimitMs: 50,
    },
    {
        name: 'mid-range',
        classifierMs: 55,
        clusteringMs: 40,
        scannerMs: 70,
        hardLimitMs: 100,
    },
    {
        name: 'low-end',
        classifierMs: 130,
        clusteringMs: 90,
        scannerMs: 160,
        hardLimitMs: 200,
    },
];

// ── Feature fixtures ─────────────────────────────────────────────────────────

/** 10-element classifier feature vector (difficulty analysis features) */
export const CLASSIFIER_FEATURES = new Float32Array([
    36,    // clue_count
    12,    // naked_singles
    5,     // hidden_singles
    2,     // pointing_pairs
    1,     // box_reductions
    1,     // naked_pairs
    0,     // naked_triples
    0,     // x_wings
    0,     // swordfish
    1.2,   // branching_factor
]);

/** 8-element clustering feature vector (skill segment features) */
export const CLUSTERING_FEATURES = new Float32Array([
    180,   // avg_solve_time_easy (seconds)
    420,   // avg_solve_time_medium
    900,   // avg_solve_time_hard
    0.3,   // hint_rate
    2.1,   // error_rate
    0.75,  // completion_rate
    3.0,   // difficulty_spread
    22,    // games_last_30d
]);

/** Flat 64×64 grayscale image tensor (scanner input) */
export const SCANNER_IMAGE = new Float32Array(64 * 64).fill(0.5);

// ── Mock ONNX session ────────────────────────────────────────────────────────

/**
 * Simulates an OnnxRuntime InferenceSession with configurable latency.
 * Used in benchmarks and Jest tests where the native runtime is unavailable.
 */
export function createMockSession(inferenceMs: number) {
    return {
        run: async (_inputs: Record<string, unknown>): Promise<Record<string, { data: unknown[] }>> => {
            await sleep(inferenceMs);
            return {
                label: { data: ['medium'] },
                probabilities: { data: [{ medium: 0.82, hard: 0.12, easy: 0.06 }] },
            };
        },
    };
}

// ── Benchmark runner ─────────────────────────────────────────────────────────

async function benchmarkModel(
    modelName: string,
    session: { run: (inputs: Record<string, unknown>) => Promise<unknown> },
    inputs: Record<string, unknown>,
    device: DeviceProfile,
    hardLimitMs: number,
): Promise<BenchmarkResult> {
    const t0 = Date.now();
    await session.run(inputs);
    const inferenceMs = Date.now() - t0;

    return {
        model: modelName,
        device: device.name,
        inferenceMs,
        withinBudget: inferenceMs <= hardLimitMs,
        hardLimitMs,
    };
}

/**
 * Run all 3 models × 3 device profiles and return a summary.
 *
 * @param warmupRuns  number of warm-up iterations before measurement (default 2)
 * @param measureRuns number of timed iterations to average (default 5)
 */
export async function runBenchmarks(
    warmupRuns = 2,
    measureRuns = 5,
): Promise<BenchmarkSummary> {
    const results: BenchmarkResult[] = [];

    for (const device of DEVICE_PROFILES) {
        const classifierSession = createMockSession(device.classifierMs);
        const clusteringSession = createMockSession(device.clusteringMs);
        const scannerSession    = createMockSession(device.scannerMs);

        const models: Array<{
            name: string;
            session: ReturnType<typeof createMockSession>;
            inputs: Record<string, unknown>;
            limitMs: number;
        }> = [
            { name: 'classifier', session: classifierSession, inputs: { features: CLASSIFIER_FEATURES }, limitMs: device.hardLimitMs },
            { name: 'clustering', session: clusteringSession, inputs: { features: CLUSTERING_FEATURES }, limitMs: device.hardLimitMs },
            { name: 'scanner',    session: scannerSession,    inputs: { image: SCANNER_IMAGE },          limitMs: device.hardLimitMs },
        ];

        for (const m of models) {
            // Warm-up (not recorded)
            for (let i = 0; i < warmupRuns; i++) {
                await m.session.run(m.inputs);
            }

            // Timed runs — take the median
            const times: number[] = [];
            for (let i = 0; i < measureRuns; i++) {
                const t0 = Date.now();
                await m.session.run(m.inputs);
                times.push(Date.now() - t0);
            }
            times.sort((a, b) => a - b);
            const medianMs = times[Math.floor(times.length / 2)];

            results.push({
                model: m.name,
                device: device.name,
                inferenceMs: medianMs,
                withinBudget: medianMs <= m.limitMs,
                hardLimitMs: m.limitMs,
            });
        }
    }

    const passed = results.filter((r) => r.withinBudget).length;
    return {
        totalRuns: results.length,
        passed,
        failed: results.length - passed,
        results,
    };
}

// ── Utilities ────────────────────────────────────────────────────────────────

function sleep(ms: number): Promise<void> {
    return new Promise((resolve) => setTimeout(resolve, ms));
}

function formatTable(summary: BenchmarkSummary): string {
    const header = ['Model', 'Device', 'Median ms', 'Limit ms', 'Status'].join('\t');
    const rows = summary.results.map((r) =>
        [
            r.model.padEnd(12),
            r.device.padEnd(10),
            String(r.inferenceMs).padStart(9),
            String(r.hardLimitMs).padStart(8),
            r.withinBudget ? 'PASS' : 'FAIL',
        ].join('\t'),
    );
    return [header, ...rows].join('\n');
}

// ── CLI entry point ──────────────────────────────────────────────────────────

if (require.main === module) {
    (async () => {
        console.log('Running Edge AI benchmarks (simulated device profiles)...\n');
        const summary = await runBenchmarks(2, 5);
        console.log(formatTable(summary));
        console.log(`\nSummary: ${summary.passed}/${summary.totalRuns} passed`);
        if (summary.failed > 0) {
            console.error(`\n${summary.failed} benchmark(s) failed — review device profile limits.`);
            process.exit(1);
        }
    })();
}
