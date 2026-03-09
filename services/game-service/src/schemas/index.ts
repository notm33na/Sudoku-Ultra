import { z } from 'zod';

// ─── Auth Schemas ─────────────────────────────────────────────────────────────

export const registerSchema = z.object({
    email: z.string().email('Invalid email address'),
    username: z
        .string()
        .min(3, 'Username must be at least 3 characters')
        .max(30, 'Username must be at most 30 characters')
        .regex(/^[a-zA-Z0-9_]+$/, 'Username can only contain letters, numbers, and underscores'),
    password: z.string().min(8, 'Password must be at least 8 characters'),
});

export const loginSchema = z.object({
    email: z.string().email('Invalid email address'),
    password: z.string().min(1, 'Password is required'),
});

export const refreshSchema = z.object({
    refreshToken: z.string().min(1, 'Refresh token is required'),
});

// ─── Puzzle Schemas ───────────────────────────────────────────────────────────

export const generatePuzzleSchema = z.object({
    difficulty: z.enum(['beginner', 'easy', 'medium', 'hard', 'expert', 'evil']),
});

// ─── Session Schemas ──────────────────────────────────────────────────────────

export const createSessionSchema = z.object({
    puzzleId: z.string().uuid('Invalid puzzle ID'),
});

export const updateSessionSchema = z.object({
    currentGrid: z.any().optional(), // Cell[][] — validated at service layer
    timeElapsedMs: z.number().int().nonnegative().optional(),
    status: z.enum(['in_progress', 'paused', 'abandoned']).optional(),
});

export const completeSessionSchema = z.object({
    timeElapsedMs: z.number().int().nonnegative(),
    currentGrid: z.any(), // Cell[][] — final state
});

// ─── Score Schemas ────────────────────────────────────────────────────────────

export const leaderboardQuerySchema = z.object({
    difficulty: z.enum(['beginner', 'easy', 'medium', 'hard', 'expert', 'evil']).optional(),
    limit: z.coerce.number().int().min(1).max(100).default(10),
    page: z.coerce.number().int().min(1).default(1),
});

// ─── Type Exports ─────────────────────────────────────────────────────────────

export type RegisterInput = z.infer<typeof registerSchema>;
export type LoginInput = z.infer<typeof loginSchema>;
export type RefreshInput = z.infer<typeof refreshSchema>;
export type GeneratePuzzleInput = z.infer<typeof generatePuzzleSchema>;
export type CreateSessionInput = z.infer<typeof createSessionSchema>;
export type UpdateSessionInput = z.infer<typeof updateSessionSchema>;
export type CompleteSessionInput = z.infer<typeof completeSessionSchema>;
export type LeaderboardQuery = z.infer<typeof leaderboardQuerySchema>;
