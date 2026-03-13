/**
 * Sudoku Ultra — On-Device AI Service
 *
 * 3-tier fallback chain for difficulty classification:
 *   Tier 1 — On-device ONNX inference via onnxruntime-react-native  (~10-50ms)
 *   Tier 2 — ml-service REST API with 3s timeout                    (~100-500ms)
 *   Tier 3 — Rule-based clue-count heuristic                        (<1ms)
 *
 * The source of each result is reported so the AIStatusIndicator can
 * show the correct mode to the user.
 */

import { Asset } from 'expo-asset';

// Dynamic import — degrades gracefully if package is not installed
// (e.g. in CI/web builds where native modules are unavailable).
let InferenceSession: any = null;
let OrtTensor: any = null;
try {
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    const ort = require('onnxruntime-react-native');
    InferenceSession = ort.InferenceSession;
    OrtTensor = ort.Tensor;
} catch {
    // onnxruntime-react-native not available — Tier 1 will be skipped
}

// ─── Types ────────────────────────────────────────────────────────────────────

export type Difficulty =
    | 'super_easy'
    | 'easy'
    | 'medium'
    | 'hard'
    | 'super_hard'
    | 'extreme';

export interface PuzzleFeatures {
    clueCount: number;
    nakedSingles: number;
    hiddenSingles: number;
    nakedPairs: number;
    pointingPairs: number;
    boxLineReduction: number;
    backtrackDepth: number;
    constraintDensity: number;
    symmetryScore: number;
    avgCandidateCount: number;
}

export interface ClassificationResult {
    difficulty: Difficulty;
    confidence: number;
    source: 'on-device' | 'api' | 'rule-based';
    latencyMs: number;
}

// ─── Constants ────────────────────────────────────────────────────────────────

const DIFFICULTY_LABELS: Difficulty[] = [
    'super_easy',
    'easy',
    'medium',
    'hard',
    'super_hard',
    'extreme',
];

const API_TIMEOUT_MS = 3000;

// ─── Tier 1 — On-Device ONNX ─────────────────────────────────────────────────

let onDeviceSession: any | null = null;
let onDeviceAvailable = false;

/**
 * Load the bundled ONNX classifier into an onnxruntime InferenceSession.
 * Call once at app startup (e.g. in App.tsx useEffect).
 *
 * Requires: assets/models/classifier.onnx to be present in the bundle.
 * If the file or package is missing, returns false and the fallback chain
 * handles all subsequent calls transparently.
 */
export async function initOnDeviceModel(): Promise<boolean> {
    if (!InferenceSession) {
        console.log('[EdgeAI] onnxruntime-react-native not available — skipping on-device init');
        return false;
    }

    try {
        // eslint-disable-next-line @typescript-eslint/no-var-requires
        const asset = Asset.fromModule(require('../../assets/models/classifier.onnx'));
        await asset.downloadAsync();

        if (!asset.localUri) {
            throw new Error('Asset localUri is null after download');
        }

        onDeviceSession = await InferenceSession.create(asset.localUri);
        onDeviceAvailable = true;
        console.log('[EdgeAI] On-device ONNX classifier loaded ✓');
        return true;
    } catch (error) {
        console.warn('[EdgeAI] Failed to load on-device model:', error);
        onDeviceAvailable = false;
        return false;
    }
}

