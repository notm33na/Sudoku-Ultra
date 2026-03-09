import { Difficulty, Puzzle } from '@sudoku-ultra/shared-types';
import { GRID_SIZE, EMPTY_VALUE, CLUE_RANGES, TOTAL_CELLS } from './constants';
import {
    createEmptyNumberGrid,
    cloneNumberGrid,
    shuffleArray,
    getCandidateValues,
    countClues,
    createCellGrid,
} from './utils';
import { hasUniqueSolution } from './solver';

// ─── Generator ────────────────────────────────────────────────────────────────

/**
 * Generate a complete Sudoku puzzle with the given difficulty.
 *
 * Algorithm:
 * 1. Fill a complete valid 9×9 grid using randomized backtracking
 * 2. Pass 1 — symmetrically remove cells (180° rotational symmetry)
 * 3. Pass 2 — individual cell removal if symmetric pass didn't reach target
 * 4. After each removal, verify unique solvability
 * 5. Stop when the target clue count is reached
 */
export function generatePuzzle(difficulty: Difficulty): Puzzle {
    const solution = generateFullGrid();

    const clueRange = CLUE_RANGES[difficulty];
    const targetClues = randomInRange(clueRange.min, clueRange.max);
    const puzzleGrid = removeCells(solution, targetClues);

    const clueCount = countClues(puzzleGrid);
    const cellGrid = createCellGrid(puzzleGrid, solution);

    return {
        id: generateId(),
        grid: cellGrid,
        solution,
        difficulty,
        clueCount,
        createdAt: new Date().toISOString(),
    };
}

// ─── Internal: Full Grid Generation ───────────────────────────────────────────

function generateFullGrid(): number[][] {
    const grid = createEmptyNumberGrid();
    fillGrid(grid);
    return grid;
}

function fillGrid(grid: number[][]): boolean {
    for (let r = 0; r < GRID_SIZE; r++) {
        for (let c = 0; c < GRID_SIZE; c++) {
            if (grid[r][c] !== EMPTY_VALUE) continue;

            const candidates = shuffleArray([...getCandidateValues(grid, r, c)]);

            for (const val of candidates) {
                grid[r][c] = val;
                if (fillGrid(grid)) return true;
                grid[r][c] = EMPTY_VALUE;
            }

            return false;
        }
    }
    return true;
}

// ─── Internal: Cell Removal ───────────────────────────────────────────────────

/**
 * Remove cells from a solved grid to create a puzzle.
 *
 * Pass 1: Symmetric removal (180° rotational symmetry).
 * Pass 2: Individual cell removal when symmetric pass is exhausted.
 *
 * Both passes verify unique solvability after each removal.
 */
function removeCells(solution: number[][], targetClues: number): number[][] {
    const puzzle = cloneNumberGrid(solution);
    let currentClues = TOTAL_CELLS;

    // ── Pass 1: Symmetric pairs ─────────────────────────────────────────────────
    const symPositions: Array<[number, number]> = [];
    for (let r = 0; r < GRID_SIZE; r++) {
        for (let c = 0; c < GRID_SIZE; c++) {
            if (r < GRID_SIZE - 1 - r || (r === GRID_SIZE - 1 - r && c <= GRID_SIZE - 1 - c)) {
                symPositions.push([r, c]);
            }
        }
    }
    shuffleArray(symPositions);

    for (const [r, c] of symPositions) {
        if (currentClues <= targetClues) break;

        const symR = GRID_SIZE - 1 - r;
        const symC = GRID_SIZE - 1 - c;
        const isCenterCell = r === symR && c === symC;

        const val1 = puzzle[r][c];
        const val2 = isCenterCell ? 0 : puzzle[symR][symC];

        if (val1 === EMPTY_VALUE) continue;

        puzzle[r][c] = EMPTY_VALUE;
        const removedCount = isCenterCell ? 1 : 2;
        if (!isCenterCell) puzzle[symR][symC] = EMPTY_VALUE;

        if (hasUniqueSolution(puzzle)) {
            currentClues -= removedCount;
        } else {
            // Restore — removal broke uniqueness
            puzzle[r][c] = val1;
            if (!isCenterCell) puzzle[symR][symC] = val2;
        }
    }

    // ── Pass 2: Individual cells ────────────────────────────────────────────────
    // For hard/evil difficulties the symmetric pass often can't reach the target.
    // Fall back to removing individual cells in random order.
    if (currentClues > targetClues) {
        const singlePositions: Array<[number, number]> = [];
        for (let r = 0; r < GRID_SIZE; r++) {
            for (let c = 0; c < GRID_SIZE; c++) {
                if (puzzle[r][c] !== EMPTY_VALUE) singlePositions.push([r, c]);
            }
        }
        shuffleArray(singlePositions);

        for (const [r, c] of singlePositions) {
            if (currentClues <= targetClues) break;
            if (puzzle[r][c] === EMPTY_VALUE) continue;

            const savedVal = puzzle[r][c];
            puzzle[r][c] = EMPTY_VALUE;

            if (hasUniqueSolution(puzzle)) {
                currentClues--;
            } else {
                puzzle[r][c] = savedVal;
            }
        }
    }

    return puzzle;
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function randomInRange(min: number, max: number): number {
    return Math.floor(Math.random() * (max - min + 1)) + min;
}

let idCounter = 0;

function generateId(): string {
    const timestamp = Date.now().toString(36);
    const random = Math.random().toString(36).substring(2, 8);
    const counter = (idCounter++).toString(36);
    return `pzl_${timestamp}_${random}_${counter}`;
}
