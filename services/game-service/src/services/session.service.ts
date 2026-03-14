import { getHint as engineGetHint, findConflicts, cellGridToNumberGrid } from '@sudoku-ultra/sudoku-engine';
import { Grid } from '@sudoku-ultra/shared-types';
import { prisma } from '../prisma/client';
import { AppError } from '../middleware/errorHandler';
import { CreateSessionInput, UpdateSessionInput, CompleteSessionInput } from '../schemas';
import { getPuzzleWithSolution } from './puzzle.service';
import { kafkaService } from './kafka.service';
import { checkSessionAnomaly } from './anomaly.service';

// ─── Create Session ───────────────────────────────────────────────────────────

export async function createSession(userId: string, input: CreateSessionInput) {
    const puzzle = await getPuzzleWithSolution(input.puzzleId);

    const session = await prisma.gameSession.create({
        data: {
            userId,
            puzzleId: puzzle.id,
            currentGrid: puzzle.grid as object,
            difficulty: puzzle.difficulty,
            status: 'in_progress',
        },
        include: { puzzle: { select: { grid: true, difficulty: true, clueCount: true } } },
    });

    return {
        id: session.id,
        puzzleId: session.puzzleId,
        currentGrid: session.currentGrid,
        status: session.status,
        difficulty: session.difficulty,
        timeElapsedMs: session.timeElapsedMs,
        hintsUsed: session.hintsUsed,
        errorsCount: session.errorsCount,
        startedAt: session.startedAt.toISOString(),
    };
}

// ─── Get Session ──────────────────────────────────────────────────────────────

export async function getSession(sessionId: string, userId: string) {
    const session = await prisma.gameSession.findUnique({ where: { id: sessionId } });
    if (!session) throw new AppError(404, 'Session not found');
    if (session.userId !== userId) throw new AppError(403, 'Not your session');

    return {
        id: session.id,
        puzzleId: session.puzzleId,
        currentGrid: session.currentGrid,
        status: session.status,
        difficulty: session.difficulty,
        timeElapsedMs: session.timeElapsedMs,
        score: session.score,
        hintsUsed: session.hintsUsed,
        errorsCount: session.errorsCount,
        startedAt: session.startedAt.toISOString(),
        updatedAt: session.updatedAt.toISOString(),
        completedAt: session.completedAt?.toISOString() ?? null,
    };
}

// ─── Update Session ───────────────────────────────────────────────────────────

export async function updateSession(sessionId: string, userId: string, input: UpdateSessionInput) {
    const session = await prisma.gameSession.findUnique({ where: { id: sessionId } });
    if (!session) throw new AppError(404, 'Session not found');
    if (session.userId !== userId) throw new AppError(403, 'Not your session');
    if (session.status === 'completed') throw new AppError(400, 'Session already completed');

    const updateData: Record<string, unknown> = {};
    if (input.currentGrid !== undefined) updateData.currentGrid = input.currentGrid;
    if (input.timeElapsedMs !== undefined) updateData.timeElapsedMs = input.timeElapsedMs;
    if (input.status !== undefined) updateData.status = input.status;

    const updated = await prisma.gameSession.update({
        where: { id: sessionId },
        data: updateData,
    });

    return {
        id: updated.id,
        status: updated.status,
        timeElapsedMs: updated.timeElapsedMs,
        updatedAt: updated.updatedAt.toISOString(),
    };
}

// ─── Get Hint ─────────────────────────────────────────────────────────────────

export async function getSessionHint(sessionId: string, userId: string) {
    const session = await prisma.gameSession.findUnique({ where: { id: sessionId } });
    if (!session) throw new AppError(404, 'Session not found');
    if (session.userId !== userId) throw new AppError(403, 'Not your session');
    if (session.status !== 'in_progress') throw new AppError(400, 'Session not in progress');

    const puzzle = await getPuzzleWithSolution(session.puzzleId);
    const currentGrid = session.currentGrid as unknown as Grid;
    const numberGrid = cellGridToNumberGrid(currentGrid);
    const solution = puzzle.solution as unknown as number[][];

    const hint = engineGetHint(numberGrid, solution);
    if (!hint) throw new AppError(400, 'No hint available — puzzle may already be complete');

    // Increment hint counter
    await prisma.gameSession.update({
        where: { id: sessionId },
        data: { hintsUsed: { increment: 1 } },
    });

    return hint;
}

