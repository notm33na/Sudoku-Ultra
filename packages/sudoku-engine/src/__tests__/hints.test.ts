import { getHint } from '../hints';

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

// Puzzle with one empty cell → must produce a naked single hint
const ONE_EMPTY_PUZZLE: number[][] = SOLVED_GRID.map((row, r) =>
    row.map((val, c) => (r === 8 && c === 8 ? 0 : val)),
);

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

describe('getHint()', () => {
    it('returns null when the puzzle is already solved', () => {
        expect(getHint(SOLVED_GRID, SOLVED_GRID)).toBeNull();
    });

    it('returns a hint for a puzzle with one empty cell', () => {
        const hint = getHint(ONE_EMPTY_PUZZLE, SOLVED_GRID);
        expect(hint).not.toBeNull();
        expect(hint!.row).toBe(8);
        expect(hint!.col).toBe(8);
        expect(hint!.value).toBe(9);
    });

    it('hint value matches the solution', () => {
        const hint = getHint(EASY_PUZZLE, SOLVED_GRID);
        expect(hint).not.toBeNull();
        expect(hint!.value).toBe(SOLVED_GRID[hint!.row][hint!.col]);
    });

    it('hint technique is a non-empty string', () => {
        const hint = getHint(EASY_PUZZLE, SOLVED_GRID);
        expect(hint).not.toBeNull();
        expect(typeof hint!.technique).toBe('string');
        expect(hint!.technique.length).toBeGreaterThan(0);
    });

    it('hint explanation is a non-empty string', () => {
        const hint = getHint(EASY_PUZZLE, SOLVED_GRID);
        expect(hint).not.toBeNull();
        expect(typeof hint!.explanation).toBe('string');
        expect(hint!.explanation.length).toBeGreaterThan(0);
    });

    it('hint row and col are within grid bounds', () => {
        const hint = getHint(EASY_PUZZLE, SOLVED_GRID);
        expect(hint).not.toBeNull();
        expect(hint!.row).toBeGreaterThanOrEqual(0);
        expect(hint!.row).toBeLessThan(9);
        expect(hint!.col).toBeGreaterThanOrEqual(0);
        expect(hint!.col).toBeLessThan(9);
    });

    it('hint points to an empty cell', () => {
        const hint = getHint(EASY_PUZZLE, SOLVED_GRID);
        expect(hint).not.toBeNull();
        expect(EASY_PUZZLE[hint!.row][hint!.col]).toBe(0);
    });

    it('naked single technique is returned for one-empty-cell puzzle', () => {
        const hint = getHint(ONE_EMPTY_PUZZLE, SOLVED_GRID);
        expect(hint!.technique).toBe('Naked Single');
    });
});
