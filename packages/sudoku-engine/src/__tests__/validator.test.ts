import { validatePlacement, findConflicts, isGridComplete, isGridCorrect, validateCellGrid } from '../validator';
import { createCellGrid } from '../utils';
import { EMPTY_VALUE } from '../constants';

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

const PUZZLE_GRID: number[][] = [
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

describe('validatePlacement()', () => {
    it('returns true for a valid placement with no conflicts', () => {
        expect(validatePlacement(PUZZLE_GRID, 0, 2, 4)).toBe(true);
    });

    it('returns false when the value already exists in the same row', () => {
        // Row 0 has 5 at col 0 — placing 5 at col 2 should fail
        expect(validatePlacement(PUZZLE_GRID, 0, 2, 5)).toBe(false);
    });

    it('returns false when the value already exists in the same column', () => {
        // Col 0 has 5,6,8,4,7 — placing 6 at row 0 col 0 is fine; placing 8 conflicts
        expect(validatePlacement(PUZZLE_GRID, 0, 0, 8)).toBe(false);
    });

    it('returns false when the value already exists in the same box', () => {
        // Box top-left has 5,3,6,9,8 — placing 3 at (0,2) conflicts via box
        expect(validatePlacement(PUZZLE_GRID, 0, 2, 3)).toBe(false);
    });

    it('allows placing a value that equals the existing value in the same cell', () => {
        // The cell itself is excluded from peer checking
        expect(validatePlacement(SOLVED_GRID, 0, 0, 5)).toBe(true);
    });
});

describe('findConflicts()', () => {
    it('returns empty array for a conflict-free puzzle grid', () => {
        expect(findConflicts(PUZZLE_GRID)).toHaveLength(0);
    });

    it('returns empty array for the solved grid', () => {
        expect(findConflicts(SOLVED_GRID)).toHaveLength(0);
    });

    it('detects a row conflict', () => {
        const grid = PUZZLE_GRID.map((r) => [...r]);
        grid[0][2] = 5; // Duplicate 5 in row 0 (already at col 0)
        const conflicts = findConflicts(grid);
        const positions = conflicts.map((c) => `${c.row},${c.col}`);
        expect(positions).toContain('0,0');
        expect(positions).toContain('0,2');
    });

    it('detects a column conflict', () => {
        const grid = PUZZLE_GRID.map((r) => [...r]);
        grid[1][0] = 5; // Duplicate 5 in col 0 (already at row 0, col 0)
        // Row 1, col 0 gets 5 — but row 1 also has 6 at col 0 in original
        // Override to ensure col conflict
        grid[1][0] = 8; // 8 already in col 0 at row 3
        const conflicts = findConflicts(grid);
        expect(conflicts.length).toBeGreaterThan(0);
    });

    it('detects a box conflict', () => {
        const grid = PUZZLE_GRID.map((r) => [...r]);
        grid[0][2] = 9; // 9 already at (2,1) in box 0
        const conflicts = findConflicts(grid);
        expect(conflicts.length).toBeGreaterThan(0);
    });
});

describe('isGridComplete()', () => {
    it('returns true for the solved grid', () => {
        expect(isGridComplete(SOLVED_GRID)).toBe(true);
    });

    it('returns false for a puzzle with empty cells', () => {
        expect(isGridComplete(PUZZLE_GRID)).toBe(false);
    });

    it('returns false for an empty grid', () => {
        const empty = Array.from({ length: 9 }, () => new Array(9).fill(EMPTY_VALUE));
        expect(isGridComplete(empty)).toBe(false);
    });
});

describe('isGridCorrect()', () => {
    it('returns true when grid matches solution', () => {
        expect(isGridCorrect(SOLVED_GRID, SOLVED_GRID)).toBe(true);
    });

    it('returns false when grid has a wrong value', () => {
        const wrong = SOLVED_GRID.map((r) => [...r]);
        wrong[0][0] = 9; // Change 5 to 9
        expect(isGridCorrect(wrong, SOLVED_GRID)).toBe(false);
    });

    it('returns false for an incomplete grid', () => {
        expect(isGridCorrect(PUZZLE_GRID, SOLVED_GRID)).toBe(false);
    });
});

describe('validateCellGrid()', () => {
    it('returns no conflicts for a correct Cell grid', () => {
        const cellGrid = createCellGrid(PUZZLE_GRID, SOLVED_GRID);
        expect(validateCellGrid(cellGrid)).toHaveLength(0);
    });
});
