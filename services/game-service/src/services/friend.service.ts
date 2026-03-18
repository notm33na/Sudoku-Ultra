/**
 * friend.service.ts — Friends system and activity feed.
 *
 * Friendship lifecycle:
 *   send request → pending
 *   accept        → accepted  (bi-directional lookup via OR query)
 *   decline       → declined
 *   block         → blocked
 *
 * Activity feed:
 *   emitActivity() is called by session, lesson, and friend services.
 *   Feed entries are written for the actor AND fanned out to all accepted friends,
 *   so each user's feed contains their own actions + friends' actions.
 */

import { prisma } from '../prisma/client';

// ── Types ──────────────────────────────────────────────────────────────────────

export type FriendStatus = 'pending' | 'accepted' | 'declined' | 'blocked';

export type ActivityType =
    | 'puzzle_completed'
    | 'badge_earned'
    | 'lesson_completed'
    | 'friend_added';

export interface FriendEntry {
    userId: string;
    username: string;
    avatarUrl: string | null;
    friendshipId: string;
    since: string;
    eloRating: number | null;
}

export interface PendingRequest {
    friendshipId: string;
    from: {
        userId: string;
        username: string;
        avatarUrl: string | null;
    };
    createdAt: string;
}

export interface ActivityEntry {
    id: string;
    actorId: string;
    actorUsername: string;
    actorAvatarUrl: string | null;
    type: ActivityType;
    payload: Record<string, unknown>;
    createdAt: string;
}

export interface FriendLeaderboardEntry {
    rank: number;
    userId: string;
    username: string;
    avatarUrl: string | null;
    eloRating: number;
    wins: number;
    losses: number;
    winRate: number;
    isMe: boolean;
}

// ── Send Friend Request ────────────────────────────────────────────────────────

export async function sendFriendRequest(
    requesterId: string,
    addresseeId: string,
): Promise<{ friendshipId: string; status: string }> {
    if (requesterId === addresseeId) {
        throw Object.assign(new Error('Cannot add yourself.'), { statusCode: 400 });
    }

    // Check for existing relationship in either direction.
    const existing = await prisma.friendship.findFirst({
        where: {
            OR: [
                { requesterId, addresseeId },
                { requesterId: addresseeId, addresseeId: requesterId },
            ],
        },
    });

    if (existing) {
        if (existing.status === 'blocked') {
            throw Object.assign(new Error('Cannot send request.'), { statusCode: 403 });
        }
        if (existing.status === 'accepted') {
            throw Object.assign(new Error('Already friends.'), { statusCode: 409 });
        }
        if (existing.status === 'pending') {
            throw Object.assign(new Error('Request already sent.'), { statusCode: 409 });
        }
        // declined → re-open
        const updated = await prisma.friendship.update({
            where: { id: existing.id },
            data: { status: 'pending', requesterId, addresseeId },
        });
        return { friendshipId: updated.id, status: updated.status };
    }

    const addressee = await prisma.user.findUnique({ where: { id: addresseeId } });
    if (!addressee) {
        throw Object.assign(new Error('User not found.'), { statusCode: 404 });
    }

    const friendship = await prisma.friendship.create({
        data: { requesterId, addresseeId, status: 'pending' },
    });
    return { friendshipId: friendship.id, status: friendship.status };
}

// ── Accept ─────────────────────────────────────────────────────────────────────

export async function acceptFriendRequest(
    friendshipId: string,
    currentUserId: string,
): Promise<void> {
    const friendship = await prisma.friendship.findUnique({ where: { id: friendshipId } });
    if (!friendship || friendship.status !== 'pending') {
        throw Object.assign(new Error('Request not found or already resolved.'), { statusCode: 404 });
    }
    if (friendship.addresseeId !== currentUserId) {
        throw Object.assign(new Error('Not the addressee of this request.'), { statusCode: 403 });
    }

    await prisma.friendship.update({
        where: { id: friendshipId },
        data: { status: 'accepted' },
    });

    // Emit activity to both sides.
    await Promise.all([
        emitActivity(friendship.requesterId, friendship.addresseeId, 'friend_added', {
            friendId: currentUserId,
        }),
        emitActivity(currentUserId, currentUserId, 'friend_added', {
            friendId: friendship.requesterId,
        }),
    ]);
}

