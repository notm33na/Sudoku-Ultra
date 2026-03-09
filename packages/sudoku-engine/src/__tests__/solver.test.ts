import { solve, hasUniqueSolution, countSolutions, solveWithNakedSinglesOnly, isSolvableWithBasicConstraints } from '../solver';

// ─── Fixtures ─────────────────────────────────────────────────────────────────

const SOLVED_GRID: number[][] = [
    [5, 3, 4, 6, 7, 8, 9, 1, 2],
    [6, 7, 2, 1, 9, 5, 3, 4, 8],
    [1, 9, 8, 3, 4, 2, 5, 6, 7],
    [8, 5, 9, 7, 6, 1, 4, 2, 3],
    [4, 2, 6, 8, 5, 3, 7, 9, 1],
    [7, 1, 3, 9, 2, 4, 8, 5, 6],
    [9, 6, 1, 5, 3, 7, 2, 8, 4],
    [2, 8, 7, 4, 1, 9, 6, 3, 5],
    [3, 4, 5, 2, 8, 6, 1, 7, 9],
];

// Classic easy Sudoku puzzle — unique solution, solvable with basic constraints
const EASY_PUZZLE: number[][] = [
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

// Unsolvable — duplicate 1 in row 0 + same box
const UNSOLVABLE_GRID: number[][] = [
    [1, 1, 0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0, 0, 0],
];

// Almost solved — only 2 cells empty in row 0 (fast, guaranteed unique)
const ALMOST_SOLVED: number[][] = SOLVED_GRID.map((row, r) =>
    row.map((val, c) => (r === 0 && (c === 2 || c === 3) ? 0 : val)),
);

describe('solve()', () => {
    it('solves an easy puzzle to the correct solution', () => {
        const result = solve(EASY_PUZZLE);
        expect(result).not.toBeNull();
        expect(result).toEqual(SOLVED_GRID);
    });

    it('returns null for an unsolvable grid', () => {
        expect(solve(UNSOLVABLE_GRID)).toBeNull();
    });

    it('solves an almost-completed grid', () => {
        const result = solve(ALMOST_SOLVED);
        expect(result).not.toBeNull();
        expect(result![0][2]).toBe(4);
        expect(result![0][3]).toBe(6);
    });

    it('does not mutate the input grid', () => {
        const input = EASY_PUZZLE.map((r) => [...r]);
        const snapshot = EASY_PUZZLE.map((r) => [...r]);
        solve(input);
        expect(input).toEqual(snapshot);
    });

    it('produces a grid with all values 1–9 in each row', () => {
        const result = solve(EASY_PUZZLE)!;
        for (let r = 0; r < 9; r++) {
            expect([...result[r]].sort((a, b) => a - b)).toEqual([1, 2, 3, 4, 5, 6, 7, 8, 9]);
        }
    });

    it('produces a grid with all values 1–9 in each column', () => {
        const result = solve(EASY_PUZZLE)!;
        for (let c = 0; c < 9; c++) {
            const col = result.map((r) => r[c]).sort((a, b) => a - b);
            expect(col).toEqual([1, 2, 3, 4, 5, 6, 7, 8, 9]);
        }
    });

    it('produces a grid with all values 1–9 in each box', () => {
        const result = solve(EASY_PUZZLE)!;
        for (let boxRow = 0; boxRow < 3; boxRow++) {
            for (let boxCol = 0; boxCol < 3; boxCol++) {
                const values: number[] = [];
                for (let r = boxRow * 3; r < boxRow * 3 + 3; r++) {
                    for (let c = boxCol * 3; c < boxCol * 3 + 3; c++) {
                        values.push(result[r][c]);
                    }
                }
                expect(values.sort((a, b) => a - b)).toEqual([1, 2, 3, 4, 5, 6, 7, 8, 9]);
            }
        }
    });
});

describe('hasUniqueSolution()', () => {
    it('returns true for the easy puzzle', () => {
        expect(hasUniqueSolution(EASY_PUZZLE)).toBe(true);
    });

    it('returns true for the almost-solved puzzle', () => {
        expect(hasUniqueSolution(ALMOST_SOLVED)).toBe(true);
    });
});

describe('countSolutions()', () => {
    it('counts 1 solution for a well-formed puzzle', () => {
        expect(countSolutions(EASY_PUZZLE, 2)).toBe(1);
    });

    it('counts 0 for an unsolvable grid', () => {
        expect(countSolutions(UNSOLVABLE_GRID, 2)).toBe(0);
    });

    it('respects the limit parameter', () => {
        // limit=1: stops after first solution found
        expect(countSolutions(EASY_PUZZLE, 1)).toBe(1);
    });
});

describe('solveWithNakedSinglesOnly()', () => {
    it('returns a positive count for easy puzzles', () => {
        const count = solveWithNakedSinglesOnly(EASY_PUZZLE);
        expect(count).toBeGreaterThan(0);
    });

    it('fills both cells for the almost-solved puzzle', () => {
        const count = solveWithNakedSinglesOnly(ALMOST_SOLVED);
        expect(count).toBe(2);
    });
});

describe('isSolvableWithBasicConstraints()', () => {
    it('returns true for the easy puzzle', () => {
        expect(isSolvableWithBasicConstraints(EASY_PUZZLE)).toBe(true);
    });

    it('returns true for the almost-solved puzzle', () => {
        expect(isSolvableWithBasicConstraints(ALMOST_SOLVED)).toBe(true);
    });
});
