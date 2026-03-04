// ─── Enums ────────────────────────────────────────────────────────────────────

export enum Difficulty {
    BEGINNER = 'beginner',
    EASY = 'easy',
    MEDIUM = 'medium',
    HARD = 'hard',
    EXPERT = 'expert',
    EVIL = 'evil',
}

export enum CellStatus {
    GIVEN = 'given',
    EMPTY = 'empty',
    FILLED = 'filled',
    ERROR = 'error',
}

export enum GameStatus {
    IN_PROGRESS = 'in_progress',
    COMPLETED = 'completed',
    PAUSED = 'paused',
    ABANDONED = 'abandoned',
}

// ─── Core Puzzle Types ────────────────────────────────────────────────────────

export interface Cell {
    row: number;
    col: number;
    value: number | null;
    status: CellStatus;
    notes: number[];
    isLocked: boolean;
}

export type Grid = Cell[][];

export interface Puzzle {
    id: string;
    grid: Grid;
    solution: number[][];
    difficulty: Difficulty;
    clueCount: number;
    createdAt: string;
}

// ─── Game Session ─────────────────────────────────────────────────────────────

export interface GameSession {
    id: string;
    userId: string;
    puzzleId: string;
    currentGrid: Grid;
    status: GameStatus;
    difficulty: Difficulty;
    timeElapsedMs: number;
    score: number;
    hintsUsed: number;
    errorsCount: number;
    startedAt: string;
    updatedAt: string;
    completedAt: string | null;
}

// ─── User ─────────────────────────────────────────────────────────────────────

export interface User {
    id: string;
    email: string;
    username: string;
    avatarUrl: string | null;
    createdAt: string;
    updatedAt: string;
}

// ─── Score & Streak ───────────────────────────────────────────────────────────

export interface Score {
    id: string;
    userId: string;
    puzzleId: string;
    sessionId: string;
    timeMs: number;
    points: number;
    difficulty: Difficulty;
    completedAt: string;
}

export interface Streak {
    id: string;
    userId: string;
    currentStreak: number;
    longestStreak: number;
    lastPlayedDate: string;
}

// ─── Daily Puzzle ─────────────────────────────────────────────────────────────

export interface DailyPuzzle {
    id: string;
    puzzleId: string;
    date: string;
    difficulty: Difficulty;
}

// ─── API Types ────────────────────────────────────────────────────────────────

export interface ApiResponse<T> {
    success: boolean;
    data: T | null;
    error: string | null;
    timestamp: string;
}

export interface PaginatedResponse<T> extends ApiResponse<T[]> {
    page: number;
    pageSize: number;
    totalCount: number;
    totalPages: number;
}

// ─── Auth Types ───────────────────────────────────────────────────────────────

export interface AuthTokens {
    accessToken: string;
    refreshToken: string;
    expiresIn: number;
}

export interface LoginRequest {
    email: string;
    password: string;
}

export interface RegisterRequest {
    email: string;
    username: string;
    password: string;
}

// ─── Hint Types ───────────────────────────────────────────────────────────────

export interface Hint {
    row: number;
    col: number;
    value: number;
    technique: string;
    explanation: string;
}

// ─── Event Sourcing (Undo/Redo) ───────────────────────────────────────────────

export enum GameActionType {
    SET_VALUE = 'set_value',
    CLEAR_VALUE = 'clear_value',
    TOGGLE_NOTE = 'toggle_note',
    SET_NOTES = 'set_notes',
    CLEAR_NOTES = 'clear_notes',
    USE_HINT = 'use_hint',
    VALIDATE = 'validate',
    AUTO_NOTES = 'auto_notes',
}

export interface GameAction {
    type: GameActionType;
    row: number;
    col: number;
    value: number | null;
    previousValue: number | null;
    previousNotes: number[];
    timestamp: number;
}
