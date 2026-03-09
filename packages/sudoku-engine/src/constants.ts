// ─── Sudoku Engine Constants ──────────────────────────────────────────────────

/** Size of the Sudoku grid (9×9). */
export const GRID_SIZE = 9;

/** Size of a single box/block (3×3). */
export const BOX_SIZE = 3;

/** Valid cell values 1–9. */
export const VALID_VALUES: readonly number[] = [1, 2, 3, 4, 5, 6, 7, 8, 9];

/** Represents an empty cell in a number grid. */
export const EMPTY_VALUE = 0;

/** Total number of cells in the grid. */
export const TOTAL_CELLS = GRID_SIZE * GRID_SIZE; // 81

/** Number of boxes in the grid. */
export const TOTAL_BOXES = GRID_SIZE; // 9

/**
 * Clue count ranges per difficulty level.
 * These define how many pre-filled cells a generated puzzle will have.
 */
export const CLUE_RANGES: Record<string, { min: number; max: number }> = {
    beginner: { min: 46, max: 50 },
    easy: { min: 36, max: 45 },
    medium: { min: 32, max: 35 },
    hard: { min: 28, max: 31 },
    expert: { min: 24, max: 27 },
    evil: { min: 17, max: 23 },
};
