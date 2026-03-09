import { Difficulty } from '@sudoku-ultra/shared-types';
import { generatePuzzle as engineGenerate } from '@sudoku-ultra/sudoku-engine';
import { prisma } from '../prisma/client';
import { AppError } from '../middleware/errorHandler';

// ─── Generate Puzzle ──────────────────────────────────────────────────────────

export async function generatePuzzle(difficulty: string) {
    const puzzle = engineGenerate(difficulty as Difficulty);

    const saved = await prisma.puzzle.create({
        data: {
            grid: JSON.parse(JSON.stringify(puzzle.grid)),
            solution: JSON.parse(JSON.stringify(puzzle.solution)),
            difficulty: puzzle.difficulty,
            clueCount: puzzle.clueCount,
        },
    });

    return {
        id: saved.id,
        grid: saved.grid,
        difficulty: saved.difficulty,
        clueCount: saved.clueCount,
        createdAt: saved.createdAt.toISOString(),
    };
}

// ─── Get Puzzle ───────────────────────────────────────────────────────────────

export async function getPuzzle(id: string) {
    const puzzle = await prisma.puzzle.findUnique({ where: { id } });
    if (!puzzle) throw new AppError(404, 'Puzzle not found');

    return {
        id: puzzle.id,
        grid: puzzle.grid,
        difficulty: puzzle.difficulty,
        clueCount: puzzle.clueCount,
        createdAt: puzzle.createdAt.toISOString(),
    };
}

// ─── Get Puzzle With Solution (internal) ──────────────────────────────────────

export async function getPuzzleWithSolution(id: string) {
    const puzzle = await prisma.puzzle.findUnique({ where: { id } });
    if (!puzzle) throw new AppError(404, 'Puzzle not found');
    return puzzle;
}
