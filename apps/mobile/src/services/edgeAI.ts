/**
 * Sudoku Ultra — On-Device AI Service
 *
 * Provides offline difficulty classification using ONNX Runtime
 * with a 3-tier fallback chain:
 *   1. On-device ONNX model inference
 *   2. ml-service API call
 *   3. Rule-based heuristic (clue count)
 */

// PHASE-2-HOOK: Install onnxruntime-react-native when ready
// import { InferenceSession, Tensor } from 'onnxruntime-react-native';

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

// ─── Fallback Chain ───────────────────────────────────────────────────────────

/**
 * Classify puzzle difficulty using the 3-tier fallback chain.
 * Tries on-device ONNX first, then API, then rule-based.
 */
export async function classifyDifficulty(
  features: PuzzleFeatures,
  mlServiceUrl?: string,
): Promise<ClassificationResult> {
  const start = Date.now();

  // Tier 1: On-device ONNX inference
  try {
    const result = await classifyOnDevice(features);
    if (result) {
      return {
        ...result,
        source: 'on-device',
        latencyMs: Date.now() - start,
      };
    }
  } catch {
    // Fall through to API
  }

  // Tier 2: ML Service API
  if (mlServiceUrl) {
    try {
      const result = await classifyViaAPI(features, mlServiceUrl);
      if (result) {
        return {
          ...result,
          source: 'api',
          latencyMs: Date.now() - start,
        };
      }
    } catch {
      // Fall through to rule-based
    }
  }

  // Tier 3: Rule-based heuristic
  const result = classifyRuleBased(features);
  return {
    ...result,
    source: 'rule-based',
    latencyMs: Date.now() - start,
  };
}

// ─── Tier 1: On-Device ────────────────────────────────────────────────────────

let onDeviceSession: any | null = null;
let onDeviceAvailable = false;

/**
 * Initialize the on-device ONNX model.
 * Call this at app startup.
 */
export async function initOnDeviceModel(): Promise<boolean> {
  try {
    // PHASE-2-HOOK: Uncomment when onnxruntime-react-native is installed
    // const modelAsset = Asset.fromModule(require('../../ml/models/classifier.onnx'));
    // await modelAsset.downloadAsync();
    // onDeviceSession = await InferenceSession.create(modelAsset.localUri!);
    // onDeviceAvailable = true;
    // console.log('[EdgeAI] On-device model loaded');

    console.log('[EdgeAI] On-device model not yet bundled — using fallback chain');
    onDeviceAvailable = false;
    return false;
  } catch (error) {
    console.warn('[EdgeAI] Failed to load on-device model:', error);
    onDeviceAvailable = false;
    return false;
  }
}

async function classifyOnDevice(
  features: PuzzleFeatures,
): Promise<{ difficulty: Difficulty; confidence: number } | null> {
  if (!onDeviceAvailable || !onDeviceSession) {
    return null;
  }

  // PHASE-2-HOOK: Uncomment when onnxruntime-react-native is installed
  // const inputArray = new Float32Array([
  //   features.clueCount,
  //   features.nakedSingles,
  //   features.hiddenSingles,
  //   features.nakedPairs,
  //   features.pointingPairs,
  //   features.boxLineReduction,
  //   features.backtrackDepth,
  //   features.constraintDensity,
  //   features.symmetryScore,
  //   features.avgCandidateCount,
  // ]);
  // const tensor = new Tensor('float32', inputArray, [1, 10]);
  // const result = await onDeviceSession.run({ features: tensor });
  // const output = result.label.data as string[];
  // return {
  //   difficulty: output[0] as Difficulty,
  //   confidence: 0.85,
  // };

  return null;
}

// ─── Tier 2: API ──────────────────────────────────────────────────────────────

async function classifyViaAPI(
  features: PuzzleFeatures,
  baseUrl: string,
): Promise<{ difficulty: Difficulty; confidence: number } | null> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 3000);

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
    return {
      difficulty: data.difficulty as Difficulty,
      confidence: data.confidence,
    };
  } catch {
    return null;
  } finally {
    clearTimeout(timeout);
  }
}

// ─── Tier 3: Rule-Based ───────────────────────────────────────────────────────

function classifyRuleBased(
  features: PuzzleFeatures,
): { difficulty: Difficulty; confidence: number } {
  const { clueCount } = features;

  let difficulty: Difficulty;
  if (clueCount >= 45) difficulty = 'super_easy';
  else if (clueCount >= 36) difficulty = 'easy';
  else if (clueCount >= 30) difficulty = 'medium';
  else if (clueCount >= 26) difficulty = 'hard';
  else if (clueCount >= 22) difficulty = 'super_hard';
  else difficulty = 'extreme';

  return { difficulty, confidence: 0.5 };
}

// ─── Status ───────────────────────────────────────────────────────────────────

export function getAIStatus(): {
  onDeviceAvailable: boolean;
  source: 'on-device' | 'api' | 'rule-based';
} {
  return {
    onDeviceAvailable,
    source: onDeviceAvailable ? 'on-device' : 'api',
  };
}
