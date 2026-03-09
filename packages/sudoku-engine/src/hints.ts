import { Hint } from '@sudoku-ultra/shared-types';
import { GRID_SIZE, EMPTY_VALUE } from './constants';
import { getCandidateValues } from './utils';

// ─── Hint System ──────────────────────────────────────────────────────────────

/**
 * Get a hint for the next logical cell to fill.
 *
 * Strategy (in order of preference):
 * 1. Naked single — a cell with exactly one candidate
 * 2. Hidden single — a value that can only go in one place in a row/col/box
 * 3. Fallback — the cell with the fewest candidates (from the solution)
 *
 * @param grid Current puzzle state (number[][])
 * @param solution The known solution
 * @returns A Hint with row, col, value, technique name, and explanation
 */
export function getHint(grid: number[][], solution: number[][]): Hint | null {
    // Strategy 1: Find a naked single
    const nakedSingle = findNakedSingle(grid);
    if (nakedSingle) return nakedSingle;

    // Strategy 2: Find a hidden single
    const hiddenSingle = findHiddenSingle(grid);
    if (hiddenSingle) return hiddenSingle;

    // Strategy 3: Fallback — find the easiest empty cell from solution
    return findEasiestCell(grid, solution);
}

// ─── Internal: Naked Single ───────────────────────────────────────────────────

function findNakedSingle(grid: number[][]): Hint | null {
    for (let r = 0; r < GRID_SIZE; r++) {
        for (let c = 0; c < GRID_SIZE; c++) {
            if (grid[r][c] !== EMPTY_VALUE) continue;

            const candidates = getCandidateValues(grid, r, c);
            if (candidates.length === 1) {
                return {
                    row: r,
                    col: c,
                    value: candidates[0],
                    technique: 'Naked Single',
                    explanation: `Cell R${r + 1}C${c + 1} has only one possible value: ${candidates[0]}. All other values are eliminated by the row, column, and box constraints.`,
                };
            }
        }
    }
    return null;
}

// ─── Internal: Hidden Single ──────────────────────────────────────────────────

function findHiddenSingle(grid: number[][]): Hint | null {
    // Check rows
    for (let r = 0; r < GRID_SIZE; r++) {
        const hint = findHiddenSingleInUnit(grid, getRowCells(r), 'row', r + 1);
        if (hint) return hint;
    }

    // Check columns
    for (let c = 0; c < GRID_SIZE; c++) {
        const hint = findHiddenSingleInUnit(grid, getColCells(c), 'column', c + 1);
        if (hint) return hint;
    }

    // Check boxes
    for (let box = 0; box < GRID_SIZE; box++) {
        const hint = findHiddenSingleInUnit(grid, getBoxCells(box), 'box', box + 1);
        if (hint) return hint;
    }

    return null;
}

function findHiddenSingleInUnit(
    grid: number[][],
    cells: Array<[number, number]>,
    unitType: string,
    unitIndex: number,
): Hint | null {
    for (let val = 1; val <= GRID_SIZE; val++) {
        // Skip if value already placed in this unit
        if (cells.some(([r, c]) => grid[r][c] === val)) continue;

        // Find cells where this value can go
        const possibleCells = cells.filter(([r, c]) => {
            if (grid[r][c] !== EMPTY_VALUE) return false;
            return getCandidateValues(grid, r, c).includes(val);
        });

        if (possibleCells.length === 1) {
            const [r, c] = possibleCells[0];
            return {
                row: r,
                col: c,
                value: val,
                technique: 'Hidden Single',
                explanation: `In ${unitType} ${unitIndex}, the value ${val} can only go in cell R${r + 1}C${c + 1}. No other cell in this ${unitType} can hold this value.`,
            };
        }
    }

    return null;
}

// ─── Internal: Easiest Cell Fallback ──────────────────────────────────────────

function findEasiestCell(grid: number[][], solution: number[][]): Hint | null {
    let bestCount = GRID_SIZE + 1;
    let bestRow = -1;
    let bestCol = -1;

    for (let r = 0; r < GRID_SIZE; r++) {
        for (let c = 0; c < GRID_SIZE; c++) {
            if (grid[r][c] !== EMPTY_VALUE) continue;

            const count = getCandidateValues(grid, r, c).length;
            if (count > 0 && count < bestCount) {
                bestCount = count;
                bestRow = r;
                bestCol = c;
            }
        }
    }

    if (bestRow === -1) return null;

    return {
        row: bestRow,
        col: bestCol,
        value: solution[bestRow][bestCol],
        technique: 'Elimination',
        explanation: `Cell R${bestRow + 1}C${bestCol + 1} has ${bestCount} possible values. The correct value is ${solution[bestRow][bestCol]}.`,
    };
}

// ─── Internal: Unit Cell Coordinates ──────────────────────────────────────────

function getRowCells(row: number): Array<[number, number]> {
    return Array.from({ length: GRID_SIZE }, (_, c) => [row, c] as [number, number]);
}

function getColCells(col: number): Array<[number, number]> {
    return Array.from({ length: GRID_SIZE }, (_, r) => [r, col] as [number, number]);
}

function getBoxCells(box: number): Array<[number, number]> {
    const boxRow = Math.floor(box / 3) * 3;
    const boxCol = (box % 3) * 3;
    const cells: Array<[number, number]> = [];
    for (let r = boxRow; r < boxRow + 3; r++) {
        for (let c = boxCol; c < boxCol + 3; c++) {
            cells.push([r, c]);
        }
    }
    return cells;
}
