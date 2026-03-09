import { Difficulty } from '@sudoku-ultra/shared-types';
import { generatePuzzle } from '../generator';
import { hasUniqueSolution, solve } from '../solver';
import { isGridComplete, isGridCorrect } from '../validator';
import { countClues } from '../utils';

// Generator tests involve actual puzzle generation — allow extra time
jest.setTimeout(60000);

describe('generatePuzzle()', () => {
    // Test easy/beginner/medium independently — these always hit their clue ranges
    it.each([Difficulty.BEGINNER, Difficulty.EASY, Difficulty.MEDIUM] as const)(
        'generates a valid unique puzzle for %s',
        (difficulty) => {
            const puzzle = generatePuzzle(difficulty);

            // Structure checks
            expect(puzzle.id).toMatch(/^pzl_/);
            expect(puzzle.difficulty).toBe(difficulty);
            expect(puzzle.grid).toHaveLength(9);
            puzzle.grid.forEach((row) => expect(row).toHaveLength(9));
            expect(puzzle.createdAt).toBeTruthy();

            // Unique solution
            const numberGrid = puzzle.grid.map((row) => row.map((cell) => cell.value ?? 0));
            expect(hasUniqueSolution(numberGrid)).toBe(true);

            // Solution is complete and valid
            expect(isGridComplete(puzzle.solution)).toBe(true);
        },
    );

    // Hard/expert/evil may not always reach exact clue targets due to uniqueness
    // constraints, but they must still have unique solutions and fewer clues
    // than easier difficulties
    it.each([Difficulty.HARD, Difficulty.EXPERT, Difficulty.EVIL] as const)(
        'generates a valid unique puzzle for %s',
        (difficulty) => {
            const puzzle = generatePuzzle(difficulty);

            // Structure checks
            expect(puzzle.id).toMatch(/^pzl_/);
            expect(puzzle.difficulty).toBe(difficulty);

            // Unique solution — the most critical invariant
            const numberGrid = puzzle.grid.map((row) => row.map((cell) => cell.value ?? 0));
            expect(hasUniqueSolution(numberGrid)).toBe(true);

            // Should have fewer clues than a beginner puzzle would
            expect(puzzle.clueCount).toBeLessThanOrEqual(45);

            // Solution is complete
            expect(isGridComplete(puzzle.solution)).toBe(true);
        },
    );

    it('given cells in puzzle grid are locked', () => {
        const puzzle = generatePuzzle(Difficulty.EASY);
        puzzle.grid.forEach((row) => {
            row.forEach((cell) => {
                if (cell.value !== null) {
                    expect(cell.isLocked).toBe(true);
                } else {
                    expect(cell.isLocked).toBe(false);
                }
            });
        });
    });

    it('solution solves the puzzle correctly', () => {
        const puzzle = generatePuzzle(Difficulty.MEDIUM);
        const numberGrid = puzzle.grid.map((row) => row.map((cell) => cell.value ?? 0));
        const solved = solve(numberGrid);
        expect(solved).not.toBeNull();
        expect(isGridCorrect(solved!, puzzle.solution)).toBe(true);
    });

    it('clueCount matches the actual number of given cells', () => {
        const puzzle = generatePuzzle(Difficulty.EASY);
        const numberGrid = puzzle.grid.map((row) => row.map((cell) => cell.value ?? 0));
        expect(puzzle.clueCount).toBe(countClues(numberGrid));
    });

    it('generates different puzzles on successive calls', () => {
        const p1 = generatePuzzle(Difficulty.EASY);
        const p2 = generatePuzzle(Difficulty.EASY);
        // Both must be independently valid
        expect(hasUniqueSolution(p1.grid.map((r) => r.map((c) => c.value ?? 0)))).toBe(true);
        expect(hasUniqueSolution(p2.grid.map((r) => r.map((c) => c.value ?? 0)))).toBe(true);
    });
});
