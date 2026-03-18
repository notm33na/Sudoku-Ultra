/**
 * Static lesson definitions — 15 lessons covering Sudoku techniques
 * in ascending difficulty order.
 *
 * Each lesson has 3 steps:
 *   read     — concept explanation (markdown text)
 *   example  — annotated worked example
 *   practice — user fills one cell on a real board
 *
 * XP rewards: difficulty × 100  (rounded to nearest 50 for levels 3-5)
 */

export type StepType = 'read' | 'example' | 'practice';

export interface LessonStep {
    stepNumber: number;
    type: StepType;
    title: string;
    content: string;
    /** 81-cell board for practice steps (0 = empty) */
    puzzle?: number[];
    /** Correct completed board for validation */
    solution?: number[];
    /** Cell index the student must fill */
    targetCell?: number;
    /** Expected digit */
    targetValue?: number;
    /** Cells to highlight to guide the student */
    highlightCells?: number[];
}

export interface LessonDefinition {
    id: string;
    title: string;
    techniqueId: string;
    difficulty: 1 | 2 | 3 | 4 | 5;
    xpReward: number;
    estimatedMinutes: number;
    description: string;
    tags: string[];
    prerequisiteIds: string[];
    steps: LessonStep[];
}

// ── Shared practice boards ─────────────────────────────────────────────────

// Near-complete board — only cell 0 empty; naked single = 1
const NS_BOARD = [
    0, 2, 3, 4, 5, 6, 7, 8, 9,
    4, 5, 6, 7, 8, 9, 1, 2, 3,
    7, 8, 9, 1, 2, 3, 4, 5, 6,
    2, 1, 4, 3, 6, 5, 8, 9, 7,
    3, 6, 5, 8, 9, 7, 2, 1, 4,
    8, 9, 7, 2, 1, 4, 3, 6, 5,
    5, 3, 1, 6, 4, 2, 9, 7, 8,
    6, 4, 2, 9, 7, 8, 5, 3, 1,
    9, 7, 8, 5, 3, 1, 6, 4, 2,
];
const NS_SOLUTION = [1, ...NS_BOARD.slice(1)];

// Hidden single in row 1 col 0: only cell(0,0) can hold 1 in row 0
const HS_BOARD = [
    0, 0, 3, 4, 5, 6, 7, 8, 9,
    4, 5, 6, 7, 8, 9, 1, 2, 3,
    7, 8, 9, 1, 2, 3, 4, 5, 6,
    2, 1, 4, 3, 6, 5, 8, 9, 7,
    3, 6, 5, 8, 9, 7, 2, 1, 4,
    8, 9, 7, 2, 1, 4, 3, 6, 5,
    5, 3, 1, 6, 4, 2, 9, 7, 8,
    6, 4, 2, 9, 7, 8, 5, 3, 1,
    9, 7, 8, 5, 3, 1, 6, 4, 2,
];
// cell(0,0)=1, cell(0,1)=2
const HS_SOLUTION = [1, 2, ...HS_BOARD.slice(2)];

// ── Lesson definitions ─────────────────────────────────────────────────────

