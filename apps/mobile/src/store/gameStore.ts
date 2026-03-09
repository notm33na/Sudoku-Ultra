import { create } from 'zustand';
import {
    Difficulty,
    Cell,
    Grid,
    CellStatus,
    GameAction,
    GameActionType,
} from '@sudoku-ultra/shared-types';
import {
    generatePuzzle,
    getHint,
    findConflicts,
    cellGridToNumberGrid,
    getAllCandidates,
} from '@sudoku-ultra/sudoku-engine';

// ─── Types ────────────────────────────────────────────────────────────────────

interface SelectedCell {
    row: number;
    col: number;
}

interface GameState {
    // Puzzle data
    puzzle: ReturnType<typeof generatePuzzle> | null;
    currentGrid: Grid;
    solution: number[][] | null;
    difficulty: Difficulty;

    // Selection
    selectedCell: SelectedCell | null;

    // Game state
    isPlaying: boolean;
    isPaused: boolean;
    isComplete: boolean;
    notesMode: boolean;
    timerMs: number;
    hintsUsed: number;
    errorsCount: number;
    score: number;

    // Undo/redo
    history: GameAction[];
    historyIndex: number;

    // Actions
    startGame: (difficulty: Difficulty) => void;
    selectCell: (row: number, col: number) => void;
    setValue: (value: number) => void;
    clearValue: () => void;
    toggleNotesMode: () => void;
    toggleNote: (value: number) => void;
    useHint: () => void;
    validateGrid: () => number;
    undo: () => void;
    redo: () => void;
    autoNotes: () => void;
    pause: () => void;
    resume: () => void;
    tick: (ms: number) => void;
    reset: () => void;
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function cloneGrid(grid: Grid): Grid {
    return grid.map((row) => row.map((cell) => ({ ...cell, notes: [...cell.notes] })));
}

// ─── Store ────────────────────────────────────────────────────────────────────

export const useGameStore = create<GameState>((set, get) => ({
    // Initial state
    puzzle: null,
    currentGrid: [],
    solution: null,
    difficulty: Difficulty.EASY,
    selectedCell: null,
    isPlaying: false,
    isPaused: false,
    isComplete: false,
    notesMode: false,
    timerMs: 0,
    hintsUsed: 0,
    errorsCount: 0,
    score: 0,
    history: [],
    historyIndex: -1,

    // ── Start Game ──────────────────────────────────────────────────────────
    startGame: (difficulty: Difficulty) => {
        const puzzle = generatePuzzle(difficulty);
        set({
            puzzle,
            currentGrid: cloneGrid(puzzle.grid),
            solution: puzzle.solution,
            difficulty,
            selectedCell: null,
            isPlaying: true,
            isPaused: false,
            isComplete: false,
            notesMode: false,
            timerMs: 0,
            hintsUsed: 0,
            errorsCount: 0,
            score: 0,
            history: [],
            historyIndex: -1,
        });
    },

    // ── Cell Selection ──────────────────────────────────────────────────────
    selectCell: (row: number, col: number) => {
        set({ selectedCell: { row, col } });
    },

    // ── Set Value ───────────────────────────────────────────────────────────
    setValue: (value: number) => {
        const { selectedCell, currentGrid, solution, isPlaying, isComplete } = get();
        if (!selectedCell || !isPlaying || isComplete) return;

        const { row, col } = selectedCell;
        const cell = currentGrid[row][col];
        if (cell.isLocked) return;

        // If in notes mode, toggle note instead
        if (get().notesMode) {
            get().toggleNote(value);
            return;
        }

        const newGrid = cloneGrid(currentGrid);
        const previousValue = cell.value;
        const previousNotes = [...cell.notes];

        // Check correctness
        const isCorrect = solution ? solution[row][col] === value : true;

        newGrid[row][col] = {
            ...newGrid[row][col],
            value,
            status: isCorrect ? CellStatus.FILLED : CellStatus.ERROR,
            notes: [],
        };

        // Record action for undo
        const action: GameAction = {
            type: GameActionType.SET_VALUE,
            row,
            col,
            value,
            previousValue,
            previousNotes,
            timestamp: Date.now(),
        };

        const { history, historyIndex } = get();
        const newHistory = history.slice(0, historyIndex + 1);
        newHistory.push(action);

        const errorsCount = isCorrect ? get().errorsCount : get().errorsCount + 1;

        // Check completion
        const numberGrid = cellGridToNumberGrid(newGrid);
        const allFilled = numberGrid.flat().every((v) => v !== 0);
        const noErrors = newGrid.flat().every((c) => c.status !== CellStatus.ERROR);
        const complete = allFilled && noErrors;

        set({
            currentGrid: newGrid,
            history: newHistory,
            historyIndex: newHistory.length - 1,
            errorsCount,
            isComplete: complete,
            isPlaying: !complete,
        });

        if (complete) {
            // Calculate score
            const basePoints: Record<string, number> = {
                beginner: 100, easy: 200, medium: 400, hard: 800, expert: 1500, evil: 3000,
            };
            const base = basePoints[get().difficulty] ?? 200;
            const timePenalty = Math.floor(get().timerMs / 60000);
            const hintPenalty = get().hintsUsed * 50;
            const errorPenalty = errorsCount * 25;
            set({ score: Math.max(0, base - timePenalty - hintPenalty - errorPenalty) });
        }
    },

    // ── Clear Value ─────────────────────────────────────────────────────────
    clearValue: () => {
        const { selectedCell, currentGrid, isPlaying, isComplete } = get();
        if (!selectedCell || !isPlaying || isComplete) return;

        const { row, col } = selectedCell;
        const cell = currentGrid[row][col];
        if (cell.isLocked || cell.value === null) return;

        const newGrid = cloneGrid(currentGrid);
        const previousValue = cell.value;
        const previousNotes = [...cell.notes];

        newGrid[row][col] = {
            ...newGrid[row][col],
            value: null,
            status: CellStatus.EMPTY,
        };

        const action: GameAction = {
            type: GameActionType.CLEAR_VALUE,
            row,
            col,
            value: null,
            previousValue,
            previousNotes,
            timestamp: Date.now(),
        };

        const { history, historyIndex } = get();
        const newHistory = history.slice(0, historyIndex + 1);
        newHistory.push(action);

        set({
            currentGrid: newGrid,
            history: newHistory,
            historyIndex: newHistory.length - 1,
        });
    },

    // ── Notes Mode ──────────────────────────────────────────────────────────
    toggleNotesMode: () => set((s) => ({ notesMode: !s.notesMode })),

    toggleNote: (value: number) => {
        const { selectedCell, currentGrid, isPlaying, isComplete } = get();
        if (!selectedCell || !isPlaying || isComplete) return;

        const { row, col } = selectedCell;
        const cell = currentGrid[row][col];
        if (cell.isLocked || cell.value !== null) return;

        const newGrid = cloneGrid(currentGrid);
        const currentNotes = [...cell.notes];
        const idx = currentNotes.indexOf(value);
        if (idx >= 0) {
            currentNotes.splice(idx, 1);
        } else {
            currentNotes.push(value);
            currentNotes.sort();
        }

        newGrid[row][col] = { ...newGrid[row][col], notes: currentNotes };
        set({ currentGrid: newGrid });
    },

    // ── Hint ────────────────────────────────────────────────────────────────
    useHint: () => {
        const { currentGrid, solution, isPlaying, isComplete } = get();
        if (!isPlaying || isComplete || !solution) return;

        const numberGrid = cellGridToNumberGrid(currentGrid);
        const hint = getHint(numberGrid, solution);
        if (!hint) return;

        const newGrid = cloneGrid(currentGrid);
        newGrid[hint.row][hint.col] = {
            ...newGrid[hint.row][hint.col],
            value: hint.value,
            status: CellStatus.FILLED,
            notes: [],
        };

        set({
            currentGrid: newGrid,
            hintsUsed: get().hintsUsed + 1,
            selectedCell: { row: hint.row, col: hint.col },
        });
    },

    // ── Validate ────────────────────────────────────────────────────────────
    validateGrid: (): number => {
        const { currentGrid, isPlaying, isComplete } = get();
        if (!isPlaying || isComplete) return 0;

        const numberGrid = cellGridToNumberGrid(currentGrid);
        const conflicts = findConflicts(numberGrid);

        if (conflicts.length > 0) {
            const newGrid = cloneGrid(currentGrid);
            for (const conflict of conflicts) {
                if (!newGrid[conflict.row][conflict.col].isLocked) {
                    newGrid[conflict.row][conflict.col] = { ...newGrid[conflict.row][conflict.col], status: CellStatus.ERROR };
                }
            }
            set({
                currentGrid: newGrid,
                errorsCount: get().errorsCount + conflicts.length,
            });
        }

        return conflicts.length;
    },

    // ── Undo / Redo ─────────────────────────────────────────────────────────
    undo: () => {
        const { history, historyIndex, currentGrid } = get();
        if (historyIndex < 0) return;

        const action = history[historyIndex];
        const newGrid = cloneGrid(currentGrid);

        newGrid[action.row][action.col] = {
            ...newGrid[action.row][action.col],
            value: action.previousValue,
            notes: [...action.previousNotes],
            status: action.previousValue ? CellStatus.FILLED : CellStatus.EMPTY,
        };

        set({
            currentGrid: newGrid,
            historyIndex: historyIndex - 1,
        });
    },

    redo: () => {
        const { history, historyIndex, currentGrid } = get();
        if (historyIndex >= history.length - 1) return;

        const action = history[historyIndex + 1];
        const newGrid = cloneGrid(currentGrid);

        if (action.type === GameActionType.CLEAR_VALUE) {
            newGrid[action.row][action.col] = {
                ...newGrid[action.row][action.col],
                value: null,
                status: CellStatus.EMPTY,
            };
        } else if (action.value !== null) {
            newGrid[action.row][action.col] = {
                ...newGrid[action.row][action.col],
                value: action.value,
                status: CellStatus.FILLED,
                notes: [],
            };
        }

        set({
            currentGrid: newGrid,
            historyIndex: historyIndex + 1,
        });
    },

    // ── Auto Notes ──────────────────────────────────────────────────────────
    autoNotes: () => {
        const { currentGrid, isPlaying, isComplete } = get();
        if (!isPlaying || isComplete) return;

        const numberGrid = cellGridToNumberGrid(currentGrid);
        const candidates = getAllCandidates(numberGrid);
        const newGrid = cloneGrid(currentGrid);

        for (let r = 0; r < 9; r++) {
            for (let c = 0; c < 9; c++) {
                if (newGrid[r][c].value === null) {
                    newGrid[r][c] = { ...newGrid[r][c], notes: candidates[r][c] };
                }
            }
        }

        set({ currentGrid: newGrid });
    },

    // ── Timer & Pause ──────────────────────────────────────────────────────
    pause: () => set({ isPaused: true }),
    resume: () => set({ isPaused: false }),
    tick: (ms: number) => {
        const { isPlaying, isPaused, isComplete } = get();
        if (isPlaying && !isPaused && !isComplete) {
            set((s) => ({ timerMs: s.timerMs + ms }));
        }
    },

    // ── Reset ───────────────────────────────────────────────────────────────
    reset: () => set({
        puzzle: null,
        currentGrid: [],
        solution: null,
        selectedCell: null,
        isPlaying: false,
        isPaused: false,
        isComplete: false,
        notesMode: false,
        timerMs: 0,
        hintsUsed: 0,
        errorsCount: 0,
        score: 0,
        history: [],
        historyIndex: -1,
    }),
}));
