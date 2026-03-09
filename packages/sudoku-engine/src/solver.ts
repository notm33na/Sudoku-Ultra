import { GRID_SIZE, EMPTY_VALUE } from './constants';
import { cloneNumberGrid, getCandidateValues } from './utils';

// ─── Solver ───────────────────────────────────────────────────────────────────

/**
 * Solve a Sudoku puzzle using backtracking with constraint propagation.
 * Returns the completed grid, or null if no solution exists.
 */
export function solve(grid: number[][]): number[][] | null {
    const work = cloneNumberGrid(grid);
    if (solveRecursive(work)) {
        return work;
    }
    return null;
}

/**
 * Count the number of solutions (up to `limit`) for a puzzle.
 * Used to verify unique solvability during generation.
 */
export function countSolutions(grid: number[][], limit: number = 2): number {
    const work = cloneNumberGrid(grid);
    const counter = { count: 0 };
    countSolutionsRecursive(work, limit, counter);
    return counter.count;
}

/**
 * Check whether a puzzle has exactly one solution.
 */
export function hasUniqueSolution(grid: number[][]): boolean {
    return countSolutions(grid, 2) === 1;
}

// ─── Internal: Constraint Propagation ─────────────────────────────────────────

/**
 * Apply naked singles: if a cell has exactly one candidate, fill it.
 * Returns the number of cells filled, or -1 if a contradiction is found.
 */
function applyNakedSingles(grid: number[][]): number {
    let filled = 0;
    let changed = true;

    while (changed) {
        changed = false;
        for (let r = 0; r < GRID_SIZE; r++) {
            for (let c = 0; c < GRID_SIZE; c++) {
                if (grid[r][c] !== EMPTY_VALUE) continue;

                const candidates = getCandidateValues(grid, r, c);

                if (candidates.length === 0) {
                    // Contradiction: no valid value for this cell
                    return -1;
                }

                if (candidates.length === 1) {
                    grid[r][c] = candidates[0];
                    filled++;
                    changed = true;
                }
            }
        }
    }

    return filled;
}

/**
 * Apply hidden singles: if a value can only go in one cell within a
 * row, column, or box, fill it there.
 * Returns the number of cells filled, or -1 if a contradiction is found.
 */
function applyHiddenSingles(grid: number[][]): number {
    let filled = 0;
    let changed = true;

    while (changed) {
        changed = false;

        // Check each row
        for (let r = 0; r < GRID_SIZE; r++) {
            const result = findHiddenSinglesInUnit(grid, getRowCells(r));
            if (result === -1) return -1;
            if (result > 0) {
                filled += result;
                changed = true;
            }
        }

        // Check each column
        for (let c = 0; c < GRID_SIZE; c++) {
            const result = findHiddenSinglesInUnit(grid, getColCells(c));
            if (result === -1) return -1;
            if (result > 0) {
                filled += result;
                changed = true;
            }
        }

        // Check each box
        for (let box = 0; box < GRID_SIZE; box++) {
            const result = findHiddenSinglesInUnit(grid, getBoxCells(box));
            if (result === -1) return -1;
            if (result > 0) {
                filled += result;
                changed = true;
            }
        }
    }

    return filled;
}

