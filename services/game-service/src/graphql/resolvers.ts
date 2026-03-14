/**
 * resolvers.ts — GraphQL resolver map for the leaderboard/rating API.
 */

import {
    getLeaderboard,
    getPlayerRating,
    getMatchHistory,
} from '../services/rating.service';

export const resolvers = {
    Query: {
        async leaderboard(
            _: unknown,
            args: { limit?: number; offset?: number },
        ) {
            const limit = Math.min(args.limit ?? 20, 100);
            const offset = Math.max(args.offset ?? 0, 0);
            return getLeaderboard(limit, offset);
        },

        async playerRating(_: unknown, args: { userId: string }) {
            return getPlayerRating(args.userId);
        },

        async matchHistory(
            _: unknown,
            args: { userId: string; limit?: number },
        ) {
            return getMatchHistory(args.userId, args.limit ?? 20);
        },
    },
};
