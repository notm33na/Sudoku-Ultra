import { Difficulty } from '@sudoku-ultra/shared-types';
import { generatePuzzle as engineGenerate } from '@sudoku-ultra/sudoku-engine';
import { prisma } from '../prisma/client';
import { AppError } from '../middleware/errorHandler';

// ─── Get Today's Daily Puzzle ─────────────────────────────────────────────────

export async function getDailyPuzzle() {
    const today = new Date();
    today.setHours(0, 0, 0, 0);

    // Check if today's daily puzzle already exists
    let daily = await prisma.dailyPuzzle.findUnique({ where: { date: today } });

    if (!daily) {
        // Generate one — rotate difficulty by day of week
        const difficulties: Difficulty[] = [
            Difficulty.EASY,
            Difficulty.MEDIUM,
            Difficulty.HARD,
            Difficulty.MEDIUM,
            Difficulty.EXPERT,
            Difficulty.HARD,
            Difficulty.EASY,
        ];
        const dayOfWeek = today.getDay();
        const difficulty = difficulties[dayOfWeek];

        const puzzle = engineGenerate(difficulty);

        const saved = await prisma.puzzle.create({
            data: {
                grid: JSON.parse(JSON.stringify(puzzle.grid)),
                solution: JSON.parse(JSON.stringify(puzzle.solution)),
                difficulty: puzzle.difficulty,
                clueCount: puzzle.clueCount,
            },
        });

        daily = await prisma.dailyPuzzle.create({
            data: {
                puzzleId: saved.id,
                date: today,
                difficulty: puzzle.difficulty,
            },
        });
    }

    const puzzle = await prisma.puzzle.findUnique({ where: { id: daily.puzzleId } });
    if (!puzzle) throw new AppError(500, 'Daily puzzle data inconsistency');

    return {
        id: daily.id,
        puzzleId: puzzle.id,
        date: today.toISOString().split('T')[0],
        difficulty: daily.difficulty,
        grid: puzzle.grid,
        clueCount: puzzle.clueCount,
    };
}
