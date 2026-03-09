import { GameAction, GameActionType } from '@sudoku-ultra/shared-types';

// ─── Game History (Undo/Redo) ─────────────────────────────────────────────────

/**
 * Immutable event log that tracks all game actions for undo/redo support.
 *
 * Design:
 * - Actions are stored in an append-only log
 * - A cursor separates "done" actions from "undone" actions
 * - New actions clear the redo stack (standard undo/redo behavior)
 * - All operations return a new GameHistory instance (immutable)
 */
export class GameHistory {
    private readonly actions: readonly GameAction[];
    private readonly cursor: number; // Points to the next slot (= number of active actions)

    constructor(actions: readonly GameAction[] = [], cursor?: number) {
        this.actions = actions;
        this.cursor = cursor ?? actions.length;
    }

    /**
     * Push a new action onto the history.
     * Clears any redo stack (actions after cursor are discarded).
     */
    push(action: GameAction): GameHistory {
        const kept = this.actions.slice(0, this.cursor);
        return new GameHistory([...kept, action], this.cursor + 1);
    }

    /**
     * Undo the last action.
     * Returns [newHistory, undoneAction] or [this, null] if nothing to undo.
     */
    undo(): [GameHistory, GameAction | null] {
        if (!this.canUndo) return [this, null];
        const undoneAction = this.actions[this.cursor - 1];
        return [new GameHistory(this.actions, this.cursor - 1), undoneAction];
    }

    /**
     * Redo the last undone action.
     * Returns [newHistory, redoneAction] or [this, null] if nothing to redo.
     */
    redo(): [GameHistory, GameAction | null] {
        if (!this.canRedo) return [this, null];
        const redoneAction = this.actions[this.cursor];
        return [new GameHistory(this.actions, this.cursor + 1), redoneAction];
    }

    /** Whether there are actions to undo. */
    get canUndo(): boolean {
        return this.cursor > 0;
    }

    /** Whether there are actions to redo. */
    get canRedo(): boolean {
        return this.cursor < this.actions.length;
    }

    /** Number of active (non-undone) actions. */
    get size(): number {
        return this.cursor;
    }

    /** Total actions including undone ones still in the redo stack. */
    get totalSize(): number {
        return this.actions.length;
    }

    /** Get the active action log (everything before the cursor). */
    getLog(): readonly GameAction[] {
        return this.actions.slice(0, this.cursor);
    }

    /** Get the full action log including redo stack. */
    getFullLog(): readonly GameAction[] {
        return this.actions;
    }

    /** Get the last action (the one that would be undone). */
    getLastAction(): GameAction | null {
        if (this.cursor === 0) return null;
        return this.actions[this.cursor - 1];
    }

    /** Clear all history. */
    clear(): GameHistory {
        return new GameHistory([], 0);
    }
}

// ─── Action Factory Helpers ───────────────────────────────────────────────────

/**
 * Create a SET_VALUE action.
 */
export function createSetValueAction(
    row: number,
    col: number,
    value: number,
    previousValue: number | null,
    previousNotes: number[] = [],
): GameAction {
    return {
        type: GameActionType.SET_VALUE,
        row,
        col,
        value,
        previousValue,
        previousNotes: [...previousNotes],
        timestamp: Date.now(),
    };
}

/**
 * Create a CLEAR_VALUE action.
 */
export function createClearValueAction(
    row: number,
    col: number,
    previousValue: number,
    previousNotes: number[] = [],
): GameAction {
    return {
        type: GameActionType.CLEAR_VALUE,
        row,
        col,
        value: null,
        previousValue,
        previousNotes: [...previousNotes],
        timestamp: Date.now(),
    };
}

/**
 * Create a TOGGLE_NOTE action.
 */
export function createToggleNoteAction(
    row: number,
    col: number,
    noteValue: number,
    previousNotes: number[],
): GameAction {
    return {
        type: GameActionType.TOGGLE_NOTE,
        row,
        col,
        value: noteValue,
        previousValue: null,
        previousNotes: [...previousNotes],
        timestamp: Date.now(),
    };
}

/**
 * Create a USE_HINT action.
 */
export function createUseHintAction(
    row: number,
    col: number,
    value: number,
    previousValue: number | null,
    previousNotes: number[] = [],
): GameAction {
    return {
        type: GameActionType.USE_HINT,
        row,
        col,
        value,
        previousValue,
        previousNotes: [...previousNotes],
        timestamp: Date.now(),
    };
}

/**
 * Create an AUTO_NOTES action.
 * Uses row=-1, col=-1 to indicate a grid-wide action.
 */
export function createAutoNotesAction(): GameAction {
    return {
        type: GameActionType.AUTO_NOTES,
        row: -1,
        col: -1,
        value: null,
        previousValue: null,
        previousNotes: [],
        timestamp: Date.now(),
    };
}