// ── Decline ────────────────────────────────────────────────────────────────────

export async function declineFriendRequest(
    friendshipId: string,
    currentUserId: string,
): Promise<void> {
    const friendship = await prisma.friendship.findUnique({ where: { id: friendshipId } });
    if (!friendship || friendship.status !== 'pending') {
        throw Object.assign(new Error('Request not found or already resolved.'), { statusCode: 404 });
    }
    if (friendship.addresseeId !== currentUserId) {
        throw Object.assign(new Error('Not the addressee of this request.'), { statusCode: 403 });
    }
    await prisma.friendship.update({
        where: { id: friendshipId },
        data: { status: 'declined' },
    });
}

// ── Block ──────────────────────────────────────────────────────────────────────

export async function blockUser(
    blockerId: string,
    targetId: string,
): Promise<void> {
    if (blockerId === targetId) {
        throw Object.assign(new Error('Cannot block yourself.'), { statusCode: 400 });
    }
    const existing = await prisma.friendship.findFirst({
        where: {
            OR: [
                { requesterId: blockerId, addresseeId: targetId },
                { requesterId: targetId, addresseeId: blockerId },
            ],
        },
    });

    if (existing) {
        await prisma.friendship.update({
            where: { id: existing.id },
            data: { status: 'blocked', requesterId: blockerId, addresseeId: targetId },
        });
    } else {
        await prisma.friendship.create({
            data: { requesterId: blockerId, addresseeId: targetId, status: 'blocked' },
        });
    }
}

// ── List Friends ───────────────────────────────────────────────────────────────

export async function listFriends(userId: string): Promise<FriendEntry[]> {
    const friendships = await prisma.friendship.findMany({
        where: {
            OR: [
                { requesterId: userId, status: 'accepted' },
                { addresseeId: userId, status: 'accepted' },
            ],
        },
        orderBy: { updatedAt: 'desc' },
    });

    const friendIds = friendships.map((f) =>
        f.requesterId === userId ? f.addresseeId : f.requesterId,
    );

    if (friendIds.length === 0) return [];

    const [users, ratings] = await Promise.all([
        prisma.user.findMany({
            where: { id: { in: friendIds } },
            select: { id: true, username: true, avatarUrl: true },
        }),
        prisma.playerRating.findMany({
            where: { userId: { in: friendIds } },
            select: { userId: true, eloRating: true },
        }),
    ]);

    const userMap = new Map(users.map((u) => [u.id, u]));
    const ratingMap = new Map(ratings.map((r) => [r.userId, r.eloRating]));

    return friendships
        .map((f) => {
            const friendId = f.requesterId === userId ? f.addresseeId : f.requesterId;
            const user = userMap.get(friendId);
            if (!user) return null;
            return {
                userId: friendId,
                username: user.username,
                avatarUrl: user.avatarUrl,
                friendshipId: f.id,
                since: f.updatedAt.toISOString(),
                eloRating: ratingMap.get(friendId) ?? null,
            };
        })
        .filter((e): e is FriendEntry => e !== null);
}

// ── Pending Requests (incoming) ────────────────────────────────────────────────

export async function listPendingRequests(userId: string): Promise<PendingRequest[]> {
    const friendships = await prisma.friendship.findMany({
        where: { addresseeId: userId, status: 'pending' },
        orderBy: { createdAt: 'desc' },
        include: {
            requester: { select: { id: true, username: true, avatarUrl: true } },
        },
    });

    return friendships.map((f) => ({
        friendshipId: f.id,
        from: {
            userId: f.requester.id,
            username: f.requester.username,
            avatarUrl: f.requester.avatarUrl,
        },
        createdAt: f.createdAt.toISOString(),
    }));
}

// ── Activity Feed ──────────────────────────────────────────────────────────────

