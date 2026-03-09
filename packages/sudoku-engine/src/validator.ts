import { Grid } from '@sudoku-ultra/shared-types';
import { GRID_SIZE, BOX_SIZE, EMPTY_VALUE } from './constants';

// ─── Validator ────────────────────────────────────────────────────────────────

/**
 * Check whether placing `value` at (row, col) is valid in the number grid.
 * A placement is valid if the value doesn't already appear in the same
 * row, column, or 3×3 box (excluding the cell itself).
 */
export function validatePlacement(
    grid: number[][],
    row: number,
    col: number,
    value: number,
): boolean {
    // Check row
    for (let c = 0; c < GRID_SIZE; c++) {
        if (c !== col && grid[row][c] === value) return false;
    }

    // Check column
    for (let r = 0; r < GRID_SIZE; r++) {
        if (r !== row && grid[r][col] === value) return false;
    }

    // Check box
    const boxRowStart = Math.floor(row / BOX_SIZE) * BOX_SIZE;
    const boxColStart = Math.floor(col / BOX_SIZE) * BOX_SIZE;
    for (let r = boxRowStart; r < boxRowStart + BOX_SIZE; r++) {
        for (let c = boxColStart; c < boxColStart + BOX_SIZE; c++) {
            if (r !== row && c !== col && grid[r][c] === value) return false;
        }
    }

    return true;
}

/**
 * Find all cells with conflicts (duplicate values in row, col, or box).
 * Returns an array of {row, col} positions that have errors.
 */
export function findConflicts(grid: number[][]): Array<{ row: number; col: number }> {
    const conflicts = new Set<string>();

    for (let r = 0; r < GRID_SIZE; r++) {
        for (let c = 0; c < GRID_SIZE; c++) {
            const val = grid[r][c];
            if (val === EMPTY_VALUE) continue;

            if (!validatePlacement(grid, r, c, val)) {
                conflicts.add(`${r},${c}`);
            }
        }
    }

    return Array.from(conflicts).map((key) => {
        const [row, col] = key.split(',').map(Number);
        return { row, col };
    });
}

/**
 * Check if the grid is fully filled (no empty cells).
 */
export function isGridComplete(grid: number[][]): boolean {
    for (let r = 0; r < GRID_SIZE; r++) {
        for (let c = 0; c < GRID_SIZE; c++) {
            if (grid[r][c] === EMPTY_VALUE) return false;
        }
    }
    return true;
}

/**
 * Check if the grid matches the solution exactly.
 */
export function isGridCorrect(grid: number[][], solution: number[][]): boolean {
    for (let r = 0; r < GRID_SIZE; r++) {
        for (let c = 0; c < GRID_SIZE; c++) {
            if (grid[r][c] !== solution[r][c]) return false;
        }
    }
    return true;
}

/**
 * Validate a Cell[][] grid by converting to number grid and checking.
 */
export function validateCellGrid(cellGrid: Grid): Array<{ row: number; col: number }> {
    const numberGrid = cellGridToNumbers(cellGrid);
    return findConflicts(numberGrid);
}

/**
 * Check if a Cell[][] grid is fully complete and correct against solution.
 */
export function isCellGridCorrect(cellGrid: Grid, solution: number[][]): boolean {
    const numberGrid = cellGridToNumbers(cellGrid);
    return isGridCorrect(numberGrid, solution);
}

// ─── Internal ─────────────────────────────────────────────────────────────────

function cellGridToNumbers(grid: Grid): number[][] {
    return grid.map((row) => row.map((cell) => cell.value ?? EMPTY_VALUE));
}
