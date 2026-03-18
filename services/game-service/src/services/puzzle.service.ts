import { Difficulty } from '@sudoku-ultra/shared-types';
import { generatePuzzle as engineGenerate } from '@sudoku-ultra/sudoku-engine';
import { prisma } from '../prisma/client';
import { AppError } from '../middleware/errorHandler';
import { config } from '../config';

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

// ─── Generate Puzzle via GAN ──────────────────────────────────────────────────

export type GanMode = 'solution' | 'puzzle' | 'constrained';

export async function generatePuzzleGAN(
    difficulty: string,
    mode: GanMode = 'puzzle',
    symmetric: boolean = false,
) {
    // Call ml-service GAN endpoint; fall back to engine on failure
    try {
        const res = await fetch(`${config.ML_SERVICE_URL}/api/v1/gan/generate`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ mode, difficulty, symmetric }),
            signal: AbortSignal.timeout(10_000),
        });
        if (!res.ok) throw new Error(`ml-service ${res.status}`);
        const data: {
            puzzle: {
                solution: number[];
                puzzle: number[] | null;
                difficulty: string;
                clue_count: number;
                source: string;
            };
        } = await res.json();

        const { solution, puzzle: puzzleGrid, difficulty: diff, clue_count, source } = data.puzzle;

        // Convert flat 81-int arrays to Cell[][] (value, given, notes)
        const toGrid = (flat: number[]) =>
            Array.from({ length: 9 }, (_, r) =>
                Array.from({ length: 9 }, (_, c) => ({
                    value: flat[r * 9 + c] || null,
                    given: flat[r * 9 + c] !== 0,
                    notes: [] as number[],
                })),
            );

        const gridForDb = puzzleGrid ?? solution;
        const solutionGrid = solution;

        const saved = await prisma.puzzle.create({
            data: {
                grid: toGrid(gridForDb) as any,
                solution: toGrid(solutionGrid) as any,
                difficulty: diff,
                clueCount: mode === 'solution' ? 81 : clue_count,
            },
        });

        return {
            id: saved.id,
            grid: saved.grid,
            difficulty: saved.difficulty,
            clueCount: saved.clueCount,
            source,
            createdAt: saved.createdAt.toISOString(),
        };
    } catch {
        // Fallback to engine
        return generatePuzzle(difficulty);
    }
}

// ─── Get Puzzle With Solution (internal) ──────────────────────────────────────

export async function getPuzzleWithSolution(id: string) {
    const puzzle = await prisma.puzzle.findUnique({ where: { id } });
    if (!puzzle) throw new AppError(404, 'Puzzle not found');
    return puzzle;
}