async function _classifyOnDevice(
    features: PuzzleFeatures,
): Promise<{ difficulty: Difficulty; confidence: number } | null> {
    if (!onDeviceAvailable || !onDeviceSession || !OrtTensor) return null;

    const inputArray = new Float32Array([
        features.clueCount,
        features.nakedSingles,
        features.hiddenSingles,
        features.nakedPairs,
        features.pointingPairs,
        features.boxLineReduction,
        features.backtrackDepth,
        features.constraintDensity,
        features.symmetryScore,
        features.avgCandidateCount,
    ]);

    const tensor = new OrtTensor('float32', inputArray, [1, 10]);

    // skl2onnx RF outputs: 'label' (predicted class) and 'probabilities' (ZipMap)
    const result = await onDeviceSession.run({ features: tensor });

    const label = result['label']?.data?.[0] as string | undefined;
    if (!label) return null;

    const difficulty = label as Difficulty;

    // Extract confidence from probabilities ZipMap if available
    let confidence = 0.85;
    const probs = result['probabilities'];
    if (probs?.data && Array.isArray(probs.data) && probs.data[0]) {
        const probMap: Record<string, number> = probs.data[0];
        confidence = probMap[difficulty] ?? 0.85;
    }

    return { difficulty, confidence };
}

// ─── Tier 2 — API ────────────────────────────────────────────────────────────

async function _classifyViaAPI(
    features: PuzzleFeatures,
    baseUrl: string,
): Promise<{ difficulty: Difficulty; confidence: number } | null> {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), API_TIMEOUT_MS);

    try {
        const response = await fetch(`${baseUrl}/api/v1/classify`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                clue_count: features.clueCount,
                naked_singles: features.nakedSingles,
                hidden_singles: features.hiddenSingles,
                naked_pairs: features.nakedPairs,
                pointing_pairs: features.pointingPairs,
                box_line_reduction: features.boxLineReduction,
                backtrack_depth: features.backtrackDepth,
                constraint_density: features.constraintDensity,
                symmetry_score: features.symmetryScore,
                avg_candidate_count: features.avgCandidateCount,
            }),
            signal: controller.signal,
        });
        if (!response.ok) return null;
        const data = await response.json();
        return { difficulty: data.difficulty as Difficulty, confidence: data.confidence };
    } catch {
        return null;
    } finally {
        clearTimeout(timeout);
    }
}

// ─── Tier 3 — Rule-Based ─────────────────────────────────────────────────────

function _classifyRuleBased(
    features: PuzzleFeatures,
): { difficulty: Difficulty; confidence: number } {
    const { clueCount } = features;
    let difficulty: Difficulty;
    if (clueCount >= 45)      difficulty = 'super_easy';
    else if (clueCount >= 36) difficulty = 'easy';
    else if (clueCount >= 30) difficulty = 'medium';
    else if (clueCount >= 26) difficulty = 'hard';
    else if (clueCount >= 22) difficulty = 'super_hard';
    else                      difficulty = 'extreme';
    return { difficulty, confidence: 0.5 };
}

// ─── Public API ───────────────────────────────────────────────────────────────

/**
 * Classify puzzle difficulty using the 3-tier fallback chain.
 *
 * Performance targets (mid-range Android):
 *   Tier 1 (on-device): <50ms
 *   Tier 2 (API):       <500ms (3s timeout)
 *   Tier 3 (heuristic): <1ms
 */
export async function classifyDifficulty(
    features: PuzzleFeatures,
    mlServiceUrl?: string,
): Promise<ClassificationResult> {
    const start = Date.now();

    // Tier 1
    try {
        const result = await _classifyOnDevice(features);
        if (result) {
            return { ...result, source: 'on-device', latencyMs: Date.now() - start };
        }
    } catch {
        /* fall through */
    }

    // Tier 2
    if (mlServiceUrl) {
        try {
            const result = await _classifyViaAPI(features, mlServiceUrl);
            if (result) {
                return { ...result, source: 'api', latencyMs: Date.now() - start };
            }
        } catch {
            /* fall through */
        }
    }

    // Tier 3
    const result = _classifyRuleBased(features);
    return { ...result, source: 'rule-based', latencyMs: Date.now() - start };
}

export function getAIStatus(): {
    onDeviceAvailable: boolean;
    source: 'on-device' | 'api' | 'rule-based';
} {
    return {
        onDeviceAvailable,
        source: onDeviceAvailable ? 'on-device' : 'api',
    };
}