function findHiddenSinglesInUnit(
    grid: number[][],
    cells: Array<[number, number]>,
): number {
    let filled = 0;

    for (let val = 1; val <= GRID_SIZE; val++) {
        // Skip if this value already exists in the unit
        const alreadyPlaced = cells.some(([r, c]) => grid[r][c] === val);
        if (alreadyPlaced) continue;

        // Find which empty cells in this unit can hold this value
        const possibleCells = cells.filter(([r, c]) => {
            if (grid[r][c] !== EMPTY_VALUE) return false;
            return getCandidateValues(grid, r, c).includes(val);
        });

        if (possibleCells.length === 0) {
            // Contradiction: value has no valid placement in this unit
            return -1;
        }

        if (possibleCells.length === 1) {
            const [r, c] = possibleCells[0];
            grid[r][c] = val;
            filled++;
        }
    }

    return filled;
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

// ─── Internal: Backtracking ───────────────────────────────────────────────────

/**
 * Find the empty cell with the fewest candidates (MRV heuristic).
 */
function findBestCell(grid: number[][]): [number, number] | null {
    let bestCount = GRID_SIZE + 1;
    let bestCell: [number, number] | null = null;

    for (let r = 0; r < GRID_SIZE; r++) {
        for (let c = 0; c < GRID_SIZE; c++) {
            if (grid[r][c] !== EMPTY_VALUE) continue;
            const count = getCandidateValues(grid, r, c).length;
            if (count < bestCount) {
                bestCount = count;
                bestCell = [r, c];
                if (count === 1) return bestCell; // Can't do better than 1
            }
        }
    }

    return bestCell;
}

function solveRecursive(grid: number[][]): boolean {
    // Apply constraint propagation first
    const snapshot = cloneNumberGrid(grid);

    const nakedResult = applyNakedSingles(grid);
    if (nakedResult === -1) {
        restoreGrid(grid, snapshot);
        return false;
    }

    const hiddenResult = applyHiddenSingles(grid);
    if (hiddenResult === -1) {
        restoreGrid(grid, snapshot);
        return false;
    }

    // Find the next empty cell using MRV heuristic
    const cell = findBestCell(grid);

    // No empty cells — puzzle is solved
    if (!cell) return true;

    const [row, col] = cell;
    const candidates = getCandidateValues(grid, row, col);

    for (const val of candidates) {
        const branchSnapshot = cloneNumberGrid(grid);
        grid[row][col] = val;

        if (solveRecursive(grid)) {
            return true;
        }

        // Backtrack
        restoreGrid(grid, branchSnapshot);
    }

    restoreGrid(grid, snapshot);
    return false;
}

function countSolutionsRecursive(
    grid: number[][],
    limit: number,
    counter: { count: number },
): void {
    if (counter.count >= limit) return;

    // Apply constraint propagation
    const snapshot = cloneNumberGrid(grid);

    const nakedResult = applyNakedSingles(grid);
    if (nakedResult === -1) {
        restoreGrid(grid, snapshot);
        return;
    }

    const hiddenResult = applyHiddenSingles(grid);
    if (hiddenResult === -1) {
        restoreGrid(grid, snapshot);
        return;
    }

    const cell = findBestCell(grid);

    if (!cell) {
        // Found a complete solution
        counter.count++;
        restoreGrid(grid, snapshot);
        return;
    }

    const [row, col] = cell;
    const candidates = getCandidateValues(grid, row, col);

    for (const val of candidates) {
        if (counter.count >= limit) break;

        const branchSnapshot = cloneNumberGrid(grid);
        grid[row][col] = val;
        countSolutionsRecursive(grid, limit, counter);
        restoreGrid(grid, branchSnapshot);
    }

    restoreGrid(grid, snapshot);
}

/**
 * Restore grid state from a snapshot (in-place).
 */
function restoreGrid(grid: number[][], snapshot: number[][]): void {
    for (let r = 0; r < GRID_SIZE; r++) {
        for (let c = 0; c < GRID_SIZE; c++) {
            grid[r][c] = snapshot[r][c];
        }
    }
}

// ─── Exported Internals (for difficulty analysis) ─────────────────────────────

/**
 * Attempt to solve a puzzle using ONLY naked singles.
 * Returns the number of cells that could be filled, or -1 on contradiction.
 */
export function solveWithNakedSinglesOnly(grid: number[][]): number {
    const work = cloneNumberGrid(grid);
    return applyNakedSingles(work);
}

/**
 * Attempt to solve a puzzle using naked + hidden singles only.
 * Returns the number of cells filled, or -1 on contradiction.
 */
export function solveWithBasicConstraints(grid: number[][]): number {
    const work = cloneNumberGrid(grid);
    let total = 0;
    let changed = true;

    while (changed) {
        changed = false;
        const naked = applyNakedSingles(work);
        if (naked === -1) return -1;
        if (naked > 0) {
            total += naked;
            changed = true;
        }
        const hidden = applyHiddenSingles(work);
        if (hidden === -1) return -1;
        if (hidden > 0) {
            total += hidden;
            changed = true;
        }
    }

    // Check if fully solved
    const emptyCells = work.flat().filter((v) => v === EMPTY_VALUE).length;
    if (emptyCells === 0) return total;

    return total; // Partially solved
}

/**
 * Check whether a puzzle can be fully solved using only naked + hidden singles.
 */
export function isSolvableWithBasicConstraints(grid: number[][]): boolean {
    const work = cloneNumberGrid(grid);
    let changed = true;

    while (changed) {
        changed = false;
        const naked = applyNakedSingles(work);
        if (naked === -1) return false;
        if (naked > 0) changed = true;
        const hidden = applyHiddenSingles(work);
        if (hidden === -1) return false;
        if (hidden > 0) changed = true;
    }

    return work.flat().every((v) => v !== EMPTY_VALUE);
}
