/**
 * schema.ts — GraphQL SDL type definitions for the Sudoku Ultra leaderboard API.
 */

export const typeDefs = `#graphql
  type Query {
    """Top-N global leaderboard sorted by Elo rating descending."""
    leaderboard(limit: Int, offset: Int): LeaderboardResult!

    """Current Elo profile for a single player."""
    playerRating(userId: String!): PlayerRating

    """Recent match history for a player (max 100)."""
    matchHistory(userId: String!, limit: Int): [MultiplayerMatch!]!
  }

  type LeaderboardResult {
    entries: [LeaderboardEntry!]!
    total: Int!
  }

  type LeaderboardEntry {
    rank: Int!
    userId: String!
    username: String!
    avatarUrl: String
    eloRating: Int!
    wins: Int!
    losses: Int!
    """Win rate as a value between 0 and 1."""
    winRate: Float!
  }

  type PlayerRating {
    userId: String!
    username: String!
    avatarUrl: String
    eloRating: Int!
    wins: Int!
    losses: Int!
    """Win rate as a value between 0 and 1."""
    winRate: Float!
    """1-based global rank, or null if not yet on the leaderboard."""
    rank: Int
    lastMatchAt: String
  }

  type MultiplayerMatch {
    id: String!
    roomId: String!
    winnerId: String!
    loserId: String!
    winnerEloBefore: Int!
    winnerEloAfter: Int!
    loserEloBefore: Int!
    loserEloAfter: Int!
    """Elo points gained by the winner (positive integer)."""
    eloDelta: Int!
    """completed | forfeit | timeout"""
    endReason: String!
    durationMs: Int!
    difficulty: String!
    createdAt: String!
  }
`;
