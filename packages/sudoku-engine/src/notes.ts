import { Grid, CellStatus } from '@sudoku-ultra/shared-types';
import { GRID_SIZE, EMPTY_VALUE } from './constants';
import { getCandidateValues, cloneCellGrid } from './utils';

// ─── Notes / Candidate System ─────────────────────────────────────────────────

/**
 * Get all valid candidate values for a specific cell.
 * Candidates are values 1–9 that don't conflict with any peer.
 *
 * @param grid Number grid (0 = empty)
 * @param row Row index (0–8)
 * @param col Column index (0–8)
 */
export function getCandidates(grid: number[][], row: number, col: number): number[] {
    if (grid[row][col] !== EMPTY_VALUE) return [];
    return getCandidateValues(grid, row, col);
}

/**
 * Get candidates for ALL cells in the grid.
 * Returns a 9×9 array where each element is an array of candidate values.
 * Non-empty cells have an empty candidates array.
 */
export function getAllCandidates(grid: number[][]): number[][][] {
    const candidates: number[][][] = [];
    for (let r = 0; r < GRID_SIZE; r++) {
        const row: number[][] = [];
        for (let c = 0; c < GRID_SIZE; c++) {
            row.push(getCandidates(grid, r, c));
        }
        candidates.push(row);
    }
    return candidates;
}

/**
 * Generate auto-notes for a Cell grid.
 * Fills in the `notes` field for every empty cell with all valid candidates.
 * Returns a new grid (does not mutate the input).
 */
export function generateAutoNotes(cellGrid: Grid): Grid {
    const result = cloneCellGrid(cellGrid);

    // First, build a number grid for fast candidate computation
    const numberGrid = result.map((row) =>
        row.map((cell) => cell.value ?? EMPTY_VALUE),
    );

    for (let r = 0; r < GRID_SIZE; r++) {
        for (let c = 0; c < GRID_SIZE; c++) {
            const cell = result[r][c];
            if (cell.status === CellStatus.GIVEN || cell.value !== null) {
                cell.notes = [];
                continue;
            }
            cell.notes = getCandidateValues(numberGrid, r, c);
        }
    }

    return result;
}

/**
 * Update notes for all cells affected by placing a value.
 * Removes `value` from notes of all peers of (row, col).
 * Returns a new grid (does not mutate the input).
 */
export function updateNotesAfterPlacement(
    cellGrid: Grid,
    row: number,
    col: number,
    value: number,
): Grid {
    const result = cloneCellGrid(cellGrid);

    // Clear notes on the placed cell
    result[row][col].notes = [];

    // Remove this value from all peers' notes
    for (let c = 0; c < GRID_SIZE; c++) {
        if (c !== col) {
            result[row][c].notes = result[row][c].notes.filter((n) => n !== value);
        }
    }

    for (let r = 0; r < GRID_SIZE; r++) {
        if (r !== row) {
            result[r][col].notes = result[r][col].notes.filter((n) => n !== value);
        }
    }

    const boxRowStart = Math.floor(row / 3) * 3;
    const boxColStart = Math.floor(col / 3) * 3;
    for (let r = boxRowStart; r < boxRowStart + 3; r++) {
        for (let c = boxColStart; c < boxColStart + 3; c++) {
            if (r !== row || c !== col) {
                result[r][c].notes = result[r][c].notes.filter((n) => n !== value);
            }
        }
    }

    return result;
}

/**
 * Clear all notes from all cells.
 */
export function clearAllNotes(cellGrid: Grid): Grid {
    const result = cloneCellGrid(cellGrid);
    for (let r = 0; r < GRID_SIZE; r++) {
        for (let c = 0; c < GRID_SIZE; c++) {
            result[r][c].notes = [];
        }
    }
    return result;
}