/**
 * Emit an activity event for `actorId`.
 * Writes one entry per friend (fan-out) + one for the actor themselves.
 * Fire-and-forget safe — callers may `.catch(() => null)`.
 */
export async function emitActivity(
    ownerId: string,
    actorId: string,
    type: ActivityType,
    payload: Record<string, unknown> = {},
): Promise<void> {
    // Resolve accepted friends of the actor to fan out to their feeds.
    const friendships = await prisma.friendship.findMany({
        where: {
            OR: [
                { requesterId: actorId, status: 'accepted' },
                { addresseeId: actorId, status: 'accepted' },
            ],
            // Don't double-write if ownerId is already the actor.
        },
    });

    const audienceIds = new Set<string>([ownerId]);
    for (const f of friendships) {
        const friendId = f.requesterId === actorId ? f.addresseeId : f.requesterId;
        audienceIds.add(friendId);
    }

    await prisma.activityFeed.createMany({
        data: Array.from(audienceIds).map((uid) => ({
            userId: uid,
            actorId,
            type,
            payload,
        })),
        skipDuplicates: true,
    });
}

export async function getActivityFeed(
    userId: string,
    limit = 30,
    cursor?: string,
): Promise<{ entries: ActivityEntry[]; nextCursor: string | null }> {
    const take = Math.min(limit, 50);
    const where = cursor
        ? { userId, createdAt: { lt: new Date(cursor) } }
        : { userId };

    const rows = await prisma.activityFeed.findMany({
        where,
        orderBy: { createdAt: 'desc' },
        take: take + 1,
        include: {
            actor: { select: { id: true, username: true, avatarUrl: true } },
        },
    });

    const hasMore = rows.length > take;
    const items = hasMore ? rows.slice(0, take) : rows;

    const entries: ActivityEntry[] = items.map((r) => ({
        id: r.id,
        actorId: r.actor.id,
        actorUsername: r.actor.username,
        actorAvatarUrl: r.actor.avatarUrl,
        type: r.type as ActivityType,
        payload: r.payload as Record<string, unknown>,
        createdAt: r.createdAt.toISOString(),
    }));

    const nextCursor = hasMore ? items[items.length - 1].createdAt.toISOString() : null;
    return { entries, nextCursor };
}

// ── Friends Leaderboard (weekly score, falls back to Elo) ─────────────────────

export async function getFriendsLeaderboard(userId: string): Promise<FriendLeaderboardEntry[]> {
    const friendships = await prisma.friendship.findMany({
        where: {
            OR: [
                { requesterId: userId, status: 'accepted' },
                { addresseeId: userId, status: 'accepted' },
            ],
        },
    });

    const friendIds = friendships.map((f) =>
        f.requesterId === userId ? f.addresseeId : f.requesterId,
    );
    const allIds = [userId, ...friendIds];

    const [users, ratings] = await Promise.all([
        prisma.user.findMany({
            where: { id: { in: allIds } },
            select: { id: true, username: true, avatarUrl: true },
        }),
        prisma.playerRating.findMany({
            where: { userId: { in: allIds } },
            select: { userId: true, eloRating: true, wins: true, losses: true },
        }),
    ]);

    const userMap = new Map(users.map((u) => [u.id, u]));
    const ratingMap = new Map(ratings.map((r) => [r.userId, r]));

    const entries = allIds
        .map((id) => {
            const user = userMap.get(id);
            const rating = ratingMap.get(id);
            if (!user) return null;
            const elo = rating?.eloRating ?? 1200;
            const wins = rating?.wins ?? 0;
            const losses = rating?.losses ?? 0;
            const total = wins + losses;
            return {
                rank: 0,
                userId: id,
                username: user.username,
                avatarUrl: user.avatarUrl,
                eloRating: elo,
                wins,
                losses,
                winRate: total > 0 ? wins / total : 0,
                isMe: id === userId,
            };
        })
        .filter((e): e is FriendLeaderboardEntry => e !== null)
        .sort((a, b) => b.eloRating - a.eloRating);

    entries.forEach((e, i) => { e.rank = i + 1; });
    return entries;
}