// ─── Validate Session ─────────────────────────────────────────────────────────

export async function validateSession(sessionId: string, userId: string) {
    const session = await prisma.gameSession.findUnique({ where: { id: sessionId } });
    if (!session) throw new AppError(404, 'Session not found');
    if (session.userId !== userId) throw new AppError(403, 'Not your session');

    const currentGrid = session.currentGrid as unknown as Grid;
    const numberGrid = cellGridToNumberGrid(currentGrid);
    const conflicts = findConflicts(numberGrid);

    if (conflicts.length > 0) {
        await prisma.gameSession.update({
            where: { id: sessionId },
            data: { errorsCount: { increment: conflicts.length } },
        });
    }

    return {
        valid: conflicts.length === 0,
        conflicts,
        errorsCount: session.errorsCount + conflicts.length,
    };
}

// ─── Complete Session ─────────────────────────────────────────────────────────

export async function completeSession(
    sessionId: string,
    userId: string,
    input: CompleteSessionInput,
) {
    const session = await prisma.gameSession.findUnique({ where: { id: sessionId } });
    if (!session) throw new AppError(404, 'Session not found');
    if (session.userId !== userId) throw new AppError(403, 'Not your session');
    if (session.status === 'completed') throw new AppError(400, 'Session already completed');

    // Calculate score: base points minus penalties
    const basePoints = difficultyPoints(session.difficulty);
    const timePenalty = Math.floor(input.timeElapsedMs / 60000); // -1 per minute
    const hintPenalty = session.hintsUsed * 50;
    const errorPenalty = session.errorsCount * 25;
    const finalScore = Math.max(0, basePoints - timePenalty - hintPenalty - errorPenalty);

    const now = new Date();

    const updated = await prisma.gameSession.update({
        where: { id: sessionId },
        data: {
            status: 'completed',
            currentGrid: input.currentGrid,
            timeElapsedMs: input.timeElapsedMs,
            score: finalScore,
            completedAt: now,
        },
    });

    // Record score
    await prisma.score.create({
        data: {
            userId,
            puzzleId: session.puzzleId,
            sessionId,
            timeMs: input.timeElapsedMs,
            points: finalScore,
            difficulty: session.difficulty,
            completedAt: now,
        },
    });

    // Anti-cheat anomaly check — fire-and-forget, never blocks gameplay.
    checkSessionAnomaly({
        sessionId,
        userId,
        difficulty: session.difficulty,
        timeElapsedMs: input.timeElapsedMs,
        cellsFilled: cells_to_fill(session.difficulty),
        errorsCount: session.errorsCount,
        hintsUsed: session.hintsUsed,
    }).catch(() => null);

    // Publish analytics event to Kafka — fire-and-forget, never blocks gameplay
    kafkaService.publishSessionCompleted({
        user_id: userId,
        puzzle_id: session.puzzleId,
        session_id: sessionId,
        difficulty: session.difficulty,
        time_elapsed_ms: input.timeElapsedMs,
        score: finalScore,
        hints_used: session.hintsUsed,
        errors_count: session.errorsCount,
        completed_at: now.toISOString(),
    });

    return {
        id: updated.id,
        status: 'completed',
        score: finalScore,
        timeElapsedMs: input.timeElapsedMs,
        completedAt: now.toISOString(),
    };
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function cells_to_fill(difficulty: string): number {
    const map: Record<string, number> = {
        super_easy: 30, beginner: 35, easy: 40,
        medium: 45, hard: 50, expert: 55, evil: 60,
    };
    return map[difficulty] ?? 45;
}

function difficultyPoints(difficulty: string): number {
    const map: Record<string, number> = {
        beginner: 100,
        easy: 200,
        medium: 400,
        hard: 800,
        expert: 1500,
        evil: 3000,
    };
    return map[difficulty] ?? 200;
}
