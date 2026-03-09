import { GameActionType } from '@sudoku-ultra/shared-types';
import {
    GameHistory,
    createSetValueAction,
    createClearValueAction,
    createToggleNoteAction,
    createUseHintAction,
    createAutoNotesAction,
} from '../history';

// ─── Factory Helpers ──────────────────────────────────────────────────────────

function makeAction(row = 0, col = 0, value = 5, prev = null as number | null) {
    return createSetValueAction(row, col, value, prev);
}

// ─── GameHistory ──────────────────────────────────────────────────────────────

describe('GameHistory — initial state', () => {
    it('starts empty', () => {
        const h = new GameHistory();
        expect(h.size).toBe(0);
        expect(h.canUndo).toBe(false);
        expect(h.canRedo).toBe(false);
        expect(h.getLog()).toHaveLength(0);
    });

    it('getLastAction returns null when empty', () => {
        expect(new GameHistory().getLastAction()).toBeNull();
    });
});

describe('GameHistory — push()', () => {
    it('increments size after push', () => {
        const h = new GameHistory().push(makeAction());
        expect(h.size).toBe(1);
    });

    it('enables undo after one push', () => {
        const h = new GameHistory().push(makeAction());
        expect(h.canUndo).toBe(true);
    });

    it('does not mutate the original history', () => {
        const original = new GameHistory();
        original.push(makeAction());
        expect(original.size).toBe(0);
    });

    it('clears the redo stack on new push', () => {
        let h = new GameHistory();
        h = h.push(makeAction(0, 0, 5, null));
        const [afterUndo] = h.undo();
        expect(afterUndo.canRedo).toBe(true);

        const afterPush = afterUndo.push(makeAction(0, 0, 7, null));
        expect(afterPush.canRedo).toBe(false);
    });

    it('returns the pushed action at getLastAction', () => {
        const action = makeAction(3, 4, 7, null);
        const h = new GameHistory().push(action);
        expect(h.getLastAction()).toEqual(action);
    });
});

describe('GameHistory — undo()', () => {
    it('returns [same, null] when nothing to undo', () => {
        const h = new GameHistory();
        const [newH, action] = h.undo();
        expect(action).toBeNull();
        expect(newH.size).toBe(0);
    });

    it('decrements size after undo', () => {
        const h = new GameHistory().push(makeAction());
        const [undoneH] = h.undo();
        expect(undoneH.size).toBe(0);
    });

    it('returns the action that was undone', () => {
        const action = makeAction(1, 2, 3, null);
        const h = new GameHistory().push(action);
        const [, undoneAction] = h.undo();
        expect(undoneAction).toEqual(action);
    });

    it('enables redo after undo', () => {
        const h = new GameHistory().push(makeAction());
        const [undoneH] = h.undo();
        expect(undoneH.canRedo).toBe(true);
    });

    it('undos are ordered last-in-first-out', () => {
        let h = new GameHistory();
        const a1 = makeAction(0, 0, 1, null);
        const a2 = makeAction(0, 1, 2, null);
        h = h.push(a1).push(a2);

        const [, second] = h.undo();
        expect(second).toEqual(a2);
        const [h2] = h.undo();
        const [, first] = h2.undo();
        expect(first).toEqual(a1);
    });
});

describe('GameHistory — redo()', () => {
    it('returns [same, null] when nothing to redo', () => {
        const h = new GameHistory();
        const [newH, action] = h.redo();
        expect(action).toBeNull();
        expect(newH.size).toBe(0);
    });

    it('redoes the last undone action', () => {
        const action = makeAction(2, 3, 6, null);
        const h = new GameHistory().push(action);
        const [undoneH] = h.undo();
        const [redoneH, redoneAction] = undoneH.redo();

        expect(redoneAction).toEqual(action);
        expect(redoneH.size).toBe(1);
    });

    it('clears canRedo after redo up to end of stack', () => {
        const h = new GameHistory().push(makeAction());
        const [undoneH] = h.undo();
        const [redoneH] = undoneH.redo();
        expect(redoneH.canRedo).toBe(false);
    });
});

describe('GameHistory — clear()', () => {
    it('resets to empty state', () => {
        let h = new GameHistory();
        h = h.push(makeAction()).push(makeAction(1, 1, 2, null));
        const cleared = h.clear();
        expect(cleared.size).toBe(0);
        expect(cleared.canUndo).toBe(false);
        expect(cleared.canRedo).toBe(false);
    });
});

describe('GameHistory — getLog()', () => {
    it('returns only active (non-undone) actions', () => {
        let h = new GameHistory();
        h = h.push(makeAction(0, 0, 1, null));
        h = h.push(makeAction(0, 1, 2, null));
        const [undoneH] = h.undo();
        expect(undoneH.getLog()).toHaveLength(1);
    });
});

// ─── Action Factory Helpers ───────────────────────────────────────────────────

describe('createSetValueAction()', () => {
    it('creates an action with SET_VALUE type', () => {
        const a = createSetValueAction(1, 2, 5, 3);
        expect(a.type).toBe(GameActionType.SET_VALUE);
        expect(a.row).toBe(1);
        expect(a.col).toBe(2);
        expect(a.value).toBe(5);
        expect(a.previousValue).toBe(3);
    });
});

describe('createClearValueAction()', () => {
    it('creates an action with CLEAR_VALUE type and null value', () => {
        const a = createClearValueAction(3, 4, 7);
        expect(a.type).toBe(GameActionType.CLEAR_VALUE);
        expect(a.value).toBeNull();
        expect(a.previousValue).toBe(7);
    });
});

describe('createToggleNoteAction()', () => {
    it('creates an action with TOGGLE_NOTE type', () => {
        const a = createToggleNoteAction(0, 0, 4, [1, 2, 3]);
        expect(a.type).toBe(GameActionType.TOGGLE_NOTE);
        expect(a.value).toBe(4);
        expect(a.previousNotes).toEqual([1, 2, 3]);
    });

    it('stores a copy of previousNotes (not reference)', () => {
        const notes = [1, 2, 3];
        const a = createToggleNoteAction(0, 0, 4, notes);
        notes.push(5);
        expect(a.previousNotes).not.toContain(5);
    });
});

describe('createUseHintAction()', () => {
    it('creates an action with USE_HINT type', () => {
        const a = createUseHintAction(5, 6, 8, null);
        expect(a.type).toBe(GameActionType.USE_HINT);
        expect(a.value).toBe(8);
    });
});

describe('createAutoNotesAction()', () => {
    it('creates an AUTO_NOTES action with row/col = -1', () => {
        const a = createAutoNotesAction();
        expect(a.type).toBe(GameActionType.AUTO_NOTES);
        expect(a.row).toBe(-1);
        expect(a.col).toBe(-1);
    });
});
