import { getCandidates, getAllCandidates, generateAutoNotes, updateNotesAfterPlacement, clearAllNotes } from '../notes';
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

const PUZZLE: number[][] = [
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

describe('getCandidates()', () => {
    it('returns empty array for a filled cell', () => {
        expect(getCandidates(PUZZLE, 0, 0)).toEqual([]); // Cell has value 5
    });

    it('returns values that do not conflict with row, col, or box', () => {
        const candidates = getCandidates(PUZZLE, 0, 2); // Row 0, col 2 is empty
        // Solution value is 4 — it must be a candidate
        expect(candidates).toContain(4);
        // 5 is in the same row — not a candidate
        expect(candidates).not.toContain(5);
        // 3 is in the same row — not a candidate
        expect(candidates).not.toContain(3);
        // 7 is in the same row — not a candidate
        expect(candidates).not.toContain(7);
    });

    it('returns only values 1–9', () => {
        const candidates = getCandidates(PUZZLE, 0, 2);
        candidates.forEach((v) => {
            expect(v).toBeGreaterThanOrEqual(1);
            expect(v).toBeLessThanOrEqual(9);
        });
    });
});

describe('getAllCandidates()', () => {
    it('returns a 9×9 array', () => {
        const all = getAllCandidates(PUZZLE);
        expect(all).toHaveLength(9);
        all.forEach((row) => expect(row).toHaveLength(9));
    });

    it('filled cells have empty candidate arrays', () => {
        const all = getAllCandidates(PUZZLE);
        expect(all[0][0]).toEqual([]); // Cell (0,0) = 5
        expect(all[0][1]).toEqual([]); // Cell (0,1) = 3
    });

    it('empty cells have non-empty candidate arrays', () => {
        const all = getAllCandidates(PUZZLE);
        expect(all[0][2].length).toBeGreaterThan(0); // Cell (0,2) is empty
    });
});

describe('generateAutoNotes()', () => {
    it('fills notes for all empty cells', () => {
        const cellGrid = createCellGrid(PUZZLE, SOLVED_GRID);
        const noted = generateAutoNotes(cellGrid);
        for (let r = 0; r < 9; r++) {
            for (let c = 0; c < 9; c++) {
                if (PUZZLE[r][c] === EMPTY_VALUE) {
                    expect(noted[r][c].notes.length).toBeGreaterThan(0);
                }
            }
        }
    });

    it('does not set notes on given cells', () => {
        const cellGrid = createCellGrid(PUZZLE, SOLVED_GRID);
        const noted = generateAutoNotes(cellGrid);
        expect(noted[0][0].notes).toEqual([]); // Given cell (0,0)=5
    });

    it('does not mutate the original cell grid', () => {
        const cellGrid = createCellGrid(PUZZLE, SOLVED_GRID);
        const original = JSON.stringify(cellGrid);
        generateAutoNotes(cellGrid);
        expect(JSON.stringify(cellGrid)).toBe(original);
    });

    it('all notes are valid candidates (no conflicts)', () => {
        const cellGrid = createCellGrid(PUZZLE, SOLVED_GRID);
        const noted = generateAutoNotes(cellGrid);
        for (let r = 0; r < 9; r++) {
            for (let c = 0; c < 9; c++) {
                const valid = getCandidates(PUZZLE, r, c);
                noted[r][c].notes.forEach((note) => {
                    expect(valid).toContain(note);
                });
            }
        }
    });
});

describe('updateNotesAfterPlacement()', () => {
    it('removes placed value from notes of peers', () => {
        const cellGrid = createCellGrid(PUZZLE, SOLVED_GRID);
        const noted = generateAutoNotes(cellGrid);
        const updated = updateNotesAfterPlacement(noted, 0, 2, 4);
        // All cells in row 0 should not have 4 in notes
        for (let c = 0; c < 9; c++) {
            expect(updated[0][c].notes).not.toContain(4);
        }
        // All cells in col 2 should not have 4 in notes
        for (let r = 0; r < 9; r++) {
            expect(updated[r][2].notes).not.toContain(4);
        }
    });

    it('clears notes on the placed cell', () => {
        const cellGrid = createCellGrid(PUZZLE, SOLVED_GRID);
        const noted = generateAutoNotes(cellGrid);
        const updated = updateNotesAfterPlacement(noted, 0, 2, 4);
        expect(updated[0][2].notes).toEqual([]);
    });

    it('does not mutate the original grid', () => {
        const cellGrid = createCellGrid(PUZZLE, SOLVED_GRID);
        const noted = generateAutoNotes(cellGrid);
        const original = JSON.stringify(noted);
        updateNotesAfterPlacement(noted, 0, 2, 4);
        expect(JSON.stringify(noted)).toBe(original);
    });
});

describe('clearAllNotes()', () => {
    it('clears all notes from a noted grid', () => {
        const cellGrid = createCellGrid(PUZZLE, SOLVED_GRID);
        const noted = generateAutoNotes(cellGrid);
        const cleared = clearAllNotes(noted);
        cleared.flat().forEach((cell) => {
            expect(cell.notes).toEqual([]);
        });
    });

    it('does not mutate the original grid', () => {
        const cellGrid = createCellGrid(PUZZLE, SOLVED_GRID);
        const noted = generateAutoNotes(cellGrid);
        const original = JSON.stringify(noted);
        clearAllNotes(noted);
        expect(JSON.stringify(noted)).toBe(original);
    });
});