export const LESSONS: LessonDefinition[] = [
    // ── Difficulty 1 ──────────────────────────────────────────────────────
    {
        id: 'naked-singles',
        title: 'Naked Singles',
        techniqueId: 'naked-singles',
        difficulty: 1,
        xpReward: 100,
        estimatedMinutes: 3,
        description: 'The simplest Sudoku technique — find cells where only one digit can legally go.',
        tags: ['beginner', 'singles', 'elimination'],
        prerequisiteIds: [],
        steps: [
            {
                stepNumber: 1,
                type: 'read',
                title: 'What is a Naked Single?',
                content:
                    'A **Naked Single** occurs when a cell has only one possible candidate digit after ' +
                    'eliminating all digits already present in its row, column, and 3×3 box.\n\n' +
                    'Because every digit 1–9 must appear exactly once in each row, column, and box, ' +
                    'if a cell has only one candidate remaining, you can fill it in immediately — no guessing needed.\n\n' +
                    '**Key insight:** Look for cells with the fewest empty peer cells; those are most likely to be naked singles.',
            },
            {
                stepNumber: 2,
                type: 'example',
                title: 'Worked Example',
                content:
                    'Consider a cell in row 1, column 1.\n\n' +
                    '- Row 1 already contains: 2, 3, 4, 5, 6, 7, 8, 9\n' +
                    '- Column 1 already contains: 4, 7, 2, 3, 8, 5, 6, 9\n' +
                    '- Box (top-left) contains: 2, 3, 4, 5, 6, 7, 8, 9\n\n' +
                    'The only digit **not** present in any of those is **1**.\n' +
                    'Therefore cell (1,1) = **1** — a Naked Single!\n\n' +
                    'In the board below, the highlighted cell (top-left) is a naked single.',
                highlightCells: [0],
            },
            {
                stepNumber: 3,
                type: 'practice',
                title: 'Fill the Naked Single',
                content:
                    'The top-left cell (row 1, column 1) is highlighted. ' +
                    'All other cells in its row, column, and box are filled. ' +
                    'What is the only possible digit?',
                puzzle: NS_BOARD,
                solution: NS_SOLUTION,
                targetCell: 0,
                targetValue: 1,
                highlightCells: [0],
            },
        ],
    },
    {
        id: 'hidden-singles',
        title: 'Hidden Singles',
        techniqueId: 'hidden-singles',
        difficulty: 1,
        xpReward: 100,
        estimatedMinutes: 4,
        description: 'Find cells where a digit can only go in one place within a row, column, or box.',
        tags: ['beginner', 'singles', 'hidden'],
        prerequisiteIds: ['naked-singles'],
        steps: [
            {
                stepNumber: 1,
                type: 'read',
                title: 'What is a Hidden Single?',
                content:
                    'A **Hidden Single** occurs when a particular digit can only go into one cell ' +
                    'within a row, column, or 3×3 box — even though that cell may have more than one candidate.\n\n' +
                    'The digit is "hidden" because the cell looks like it has multiple options, ' +
                    'but when you check *where a specific digit can legally go* in the group, ' +
                    'only one position survives.\n\n' +
                    '**Process:** For each digit 1–9, scan each row, column, and box. ' +
                    'If that digit can only go in one cell of the group, it must go there.',
            },
            {
                stepNumber: 2,
                type: 'example',
                title: 'Spotting a Hidden Single',
                content:
                    'In the board below, look at **row 1** (the top row).\n\n' +
                    'Cells (1,1) and (1,2) are both empty.\n' +
                    '- Digit **2** is already in column 2 (from another row), so it cannot go in cell (1,2).\n' +
                    '- Digit **2** is already in the box for column 2 as well.\n' +
                    'Therefore **2 can only go in cell (1,2)** — it\'s a Hidden Single in row 1.\n\n' +
                    'Similarly, **1 can only go in cell (1,1)** because 1 appears in column 2 already.',
                highlightCells: [0, 1],
            },
            {
                stepNumber: 3,
                type: 'practice',
                title: 'Find the Hidden Single',
                content:
                    'In the top row, two cells are empty. ' +
                    'Digit 1 can only go in one of them — check where 1 already appears in column 2. ' +
                    'Fill the correct cell with 1.',
                puzzle: HS_BOARD,
                solution: HS_SOLUTION,
                targetCell: 0,
                targetValue: 1,
                highlightCells: [0, 1],
            },
        ],
    },

    // ── Difficulty 2 ──────────────────────────────────────────────────────
    {
        id: 'naked-pairs',
        title: 'Naked Pairs',
        techniqueId: 'naked-pairs',
        difficulty: 2,
        xpReward: 200,
        estimatedMinutes: 5,
        description: 'When two cells in a group share the same two candidates, eliminate those digits from the rest of the group.',
        tags: ['intermediate', 'pairs', 'elimination'],
        prerequisiteIds: ['naked-singles', 'hidden-singles'],
        steps: [
            {
                stepNumber: 1,
                type: 'read',
                title: 'What is a Naked Pair?',
                content:
                    'A **Naked Pair** occurs when exactly two cells in the same row, column, or box ' +
                    'both contain *exactly* the same two candidates — and no others.\n\n' +
                    'Because those two digits must occupy those two cells (in some order), ' +
                    'no other cell in the group can contain either of those digits.\n\n' +
                    '**Rule:** If cells A and B both have candidates {X, Y} and nothing else, ' +
                    'eliminate X and Y from all other cells in their shared row, column, or box.',
            },
            {
                stepNumber: 2,
                type: 'example',
                title: 'Naked Pair Elimination',
                content:
                    'Imagine row 5 has this candidate list:\n\n' +
                    '`_ [3,7] [3,7] _ 8 _ 2 _ _`\n\n' +
                    'Cells at positions 2 and 3 both have only candidates {3, 7}. ' +
                    'This is a Naked Pair!\n\n' +
                    '**Elimination:** Any other empty cell in row 5 that currently lists 3 or 7 as a ' +
                    'candidate can have those digits removed. ' +
                    'This often forces a naked single to appear elsewhere in the row.',
                highlightCells: [],
            },
            {
                stepNumber: 3,
                type: 'practice',
                title: 'Identify Naked Pairs',
                content:
                    'Look at the board below. Find a row or column where two cells share the same two candidates. ' +
                    'Once you find the pair, note which other cells in that group can have those candidates eliminated.\n\n' +
                    'For this practice, fill in the naked single that appears after the elimination.',
                puzzle: NS_BOARD,
                solution: NS_SOLUTION,
                targetCell: 0,
                targetValue: 1,
                highlightCells: [0],
            },
        ],
    },
    {
        id: 'hidden-pairs',
        title: 'Hidden Pairs',
        techniqueId: 'hidden-pairs',
        difficulty: 2,
        xpReward: 200,
        estimatedMinutes: 5,
        description: 'Two digits that can only appear in two cells of a group form a hidden pair — remove all other candidates from those cells.',
        tags: ['intermediate', 'pairs', 'hidden'],
        prerequisiteIds: ['hidden-singles', 'naked-pairs'],
        steps: [
            {
                stepNumber: 1,
                type: 'read',
                title: 'What is a Hidden Pair?',
                content:
                    'A **Hidden Pair** occurs when two digits can only appear in exactly two cells ' +
                    'within a row, column, or box. Even though those cells may have other candidates, ' +
                    'those two digits are "locked" to those two cells.\n\n' +
                    '**Consequence:** All other candidates in those two cells can be removed, ' +
                    'turning them into a Naked Pair which can drive further eliminations.\n\n' +
                    '**How to find it:** For each pair of digits {X, Y}, check if they both appear ' +
                    'as candidates in *only* two cells of a group.',
            },
            {
                stepNumber: 2,
                type: 'example',
                title: 'Finding a Hidden Pair',
                content:
                    'In a column, suppose digits 4 and 9 only appear as candidates in cells at rows 3 and 7.\n\n' +
                    'Even if those cells also have candidates {2, 4, 6, 9}, we know 4 and 9 must go ' +
                    'in those two cells. So we can remove 2 and 6 from both cells.\n\n' +
                    'After cleanup, those cells each hold only {4, 9} — a Naked Pair.',
                highlightCells: [],
            },
            {
                stepNumber: 3,
                type: 'practice',
                title: 'Apply Hidden Pairs Thinking',
                content:
                    'In the practice board, identify any row, column, or box where two digits are confined ' +
                    'to exactly two cells. After removing extra candidates from those cells, ' +
                    'fill in the resulting naked single.',
                puzzle: NS_BOARD,
                solution: NS_SOLUTION,
                targetCell: 0,
                targetValue: 1,
                highlightCells: [0],
            },
        ],
    },
    {
        id: 'pointing-pairs',
        title: 'Pointing Pairs',
        techniqueId: 'pointing-pairs',
        difficulty: 2,
        xpReward: 200,
        estimatedMinutes: 5,
        description: 'When a digit in a box is confined to one row or column, eliminate it from the rest of that row or column.',
        tags: ['intermediate', 'pointing', 'box-line'],
        prerequisiteIds: ['naked-singles', 'hidden-singles'],
        steps: [
            {
                stepNumber: 1,
                type: 'read',
                title: 'What are Pointing Pairs?',
                content:
                    'A **Pointing Pair** (or Pointing Triple) occurs when all candidates for a digit ' +
                    'within a 3×3 box are confined to a single row or column.\n\n' +
                    'Since that digit must go in that row or column (within the box), ' +
                    'it cannot appear anywhere else in that row or column *outside* the box.\n\n' +
                    '**Rule:** If digit X in box B all sit in row R, eliminate X from row R outside box B.',
            },
            {
                stepNumber: 2,
                type: 'example',
                title: 'Pointing Pair in Action',
                content:
                    'In the top-left box, suppose digit 5 can only go in cells (1,2) and (1,3) — both in row 1.\n\n' +
                    '5 must go somewhere in row 1 within this box. Therefore, 5 cannot appear in ' +
                    'any other cell of row 1 (outside this box).\n\n' +
                    'Eliminate 5 from all other empty cells in row 1. This often triggers naked singles.',
                highlightCells: [1, 2],
            },
            {
                stepNumber: 3,
                type: 'practice',
                title: 'Apply Pointing Pairs',
                content:
                    'Look for a digit in any box that is confined to a single row or column within that box. ' +
                    'Eliminate it from the rest of that row or column, then fill the resulting naked single.',
                puzzle: NS_BOARD,
                solution: NS_SOLUTION,
                targetCell: 0,
                targetValue: 1,
                highlightCells: [0],
            },
        ],
    },
    {
        id: 'box-line-reduction',
        title: 'Box-Line Reduction',
        techniqueId: 'box-line-reduction',
        difficulty: 2,
        xpReward: 200,
        estimatedMinutes: 5,
        description: 'The reverse of pointing pairs — confine a digit to a box using a row or column.',
        tags: ['intermediate', 'box-line', 'elimination'],
        prerequisiteIds: ['pointing-pairs'],
        steps: [
            {
                stepNumber: 1,
                type: 'read',
                title: 'Box-Line Reduction Explained',
                content:
                    '**Box-Line Reduction** is the reverse of pointing pairs.\n\n' +
                    'When all candidates for a digit in a row (or column) are confined to a single box, ' +
                    'that digit can be eliminated from all other cells in that box.\n\n' +
                    '**Rule:** If digit X in row R only appears in cells belonging to box B, ' +
                    'eliminate X from all cells in box B that are *not* in row R.',
            },
            {
                stepNumber: 2,
                type: 'example',
                title: 'Box-Line Reduction Example',
                content:
                    'Suppose in row 4, digit 7 can only go in columns 4 and 5 — both in the middle box.\n\n' +
                    'Since 7 in row 4 is locked to the middle box, we know 7 must go in that box ' +
                    'specifically in row 4. Therefore, 7 cannot appear in any other cell of the middle box ' +
                    '(rows 4, 5, or 6 outside row 4).\n\n' +
                    'Eliminate 7 from all non-row-4 cells in the middle box.',
                highlightCells: [30, 31],
            },
            {
                stepNumber: 3,
                type: 'practice',
                title: 'Box-Line Reduction Practice',
                content:
                    'Find a digit in a row that only appears in candidates within one box. ' +
                    'Eliminate that digit from the rest of that box, then solve the resulting naked single.',
                puzzle: NS_BOARD,
                solution: NS_SOLUTION,
                targetCell: 0,
                targetValue: 1,
                highlightCells: [0],
            },
        ],
    },

    // ── Difficulty 3 ──────────────────────────────────────────────────────
    {
        id: 'naked-triples',
        title: 'Naked Triples',
        techniqueId: 'naked-triples',
        difficulty: 3,
        xpReward: 350,
        estimatedMinutes: 7,
        description: 'Three cells in a group that collectively hold only three candidates — eliminate those digits elsewhere.',
        tags: ['advanced', 'triples', 'elimination'],
        prerequisiteIds: ['naked-pairs'],
        steps: [
            {
                stepNumber: 1,
                type: 'read',
                title: 'What is a Naked Triple?',
                content:
                    'A **Naked Triple** is a generalisation of Naked Pairs. ' +
                    'Three cells in the same row, column, or box collectively contain only three distinct candidates.\n\n' +
                    'The cells don\'t each need all three candidates — any combination works, as long as ' +
                    'the union of all their candidates contains exactly three digits.\n\n' +
                    'Valid forms: {1,2,3}, {1,2}, {2,3} — the union is {1,2,3}.\n\n' +
                    'Eliminate those three digits from all other cells in the group.',
            },
            {
                stepNumber: 2,
                type: 'example',
                title: 'Recognising a Naked Triple',
                content:
                    'In a column, three cells have these candidates:\n' +
                    '- Cell A: {2, 5}\n' +
                    '- Cell B: {2, 8}\n' +
                    '- Cell C: {5, 8}\n\n' +
                    'Union = {2, 5, 8} — three digits across three cells. That\'s a Naked Triple!\n\n' +
                    'Eliminate 2, 5, and 8 from all other cells in this column.',
                highlightCells: [],
            },
            {
                stepNumber: 3,
                type: 'practice',
                title: 'Apply Naked Triples',
                content:
                    'Scan the columns for three cells whose candidates form a set of exactly three digits. ' +
                    'After eliminating those digits from the rest of the column, fill in the naked single that appears.',
                puzzle: NS_BOARD,
                solution: NS_SOLUTION,
                targetCell: 0,
                targetValue: 1,
                highlightCells: [0],
            },
        ],
    },
    {
        id: 'x-wing',
        title: 'X-Wing',
        techniqueId: 'x-wing',
        difficulty: 3,
        xpReward: 350,
        estimatedMinutes: 8,
        description: 'A digit confined to the same two columns in two different rows forms an X — eliminate it from those columns elsewhere.',
        tags: ['advanced', 'fish', 'x-wing'],
        prerequisiteIds: ['pointing-pairs', 'box-line-reduction'],
        steps: [
            {
                stepNumber: 1,
                type: 'read',
                title: 'Understanding X-Wing',
                content:
                    'An **X-Wing** occurs when a digit appears as a candidate in exactly two cells ' +
                    'in each of two different rows, AND those cells are in the same two columns.\n\n' +
                    'The four cells form an "X" shape. The digit must go into either:\n' +
                    '- (Row1,ColA) and (Row2,ColB), OR\n' +
                    '- (Row1,ColB) and (Row2,ColA)\n\n' +
                    'Either way, columns A and B will each contain the digit once. ' +
                    'Therefore, eliminate this digit from all other cells in those two columns.',
            },
            {
                stepNumber: 2,
                type: 'example',
                title: 'X-Wing Pattern',
                content:
                    'Digit 7 appears as a candidate in:\n' +
                    '- Row 2: only columns 3 and 7\n' +
                    '- Row 6: only columns 3 and 7\n\n' +
                    'These four cells form an X-Wing. ' +
                    'Regardless of which diagonal is used, column 3 and column 7 each get exactly one 7.\n\n' +
                    'Therefore, eliminate 7 from all other cells in columns 3 and 7 (rows 1,3,4,5,7,8,9).',
                highlightCells: [11, 15, 47, 51],
            },
            {
                stepNumber: 3,
                type: 'practice',
                title: 'Spot the X-Wing',
                content:
                    'Find a digit in the board that appears in exactly two cells each in two rows, ' +
                    'with both pairs sharing the same two columns. Eliminate accordingly, then fill the resulting single.',
                puzzle: NS_BOARD,
                solution: NS_SOLUTION,
                targetCell: 0,
                targetValue: 1,
                highlightCells: [0],
            },
        ],
    },
    {
        id: 'xy-wing',
        title: 'XY-Wing',
        techniqueId: 'xy-wing',
        difficulty: 3,
        xpReward: 350,
        estimatedMinutes: 8,
        description: 'Three bi-value cells in a wing pattern allow eliminating a digit from cells that see both wing tips.',
        tags: ['advanced', 'wing', 'chains'],
        prerequisiteIds: ['naked-pairs'],
        steps: [
            {
                stepNumber: 1,
                type: 'read',
                title: 'XY-Wing Explained',
                content:
                    'An **XY-Wing** uses three cells, each with exactly two candidates:\n\n' +
                    '- **Pivot** cell: candidates {X, Y}\n' +
                    '- **Wing 1**: candidates {X, Z}, shares a group with the pivot\n' +
                    '- **Wing 2**: candidates {Y, Z}, shares a group with the pivot\n\n' +
                    'No matter what the pivot holds (X or Y):\n' +
                    '- If pivot = X → Wing 1 = Z\n' +
                    '- If pivot = Y → Wing 2 = Z\n\n' +
                    'Either way, Z is placed in one of the two wings. ' +
                    'Eliminate Z from any cell that sees **both** wings.',
            },
            {
                stepNumber: 2,
                type: 'example',
                title: 'XY-Wing Diagram',
                content:
                    'Pivot at (5,5): candidates {3, 7}\n' +
                    'Wing A at (5,1): candidates {3, 9} — shares row with pivot\n' +
                    'Wing B at (2,5): candidates {7, 9} — shares column with pivot\n\n' +
                    'Z = 9. Any cell that sees both (5,1) and (2,5) cannot be 9.\n' +
                    'Cell (2,1) sees both wings → eliminate 9 from (2,1).',
                highlightCells: [44, 40, 14],
            },
            {
                stepNumber: 3,
                type: 'practice',
                title: 'Apply XY-Wing Logic',
                content:
                    'Identify a pivot cell with two candidates and find its two wings. ' +
                    'Determine which digit can be eliminated from cells that see both wings, ' +
                    'then fill the resulting naked single.',
                puzzle: NS_BOARD,
                solution: NS_SOLUTION,
                targetCell: 0,
                targetValue: 1,
                highlightCells: [0],
            },
        ],
    },
    {
        id: 'unique-rectangle',
        title: 'Unique Rectangle',
        techniqueId: 'unique-rectangle',
        difficulty: 3,
        xpReward: 350,
        estimatedMinutes: 8,
        description: 'Avoid creating a deadly pattern by ensuring puzzles with unique solutions stay unique.',
        tags: ['advanced', 'uniqueness', 'rectangle'],
        prerequisiteIds: ['naked-pairs'],
        steps: [
            {
                stepNumber: 1,
                type: 'read',
                title: 'Unique Rectangle Logic',
                content:
                    'A **Unique Rectangle** is based on the rule that a valid Sudoku has exactly one solution.\n\n' +
                    'If four cells forming a rectangle (two rows × two columns) in two boxes ' +
                    'all have the same two candidates, the puzzle would have multiple solutions — which is invalid.\n\n' +
                    'We can use this to eliminate candidates: if three of the four "deadly" cells are confirmed ' +
                    'bi-value, the fourth cell must NOT reduce to just those two candidates, ' +
                    'so we can eliminate one of them from it.',
            },
            {
                stepNumber: 2,
                type: 'example',
                title: 'Unique Rectangle Type 1',
                content:
                    'Cells at (2,1), (2,4), (7,1), (7,4) form a rectangle across two boxes.\n' +
                    'Three of them have only candidates {4, 9}.\n' +
                    'The fourth cell, say (7,4), has candidates {4, 7, 9}.\n\n' +
                    'If (7,4) were also just {4, 9}, we\'d have a deadly pattern. ' +
                    'Since the puzzle is valid, (7,4) must use 7. We can eliminate {4, 9} from it.\n' +
                    'Result: (7,4) = 7.',
                highlightCells: [10, 13, 55, 58],
            },
            {
                stepNumber: 3,
                type: 'practice',
                title: 'Spot the Unique Rectangle',
                content:
                    'Look for a rectangle of four cells across two boxes sharing the same two candidates. ' +
                    'If three cells are confirmed as bi-value, the fourth must avoid creating the deadly pattern.',
                puzzle: NS_BOARD,
                solution: NS_SOLUTION,
                targetCell: 0,
                targetValue: 1,
                highlightCells: [0],
            },
        ],
    },

    // ── Difficulty 4 ──────────────────────────────────────────────────────
    {
        id: 'swordfish',
        title: 'Swordfish',
        techniqueId: 'swordfish',
        difficulty: 4,
        xpReward: 500,
        estimatedMinutes: 10,
        description: 'A three-row extension of X-Wing — eliminates a digit from three columns.',
        tags: ['expert', 'fish', 'swordfish'],
        prerequisiteIds: ['x-wing'],
        steps: [
            {
                stepNumber: 1,
                type: 'read',
                title: 'Swordfish — X-Wing Extended',
                content:
                    'A **Swordfish** extends the X-Wing concept to three rows (or columns).\n\n' +
                    'A digit forms a Swordfish when it appears in exactly 2 or 3 cells in each of ' +
                    'three rows, AND all those cells are in the same three columns.\n\n' +
                    'The digit must be placed exactly once in each of those three columns. ' +
                    'Therefore, eliminate it from all other cells in those three columns.\n\n' +
                    'Swordfish works exactly like X-Wing but across 3×3 instead of 2×2.',
            },
            {
                stepNumber: 2,
                type: 'example',
                title: 'Swordfish Pattern',
                content:
                    'Digit 3 in rows 1, 4, and 7:\n' +
                    '- Row 1: columns 2, 5\n' +
                    '- Row 4: columns 2, 5, 8\n' +
                    '- Row 7: columns 5, 8\n\n' +
                    'All candidates for 3 in these rows sit in columns 2, 5, and 8. ' +
                    'This is a Swordfish! Eliminate 3 from all other cells in columns 2, 5, and 8.',
                highlightCells: [1, 4, 28, 31, 34, 58, 61],
            },
            {
                stepNumber: 3,
                type: 'practice',
                title: 'Find the Swordfish',
                content:
                    'Look for a digit whose candidates in three rows are confined to three columns. ' +
                    'Apply the Swordfish elimination, then fill in any resulting singles.',
                puzzle: NS_BOARD,
                solution: NS_SOLUTION,
                targetCell: 0,
                targetValue: 1,
                highlightCells: [0],
            },
        ],
    },
    {
        id: 'xyz-wing',
        title: 'XYZ-Wing',
        techniqueId: 'xyz-wing',
        difficulty: 4,
        xpReward: 500,
        estimatedMinutes: 10,
        description: 'An XY-Wing variant where the pivot holds three candidates, allowing elimination of Z.',
        tags: ['expert', 'wing', 'chains'],
        prerequisiteIds: ['xy-wing'],
        steps: [
            {
                stepNumber: 1,
                type: 'read',
                title: 'XYZ-Wing vs XY-Wing',
                content:
                    'An **XYZ-Wing** is similar to XY-Wing but the pivot cell has three candidates {X, Y, Z} instead of two.\n\n' +
                    '- Pivot: {X, Y, Z}\n' +
                    '- Wing 1: {X, Z} — sees the pivot\n' +
                    '- Wing 2: {Y, Z} — sees the pivot\n\n' +
                    'In all cases, Z is placed in either the pivot, Wing 1, or Wing 2. ' +
                    'Eliminate Z from any cell that sees **all three** of pivot, Wing 1, and Wing 2.\n\n' +
                    'Note: unlike XY-Wing, the elimination zone now includes cells that see the pivot too.',
            },
            {
                stepNumber: 2,
                type: 'example',
                title: 'XYZ-Wing in Practice',
                content:
                    'Pivot at (4,4): {2, 6, 8}\n' +
                    'Wing 1 at (4,7): {2, 8} — same row as pivot\n' +
                    'Wing 2 at (1,4): {6, 8} — same column as pivot\n\n' +
                    'Z = 8. Cells that see ALL three: those in the same row as Wing 1 AND same column as Wing 2 AND same box as pivot.\n' +
                    'Cell (1,7) sees both wings and the pivot → eliminate 8 from (1,7).',
                highlightCells: [40, 43, 4],
            },
            {
                stepNumber: 3,
                type: 'practice',
                title: 'Apply XYZ-Wing',
                content:
                    'Find a three-candidate pivot with two bi-value wings sharing X,Z and Y,Z respectively. ' +
                    'Eliminate Z from cells visible to all three cells, then fill the resulting single.',
                puzzle: NS_BOARD,
                solution: NS_SOLUTION,
                targetCell: 0,
                targetValue: 1,
                highlightCells: [0],
            },
        ],
    },
    {
        id: 'w-wing',
        title: 'W-Wing',
        techniqueId: 'w-wing',
        difficulty: 4,
        xpReward: 500,
        estimatedMinutes: 10,
        description: 'Two bi-value cells connected by a strong link allow eliminating a shared candidate.',
        tags: ['expert', 'wing', 'links'],
        prerequisiteIds: ['xy-wing'],
        steps: [
            {
                stepNumber: 1,
                type: 'read',
                title: 'W-Wing Logic',
                content:
                    'A **W-Wing** uses two bi-value cells with the same candidates {X, Y} connected by a strong link on X.\n\n' +
                    '- Cell A: {X, Y}\n' +
                    '- Cell B: {X, Y}\n' +
                    '- A strong link on X connects A and B (X in a row/col/box can only go in A or B)\n\n' +
                    'If A = X, the strong link forces B ≠ X, so B = Y.\n' +
                    'If A = Y, then B can be X or Y, but the strong link still forces one of them.\n\n' +
                    'Result: eliminate Y from any cell that sees both A and B.',
            },
            {
                stepNumber: 2,
                type: 'example',
                title: 'W-Wing Example',
                content:
                    'Cell A at (3,2): {5, 9}\n' +
                    'Cell B at (7,8): {5, 9}\n' +
                    'Strong link: digit 5 in column 5 can only go in row 3 or row 7 (rows where 5 isn\'t yet placed in col 5).\n\n' +
                    'Either A=9 (and the strong link gives B=9 indirectly) or B=9.\n' +
                    'Either way, Y=9 goes in A or B. Eliminate 9 from cells seeing both A and B.',
                highlightCells: [20, 62],
            },
            {
                stepNumber: 3,
                type: 'practice',
                title: 'Identify the W-Wing',
                content:
                    'Find two bi-value cells with the same pair of candidates. ' +
                    'Confirm a strong link on one candidate, then eliminate the other candidate from their common peers.',
                puzzle: NS_BOARD,
                solution: NS_SOLUTION,
                targetCell: 0,
                targetValue: 1,
                highlightCells: [0],
            },
        ],
    },
    {
        id: 'bug-plus-1',
        title: 'BUG+1',
        techniqueId: 'bug-plus-1',
        difficulty: 4,
        xpReward: 500,
        estimatedMinutes: 10,
        description: 'A near-BUG state (all cells bi-value except one) forces the extra cell to its candidate that breaks the deadly pattern.',
        tags: ['expert', 'uniqueness', 'bug'],
        prerequisiteIds: ['unique-rectangle'],
        steps: [
            {
                stepNumber: 1,
                type: 'read',
                title: 'BUG (Bivalue Universal Grave)',
                content:
                    'A **BUG** is a deadly pattern where every remaining empty cell has exactly two candidates AND every candidate in each row, column, and box appears exactly twice.\n\n' +
                    'A BUG would create multiple solutions, which is impossible in a proper Sudoku.\n\n' +
                    '**BUG+1:** If exactly one cell has three candidates and all others are bi-value, ' +
                    'that extra cell is the "BUG+1 cell." Its third candidate (the one that appears an odd number of times) ' +
                    'must be the correct digit — otherwise a BUG would arise.',
            },
            {
                stepNumber: 2,
                type: 'example',
                title: 'Solving BUG+1',
                content:
                    'Suppose all empty cells have two candidates, except cell (6,3) which has {2, 5, 7}.\n\n' +
                    'Check which digit in {2, 5, 7} appears an odd number of times as a candidate across its row, column, or box.\n\n' +
                    'Say 7 appears 3 times in column 3 while 2 and 5 each appear twice. ' +
                    '7 is the "odd one out" — therefore cell (6,3) = 7, avoiding the BUG.',
                highlightCells: [48],
            },
            {
                stepNumber: 3,
                type: 'practice',
                title: 'BUG+1 in Practice',
                content:
                    'In the board, find the single cell with three candidates when all others are bi-value. ' +
                    'Identify the candidate that appears an odd number of times in its row, column, and box. ' +
                    'That is the correct value for that cell.',
                puzzle: NS_BOARD,
                solution: NS_SOLUTION,
                targetCell: 0,
                targetValue: 1,
                highlightCells: [0],
            },
        ],
    },

    // ── Difficulty 5 ──────────────────────────────────────────────────────
    {
        id: 'aic',
        title: 'Alternating Inference Chains (AIC)',
        techniqueId: 'aic',
        difficulty: 5,
        xpReward: 750,
        estimatedMinutes: 15,
        description: 'Chain logic alternating weak and strong links to force cell values or eliminations.',
        tags: ['master', 'chains', 'aic', 'advanced-logic'],
        prerequisiteIds: ['xy-wing', 'w-wing'],
        steps: [
            {
                stepNumber: 1,
                type: 'read',
                title: 'Understanding AIC',
                content:
                    'An **Alternating Inference Chain (AIC)** is a sequence of cells connected by alternating strong and weak links.\n\n' +
                    '- **Strong link:** exactly two cells can hold a digit in a group — if one is false, the other must be true.\n' +
                    '- **Weak link:** two cells share a digit as a candidate — if one is true, the other is false.\n\n' +
                    'An AIC starts and ends with strong links. ' +
                    'If the chain starts and ends on the same digit in cells that see each other, ' +
                    'that digit can be eliminated from cells that see both endpoints.\n\n' +
                    'XY-Wing and W-Wing are short, specialised AICs.',
            },
            {
                stepNumber: 2,
                type: 'example',
                title: 'Building an AIC',
                content:
                    'Chain: (A=5) -strong- (B=5) -weak- (B=3) -strong- (C=3) -weak- (C=5)\n\n' +
                    'Start: cell A, digit 5 (could be true or false)\n' +
                    'End: cell C, digit 5\n\n' +
                    'If A≠5 → B=5 (strong) → B≠3 (weak) → C=3 (strong) → C≠5 (weak)\n' +
                    'If A=5 → then A=5 directly\n\n' +
                    'Either way, cells that see **both** A and C cannot be 5. ' +
                    'Eliminate 5 from all cells in the intersection of A\'s and C\'s visible cells.',
                highlightCells: [],
            },
            {
                stepNumber: 3,
                type: 'practice',
                title: 'Trace an AIC',
                content:
                    'Build a short alternating chain (3–4 links) from a starting cell. ' +
                    'Identify whether the chain causes an elimination or forces a cell value. ' +
                    'Apply the result to progress the board.',
                puzzle: NS_BOARD,
                solution: NS_SOLUTION,
                targetCell: 0,
                targetValue: 1,
                highlightCells: [0],
            },
        ],
    },
];

// ── Derived lookups ────────────────────────────────────────────────────────

export const LESSON_MAP = new Map<string, LessonDefinition>(
    LESSONS.map((l) => [l.id, l]),
);

export const LESSONS_BY_DIFFICULTY: Record<number, LessonDefinition[]> = {
    1: LESSONS.filter((l) => l.difficulty === 1),
    2: LESSONS.filter((l) => l.difficulty === 2),
    3: LESSONS.filter((l) => l.difficulty === 3),
    4: LESSONS.filter((l) => l.difficulty === 4),
    5: LESSONS.filter((l) => l.difficulty === 5),
};

export const TOTAL_STEPS = LESSONS.reduce((n, l) => n + l.steps.length, 0);
