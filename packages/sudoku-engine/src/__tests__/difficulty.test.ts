import { Difficulty } from '@sudoku-ultra/shared-types';
import { classifyDifficulty, getDifficulty } from '../difficulty';

// ─── Fixtures ─────────────────────────────────────────────────────────────────

// Very easy — 50 clues, solvable with naked singles only
const _BEGINNER_GRID: number[][] = [
    [8, 2, 7, 1, 5, 4, 3, 9, 6],
    [9, 6, 5, 3, 2, 7, 1, 4, 8],
    [3, 4, 1, 6, 8, 9, 7, 5, 2],
    [5, 9, 3, 4, 6, 8, 2, 7, 1],
    [4, 7, 2, 5, 1, 3, 6, 8, 9],
    [6, 1, 8, 9, 7, 2, 4, 3, 5],
    [7, 8, 6, 2, 3, 5, 9, 1, 4],
    [1, 5, 4, 7, 9, 6, 8, 2, 3],
    [2, 3, 9, 8, 4, 1, 5, 6, 0], // 1 empty = 80 clues (too many for real beginner, but tests classification)
];

// Easy puzzle — 46 clues
const EASY_PUZZLE_CLASSIFIED: number[][] = [
    [5, 3, 0, 0, 7, 0, 0, 0, 0],
    [6, 0, 0, 1, 9, 5, 0, 0, 0],
    [0, 9, 8, 0, 0, 0, 0, 6, 0],
    [8, 0, 0, 0, 6, 0, 0, 0, 3],
    [4, 0, 0, 8, 0, 3, 0, 0, 1],
    [7, 0, 0, 0, 2, 0, 0, 0, 6],
    [0, 6, 0, 0, 0, 0, 2, 8, 0],
    [0, 0, 0, 4, 1, 9, 0, 0, 5],
    [0, 0, 0, 0, 8, 0, 0, 7, 9],
];

// Evil-range puzzle — only 17 clues
const EVIL_PUZZLE: number[][] = [
    [0, 0, 0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 3, 0, 8, 5],
    [0, 0, 1, 0, 2, 0, 0, 0, 0],
    [0, 0, 0, 5, 0, 7, 0, 0, 0],
    [0, 0, 4, 0, 0, 0, 1, 0, 0],
    [0, 9, 0, 0, 0, 0, 0, 0, 0],
    [5, 0, 0, 0, 0, 0, 0, 7, 3],
    [0, 0, 2, 0, 1, 0, 0, 0, 0],
    [0, 0, 0, 0, 4, 0, 0, 0, 9],
];

describe('classifyDifficulty()', () => {
    it('returns a DifficultyAnalysis object with required fields', () => {
        const analysis = classifyDifficulty(EASY_PUZZLE_CLASSIFIED);
        expect(analysis).toHaveProperty('difficulty');
        expect(analysis).toHaveProperty('clueCount');
        expect(analysis).toHaveProperty('emptyCells');
        expect(analysis).toHaveProperty('score');
        expect(analysis).toHaveProperty('solvableWithBasicConstraints');
        expect(analysis).toHaveProperty('requiresBacktracking');
    });

    it('classifies the easy puzzle as BEGINNER, EASY, or MEDIUM (within basic range)', () => {
        const analysis = classifyDifficulty(EASY_PUZZLE_CLASSIFIED);
        const easyDifficulties: Difficulty[] = [Difficulty.BEGINNER, Difficulty.EASY, Difficulty.MEDIUM];
        expect(easyDifficulties).toContain(analysis.difficulty);
    });

    it('classifies evil-range puzzle as EXPERT or EVIL', () => {
        const analysis = classifyDifficulty(EVIL_PUZZLE);
        const hardDifficulties: Difficulty[] = [Difficulty.EXPERT, Difficulty.EVIL];
        expect(hardDifficulties).toContain(analysis.difficulty);
    });

    it('clueCount + emptyCells = 81', () => {
        const analysis = classifyDifficulty(EASY_PUZZLE_CLASSIFIED);
        expect(analysis.clueCount + analysis.emptyCells).toBe(81);
    });

    it('score is between 0 and 100', () => {
        const analysis = classifyDifficulty(EASY_PUZZLE_CLASSIFIED);
        expect(analysis.score).toBeGreaterThanOrEqual(0);
        expect(analysis.score).toBeLessThanOrEqual(100);
    });

    it('easier puzzles have lower score than harder puzzles', () => {
        const easyAnalysis = classifyDifficulty(EASY_PUZZLE_CLASSIFIED);
        const evilAnalysis = classifyDifficulty(EVIL_PUZZLE);
        expect(easyAnalysis.score).toBeLessThan(evilAnalysis.score);
    });

    it('easy puzzle is solvable with basic constraints', () => {
        const analysis = classifyDifficulty(EASY_PUZZLE_CLASSIFIED);
        expect(analysis.solvableWithBasicConstraints).toBe(true);
    });
});

describe('getDifficulty()', () => {
    it('returns a valid Difficulty enum value', () => {
        const difficulty = getDifficulty(EASY_PUZZLE_CLASSIFIED);
        expect(Object.values(Difficulty)).toContain(difficulty);
    });

    it('returns EXPERT or EVIL for the evil-range puzzle', () => {
        const difficulty = getDifficulty(EVIL_PUZZLE);
        expect([Difficulty.EXPERT, Difficulty.EVIL]).toContain(difficulty);
    });
});
