// ─── Sudoku Ultra Color Palette ───────────────────────────────────────────────

export const colors = {
    // Brand
    primary: {
        50: '#eff6ff',
        100: '#dbeafe',
        200: '#bfdbfe',
        300: '#93c5fd',
        400: '#60a5fa',
        500: '#3b82f6',
        600: '#2563eb',
        700: '#1d4ed8',
        800: '#1e40af',
        900: '#1e3a8a',
    },

    // Surfaces
    surface: {
        dark: '#0f172a',
        darkAlt: '#1e293b',
        card: '#1e293b',
        light: '#f8fafc',
    },

    // Text
    text: {
        primary: '#f8fafc',
        secondary: '#94a3b8',
        muted: '#64748b',
        dark: '#0f172a',
        accent: '#60a5fa',
    },

    // Cell states
    cell: {
        given: '#334155',
        givenText: '#e2e8f0',
        empty: '#1e293b',
        emptyText: '#60a5fa',
        selected: '#1d4ed8',
        selectedText: '#ffffff',
        highlighted: '#1e3a5c',
        highlightedText: '#93c5fd',
        error: '#7f1d1d',
        errorText: '#fca5a5',
        noteText: '#64748b',
    },

    // Grid
    grid: {
        border: '#475569',
        boxBorder: '#94a3b8',
        cellBorder: '#334155',
    },

    // Status
    success: '#22c55e',
    warning: '#f59e0b',
    error: '#ef4444',

    // Difficulty badges
    difficulty: {
        beginner: '#22c55e',
        easy: '#3b82f6',
        medium: '#f59e0b',
        hard: '#f97316',
        expert: '#ef4444',
        evil: '#a855f7',
    },
} as const;
