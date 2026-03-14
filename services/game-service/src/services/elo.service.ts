/**
 * elo.service.ts — Pure Elo rating computation.
 *
 * K-factor brackets:
 *   < 1400  → K = 32  (new / developing players)
 *   < 1800  → K = 24  (intermediate)
 *   ≥ 1800  → K = 16  (established / expert)
 *
 * Starting rating: 1200 (set at PlayerRating creation in Prisma).
 * Rating floor: 100 (no player can go below this).
 */

export interface EloResult {
    /** Winner's rating before the match. */
    winnerBefore: number;
    /** Winner's new rating after the match. */
    winnerAfter: number;
    /** Loser's rating before the match. */
    loserBefore: number;
    /** Loser's new rating after the match (≥ 100). */
    loserAfter: number;
    /** Rating points gained by the winner (= winnerAfter - winnerBefore). */
    delta: number;
}

const ELO_FLOOR = 100;

function kFactor(rating: number): number {
    if (rating < 1400) return 32;
    if (rating < 1800) return 24;
    return 16;
}

/**
 * Expected score for player A against player B.
 * Returns a value in (0, 1).
 */
export function expectedScore(ratingA: number, ratingB: number): number {
    return 1 / (1 + Math.pow(10, (ratingB - ratingA) / 400));
}

/**
 * Compute new Elo ratings after a decisive match (win/loss, no draws).
 *
 * @param winnerRating  Current Elo of the winner.
 * @param loserRating   Current Elo of the loser.
 * @returns             New ratings and delta for both players.
 */
export function computeElo(winnerRating: number, loserRating: number): EloResult {
    const ew = expectedScore(winnerRating, loserRating);
    const el = expectedScore(loserRating, winnerRating);

    const kw = kFactor(winnerRating);
    const kl = kFactor(loserRating);

    // Minimum gain of 1 for a win prevents the oddity of a 0-delta victory
    // when the winner is extremely heavily favoured (e.g. 2000 vs 800).
    const winnerAfter = Math.max(winnerRating + 1, Math.round(winnerRating + kw * (1 - ew)));
    const loserAfterRaw = Math.round(loserRating + kl * (0 - el));
    const loserAfter = Math.max(ELO_FLOOR, loserAfterRaw);

    return {
        winnerBefore: winnerRating,
        winnerAfter,
        loserBefore: loserRating,
        loserAfter,
        delta: winnerAfter - winnerRating,
    };
}
