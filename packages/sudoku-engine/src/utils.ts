import { Cell, CellStatus, Grid } from '@sudoku-ultra/shared-types';
import { GRID_SIZE, BOX_SIZE, EMPTY_VALUE } from './constants';

// ─── Number Grid Helpers ──────────────────────────────────────────────────────

/**
 * Create a 9×9 grid initialized to zeros (EMPTY_VALUE).
 */
export function createEmptyNumberGrid(): number[][] {
    return Array.from({ length: GRID_SIZE }, () => new Array<number>(GRID_SIZE).fill(EMPTY_VALUE));
}

/**
 * Deep-clone a 9×9 number grid.
 */
export function cloneNumberGrid(grid: number[][]): number[][] {
    return grid.map((row) => [...row]);
}

// ─── Cell Grid Helpers ────────────────────────────────────────────────────────

/**
 * Convert a flat number grid into a Cell[][] grid.
 * Non-zero values are marked as GIVEN + locked; zeros are EMPTY.
 */
export function createCellGrid(numberGrid: number[][], solution: number[][]): Grid {
    const cellGrid: Grid = [];
    for (let r = 0; r < GRID_SIZE; r++) {
        const row: Cell[] = [];
        for (let c = 0; c < GRID_SIZE; c++) {
            const value = numberGrid[r][c];
            const isGiven = value !== EMPTY_VALUE;
            row.push({
                row: r,
                col: c,
                value: isGiven ? value : null,
                status: isGiven ? CellStatus.GIVEN : CellStatus.EMPTY,
                notes: [],
                isLocked: isGiven,
            });
        }
        cellGrid.push(row);
    }
    return cellGrid;
}

/**
 * Deep-clone a Cell[][] grid.
 */
export function cloneCellGrid(grid: Grid): Grid {
    return grid.map((row) =>
        row.map((cell) => ({
            ...cell,
            notes: [...cell.notes],
        })),
    );
}

/**
 * Convert a Cell[][] grid back to a number[][] grid.
 * null values become EMPTY_VALUE (0).
 */
export function cellGridToNumberGrid(grid: Grid): number[][] {
    return grid.map((row) => row.map((cell) => cell.value ?? EMPTY_VALUE));
}

// ─── Row / Column / Box Accessors ─────────────────────────────────────────────

/**
 * Get all non-zero values in a given row.
 */
export function getRowValues(grid: number[][], row: number): number[] {
    return grid[row].filter((v) => v !== EMPTY_VALUE);
}

/**
 * Get all non-zero values in a given column.
 */
export function getColValues(grid: number[][], col: number): number[] {
    const values: number[] = [];
    for (let r = 0; r < GRID_SIZE; r++) {
        if (grid[r][col] !== EMPTY_VALUE) {
            values.push(grid[r][col]);
        }
    }
    return values;
}

/**
 * Get all non-zero values in the 3×3 box containing (row, col).
 */
export function getBoxValues(grid: number[][], row: number, col: number): number[] {
    const values: number[] = [];
    const boxRowStart = Math.floor(row / BOX_SIZE) * BOX_SIZE;
    const boxColStart = Math.floor(col / BOX_SIZE) * BOX_SIZE;
    for (let r = boxRowStart; r < boxRowStart + BOX_SIZE; r++) {
        for (let c = boxColStart; c < boxColStart + BOX_SIZE; c++) {
            if (grid[r][c] !== EMPTY_VALUE) {
                values.push(grid[r][c]);
            }
        }
    }
    return values;
}

/**
 * Get a unique box index (0–8) for a cell at (row, col).
 */
export function getBoxIndex(row: number, col: number): number {
    return Math.floor(row / BOX_SIZE) * BOX_SIZE + Math.floor(col / BOX_SIZE);
}

/**
 * Get all values that are already used by peers of (row, col).
 * Peers = same row, same column, same box.
 */
export function getPeerValues(grid: number[][], row: number, col: number): Set<number> {
    const peers = new Set<number>();
    // Row
    for (let c = 0; c < GRID_SIZE; c++) {
        if (grid[row][c] !== EMPTY_VALUE) peers.add(grid[row][c]);
    }
    // Column
    for (let r = 0; r < GRID_SIZE; r++) {
        if (grid[r][col] !== EMPTY_VALUE) peers.add(grid[r][col]);
    }
    // Box
    const boxRowStart = Math.floor(row / BOX_SIZE) * BOX_SIZE;
    const boxColStart = Math.floor(col / BOX_SIZE) * BOX_SIZE;
    for (let r = boxRowStart; r < boxRowStart + BOX_SIZE; r++) {
        for (let c = boxColStart; c < boxColStart + BOX_SIZE; c++) {
            if (grid[r][c] !== EMPTY_VALUE) peers.add(grid[r][c]);
        }
    }
    return peers;
}

/**
 * Get all values that are valid candidates for (row, col).
 */
export function getCandidateValues(grid: number[][], row: number, col: number): number[] {
    const peers = getPeerValues(grid, row, col);
    return [1, 2, 3, 4, 5, 6, 7, 8, 9].filter((v) => !peers.has(v));
}

/**
 * Shuffle an array in-place using Fisher-Yates algorithm.
 */
export function shuffleArray<T>(arr: T[]): T[] {
    for (let i = arr.length - 1; i > 0; i--) {
        const j = Math.floor(Math.random() * (i + 1));
        [arr[i], arr[j]] = [arr[j], arr[i]];
    }
    return arr;
}

/**
 * Count how many non-zero (given/filled) cells exist in a number grid.
 */
export function countClues(grid: number[][]): number {
    let count = 0;
    for (let r = 0; r < GRID_SIZE; r++) {
        for (let c = 0; c < GRID_SIZE; c++) {
            if (grid[r][c] !== EMPTY_VALUE) count++;
        }
    }
    return count;
}
