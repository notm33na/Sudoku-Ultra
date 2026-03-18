/**
 * ActivityFeedScreen — infinite-scroll social feed.
 *
 * Shows the authenticated user's feed: their own actions + friends' actions,
 * ordered by newest first. Cursor-based pagination via "Load more" button.
 */

import React, { useCallback, useEffect, useState } from 'react';
import {
    ActivityIndicator,
    Pressable,
    RefreshControl,
    SafeAreaView,
    ScrollView,
    StyleSheet,
    Text,
    View,
} from 'react-native';
import { ActivityFeedScreenProps } from '../types/navigation';
import { colors } from '../theme/colors';

const API_BASE = process.env.EXPO_PUBLIC_API_URL ?? 'http://localhost:3001';
const API_TOKEN = process.env.EXPO_PUBLIC_API_TOKEN ?? '';

function authHeaders(): Record<string, string> {
    const h: Record<string, string> = { 'Content-Type': 'application/json' };
    if (API_TOKEN) h['Authorization'] = `Bearer ${API_TOKEN}`;
    return h;
}

// ─── Types ────────────────────────────────────────────────────────────────────

type ActivityType = 'puzzle_completed' | 'badge_earned' | 'lesson_completed' | 'friend_added';

interface ActivityEntry {
    id: string;
    actorId: string;
    actorUsername: string;
    actorAvatarUrl: string | null;
    type: ActivityType;
    payload: Record<string, unknown>;
    createdAt: string;
}

// ─── Activity icon & text helpers ─────────────────────────────────────────────

function activityIcon(type: ActivityType): string {
    switch (type) {
        case 'puzzle_completed':  return '🧩';
        case 'badge_earned':      return '🏅';
        case 'lesson_completed':  return '🎓';
        case 'friend_added':      return '👥';
    }
}

function activityText(entry: ActivityEntry): string {
    const { type, payload, actorUsername } = entry;
    switch (type) {
        case 'puzzle_completed': {
            const diff = (payload.difficulty as string | undefined) ?? 'a';
            const score = payload.score as number | undefined;
            return `${actorUsername} completed a ${diff.replace(/_/g, ' ')} puzzle${score !== undefined ? ` (${score} pts)` : ''}.`;
        }
        case 'badge_earned': {
            const icon = (payload.badgeIcon as string | undefined) ?? '🏅';
            const title = (payload.badgeTitle as string | undefined) ?? 'badge';
            return `${actorUsername} earned the ${icon} ${title} badge!`;
        }
        case 'lesson_completed': {
            const title = (payload.lessonTitle as string | undefined) ?? 'a lesson';
            const xp = payload.xpAwarded as number | undefined;
            return `${actorUsername} completed "${title}"${xp ? ` (+${xp} XP)` : ''}.`;
        }
        case 'friend_added': {
            return `${actorUsername} made a new friend.`;
        }
    }
}

function timeAgo(isoStr: string): string {
    const diff = Date.now() - new Date(isoStr).getTime();
    const mins = Math.floor(diff / 60000);
    if (mins < 1) return 'just now';
    if (mins < 60) return `${mins}m ago`;
    const hrs = Math.floor(mins / 60);
    if (hrs < 24) return `${hrs}h ago`;
    const days = Math.floor(hrs / 24);
    return `${days}d ago`;
}

// ─── Component ────────────────────────────────────────────────────────────────

