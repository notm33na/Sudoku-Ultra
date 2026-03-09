/**
 * @sudoku-ultra/sudoku-engine
 *
 * Complete Sudoku puzzle engine providing:
 * - Puzzle generation (backtracking + constraint propagation)
 * - Puzzle solver
 * - Difficulty classification (rule-based)
 * - Validation logic
 * - Hint computation (technique-aware)
 * - Note/candidate computation
 * - Undo/redo state history (immutable event log)
 * - Auto-notes generation
 */

export const ENGINE_VERSION = '0.1.0';

// ─── Constants ────────────────────────────────────────────────────────────────
export { GRID_SIZE, BOX_SIZE, VALID_VALUES, EMPTY_VALUE, TOTAL_CELLS, CLUE_RANGES } from './constants';

// ─── Utilities ────────────────────────────────────────────────────────────────
export {
    createEmptyNumberGrid,
    cloneNumberGrid,
    createCellGrid,
    cloneCellGrid,
    cellGridToNumberGrid,
    getRowValues,
    getColValues,
    getBoxValues,
    getBoxIndex,
    getPeerValues,
    getCandidateValues,
    shuffleArray,
    countClues,
} from './utils';

// ─── Solver ───────────────────────────────────────────────────────────────────
export {
    solve,
    countSolutions,
    hasUniqueSolution,
    solveWithNakedSinglesOnly,
    solveWithBasicConstraints,
    isSolvableWithBasicConstraints,
} from './solver';

// ─── Generator ────────────────────────────────────────────────────────────────
export { generatePuzzle } from './generator';

// ─── Validator ────────────────────────────────────────────────────────────────
export {
    validatePlacement,
    findConflicts,
    isGridComplete,
    isGridCorrect,
    validateCellGrid,
    isCellGridCorrect,
} from './validator';

// ─── Difficulty ───────────────────────────────────────────────────────────────
export { classifyDifficulty, getDifficulty } from './difficulty';
export type { DifficultyAnalysis } from './difficulty';

// ─── Hints ────────────────────────────────────────────────────────────────────
export { getHint } from './hints';

// ─── Notes ────────────────────────────────────────────────────────────────────
export {
    getCandidates,
    getAllCandidates,
    generateAutoNotes,
    updateNotesAfterPlacement,
    clearAllNotes,
} from './notes';

// ─── History ──────────────────────────────────────────────────────────────────
export {
    GameHistory,
    createSetValueAction,
    createClearValueAction,
    createToggleNoteAction,
    createUseHintAction,
    createAutoNotesAction,
} from './history';
