/**
 * elo.service.test.ts — Unit tests for pure Elo rating computation.
 * No database or Redis required.
 */

import { computeElo, expectedScore } from '../services/elo.service';

describe('expectedScore', () => {
    it('returns 0.5 for equal ratings', () => {
        expect(expectedScore(1200, 1200)).toBeCloseTo(0.5);
    });

    it('returns > 0.5 for higher-rated player', () => {
        expect(expectedScore(1500, 1200)).toBeGreaterThan(0.5);
    });

    it('returns < 0.5 for lower-rated player', () => {
        expect(expectedScore(1200, 1500)).toBeLessThan(0.5);
    });

    it('sums to 1 for both players', () => {
        const ea = expectedScore(1400, 1600);
        const eb = expectedScore(1600, 1400);
        expect(ea + eb).toBeCloseTo(1.0);
    });
});

describe('computeElo', () => {
    it('winner gains rating and loser loses rating', () => {
        const result = computeElo(1200, 1200);
        expect(result.winnerAfter).toBeGreaterThan(result.winnerBefore);
        expect(result.loserAfter).toBeLessThan(result.loserBefore);
    });

    it('winner gains more points when defeating a higher-rated opponent', () => {
        const upsetResult = computeElo(1200, 1600);  // upset: low beats high
        const normalResult = computeElo(1600, 1200); // favourite beats low
        expect(upsetResult.delta).toBeGreaterThan(normalResult.delta);
    });

    it('preserves before-ratings in result', () => {
        const result = computeElo(1400, 1600);
        expect(result.winnerBefore).toBe(1400);
        expect(result.loserBefore).toBe(1600);
    });

    it('delta equals winnerAfter - winnerBefore', () => {
        const result = computeElo(1350, 1400);
        expect(result.delta).toBe(result.winnerAfter - result.winnerBefore);
    });

    it('loser rating never drops below floor (100)', () => {
        // Extreme case: 100-rated player loses to 2000-rated
        const result = computeElo(2000, 100);
        expect(result.loserAfter).toBeGreaterThanOrEqual(100);
    });

    it('uses K=32 for ratings below 1400', () => {
        const result = computeElo(1300, 1300);
        // Equal ratings → E=0.5, K=32 → delta = round(32 * 0.5) = 16
        expect(result.delta).toBe(16);
    });

    it('uses K=24 for ratings in 1400–1799 bracket', () => {
        const result = computeElo(1600, 1600);
        // Equal ratings → E=0.5, K=24 → delta = round(24 * 0.5) = 12
        expect(result.delta).toBe(12);
    });

    it('uses K=16 for ratings at or above 1800', () => {
        const result = computeElo(1900, 1900);
        // Equal ratings → E=0.5, K=16 → delta = round(16 * 0.5) = 8
        expect(result.delta).toBe(8);
    });

    it('winner delta is positive for any win', () => {
        const cases = [
            [800, 2000],
            [1200, 1200],
            [2000, 800],
        ] as [number, number][];
        for (const [w, l] of cases) {
            expect(computeElo(w, l).delta).toBeGreaterThan(0);
        }
    });

    it('loser delta is negative for any loss', () => {
        const result = computeElo(1500, 1500);
        const loserDelta = result.loserAfter - result.loserBefore;
        expect(loserDelta).toBeLessThan(0);
    });

    it('returns integer ratings', () => {
        const result = computeElo(1357, 1482);
        expect(Number.isInteger(result.winnerAfter)).toBe(true);
        expect(Number.isInteger(result.loserAfter)).toBe(true);
    });
});