export default function ActivityFeedScreen({ navigation: _navigation }: ActivityFeedScreenProps) {
    const [entries, setEntries] = useState<ActivityEntry[]>([]);
    const [cursor, setCursor] = useState<string | null>(null);
    const [hasMore, setHasMore] = useState(false);
    const [loading, setLoading] = useState(true);
    const [loadingMore, setLoadingMore] = useState(false);
    const [refreshing, setRefreshing] = useState(false);

    const fetchFeed = useCallback(async (fromCursor?: string) => {
        const url = new URL(`${API_BASE}/api/friends/feed`);
        url.searchParams.set('limit', '20');
        if (fromCursor) url.searchParams.set('cursor', fromCursor);

        const res = await fetch(url.toString(), { headers: authHeaders() });
        if (!res.ok) return;
        const body = await res.json();
        return body as { entries: ActivityEntry[]; nextCursor: string | null };
    }, []);

    useEffect(() => {
        fetchFeed()
            .then((data) => {
                if (!data) return;
                setEntries(data.entries);
                setCursor(data.nextCursor);
                setHasMore(data.nextCursor !== null);
            })
            .finally(() => setLoading(false));
    }, [fetchFeed]);

    const onRefresh = useCallback(async () => {
        setRefreshing(true);
        const data = await fetchFeed();
        if (data) {
            setEntries(data.entries);
            setCursor(data.nextCursor);
            setHasMore(data.nextCursor !== null);
        }
        setRefreshing(false);
    }, [fetchFeed]);

    const loadMore = useCallback(async () => {
        if (!cursor || loadingMore) return;
        setLoadingMore(true);
        const data = await fetchFeed(cursor);
        if (data) {
            setEntries((prev) => [...prev, ...data.entries]);
            setCursor(data.nextCursor);
            setHasMore(data.nextCursor !== null);
        }
        setLoadingMore(false);
    }, [cursor, loadingMore, fetchFeed]);

    if (loading) {
        return (
            <SafeAreaView style={[styles.container, styles.center]}>
                <ActivityIndicator size="large" color="#22d3ee" />
            </SafeAreaView>
        );
    }

    return (
        <SafeAreaView style={styles.container}>
            <ScrollView
                contentContainerStyle={styles.scroll}
                showsVerticalScrollIndicator={false}
                refreshControl={
                    <RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor="#22d3ee" />
                }
            >
                {entries.length === 0 ? (
                    <View style={styles.empty}>
                        <Text style={styles.emptyEmoji}>📭</Text>
                        <Text style={styles.emptyTitle}>Nothing here yet</Text>
                        <Text style={styles.emptySubtitle}>
                            Complete puzzles or lessons and add friends to see activity.
                        </Text>
                    </View>
                ) : (
                    entries.map((entry) => (
                        <View key={entry.id} style={styles.card}>
                            <View style={styles.iconBox}>
                                <Text style={styles.icon}>{activityIcon(entry.type)}</Text>
                            </View>
                            <View style={styles.cardBody}>
                                <Text style={styles.cardText}>{activityText(entry)}</Text>
                                <Text style={styles.cardTime}>{timeAgo(entry.createdAt)}</Text>
                            </View>
                        </View>
                    ))
                )}

                {hasMore && (
                    <Pressable
                        style={({ pressed }) => [styles.loadMoreBtn, pressed && styles.pressed]}
                        onPress={loadMore}
                        disabled={loadingMore}
                    >
                        {loadingMore ? (
                            <ActivityIndicator size="small" color="#22d3ee" />
                        ) : (
                            <Text style={styles.loadMoreText}>Load more</Text>
                        )}
                    </Pressable>
                )}
            </ScrollView>
        </SafeAreaView>
    );
}

// ─── Styles ───────────────────────────────────────────────────────────────────

const CYAN = '#22d3ee';

const styles = StyleSheet.create({
    container: { flex: 1, backgroundColor: colors.surface.dark },
    center: { justifyContent: 'center', alignItems: 'center' },
    scroll: { paddingHorizontal: 20, paddingTop: 16, paddingBottom: 48 },
    pressed: { opacity: 0.75 },

    empty: { alignItems: 'center', paddingTop: 80 },
    emptyEmoji: { fontSize: 48, marginBottom: 16 },
    emptyTitle: { color: colors.text.primary, fontSize: 18, fontWeight: '700', marginBottom: 8 },
    emptySubtitle: {
        color: colors.text.muted,
        fontSize: 13,
        textAlign: 'center',
        lineHeight: 20,
        paddingHorizontal: 24,
    },

    card: {
        flexDirection: 'row',
        backgroundColor: colors.surface.darkAlt,
        borderRadius: 12,
        padding: 14,
        marginBottom: 10,
        borderWidth: 1,
        borderColor: colors.grid.cellBorder,
        gap: 12,
        alignItems: 'flex-start',
    },
    iconBox: {
        width: 40,
        height: 40,
        borderRadius: 20,
        backgroundColor: 'rgba(34,211,238,0.1)',
        alignItems: 'center',
        justifyContent: 'center',
    },
    icon: { fontSize: 20 },
    cardBody: { flex: 1 },
    cardText: { color: colors.text.primary, fontSize: 14, lineHeight: 20 },
    cardTime: { color: colors.text.muted, fontSize: 12, marginTop: 4 },

    loadMoreBtn: {
        marginTop: 8,
        paddingVertical: 14,
        alignItems: 'center',
        borderRadius: 12,
        borderWidth: 1,
        borderColor: 'rgba(34,211,238,0.3)',
        backgroundColor: 'rgba(34,211,238,0.05)',
    },
    loadMoreText: { color: CYAN, fontWeight: '600', fontSize: 14 },
});
