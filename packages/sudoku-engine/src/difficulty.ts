import { Difficulty } from '@sudoku-ultra/shared-types';
import { EMPTY_VALUE, GRID_SIZE, CLUE_RANGES } from './constants';
import { countClues } from './utils';
import { solveWithNakedSinglesOnly, solveWithBasicConstraints, isSolvableWithBasicConstraints } from './solver';

// ─── Difficulty Classifier ────────────────────────────────────────────────────

/**
 * Difficulty analysis result providing detailed metrics about a puzzle.
 */
export interface DifficultyAnalysis {
    difficulty: Difficulty;
    clueCount: number;
    emptyCells: number;
    nakedSinglesFilled: number;
    basicConstraintsFilled: number;
    solvableWithBasicConstraints: boolean;
    requiresBacktracking: boolean;
    score: number;
}

/**
 * Classify the difficulty of a puzzle using rule-based analysis.
 *
 * Classification factors:
 * 1. Number of given clues
 * 2. Whether the puzzle can be solved with naked singles alone
 * 3. Whether it can be solved with naked + hidden singles
 * 4. Whether it requires backtracking (trial & error)
 */
export function classifyDifficulty(grid: number[][]): DifficultyAnalysis {
    const clueCount = countClues(grid);
    const emptyCells = GRID_SIZE * GRID_SIZE - clueCount;

    // Technique analysis
    const nakedSinglesFilled = solveWithNakedSinglesOnly(grid);
    const basicConstraintsFilled = solveWithBasicConstraints(grid);
    const canSolveBasic = isSolvableWithBasicConstraints(grid);
    const requiresBacktracking = !canSolveBasic;

    // Compute a difficulty score (0–100)
    const score = computeDifficultyScore(
        clueCount,
        emptyCells,
        nakedSinglesFilled,
        basicConstraintsFilled,
        canSolveBasic,
    );

    // Map score to difficulty level
    const difficulty = scoreToDifficulty(score, clueCount);

    return {
        difficulty,
        clueCount,
        emptyCells,
        nakedSinglesFilled: Math.max(0, nakedSinglesFilled),
        basicConstraintsFilled: Math.max(0, basicConstraintsFilled),
        solvableWithBasicConstraints: canSolveBasic,
        requiresBacktracking,
        score,
    };
}

/**
 * Quick difficulty classification returning just the difficulty level.
 */
export function getDifficulty(grid: number[][]): Difficulty {
    return classifyDifficulty(grid).difficulty;
}

// ─── Internal: Scoring ────────────────────────────────────────────────────────

function computeDifficultyScore(
    clueCount: number,
    emptyCells: number,
    nakedSinglesFilled: number,
    basicConstraintsFilled: number,
    canSolveBasic: boolean,
): number {
    let score = 0;

    // Fewer clues = harder (0–30 points)
    // 50 clues → 0 points, 17 clues → 30 points
    score += Math.round(((50 - clueCount) / 33) * 30);

    // If naked singles alone solve most of the puzzle, it's easier (-10 to +10)
    const nakedRatio = nakedSinglesFilled > 0 ? nakedSinglesFilled / emptyCells : 0;
    if (nakedRatio > 0.8) {
        score -= 10;
    } else if (nakedRatio < 0.3) {
        score += 10;
    }

    // If basic constraints can't solve it, it's harder (+20)
    if (!canSolveBasic) {
        score += 20;
    } else {
        // If basic constraints solve it, how efficiently?
        const basicRatio = basicConstraintsFilled / emptyCells;
        if (basicRatio < 0.5) {
            score += 10;
        }
    }

    // More empty cells = harder (0–20 points)
    score += Math.round((emptyCells / 64) * 20);

    return Math.max(0, Math.min(100, score));
}

function scoreToDifficulty(score: number, clueCount: number): Difficulty {
    // Hard clue-count boundaries take priority
    if (clueCount >= CLUE_RANGES[Difficulty.BEGINNER].min) return Difficulty.BEGINNER;
    if (clueCount <= CLUE_RANGES[Difficulty.EVIL].max) {
        // Within evil clue range — check if it truly requires backtracking
        if (score >= 60) return Difficulty.EVIL;
        return Difficulty.EXPERT;
    }

    // Score-based classification for the middle range
    if (score <= 15) return Difficulty.BEGINNER;
    if (score <= 30) return Difficulty.EASY;
    if (score <= 45) return Difficulty.MEDIUM;
    if (score <= 60) return Difficulty.HARD;
    if (score <= 75) return Difficulty.EXPERT;
    return Difficulty.EVIL;
}
