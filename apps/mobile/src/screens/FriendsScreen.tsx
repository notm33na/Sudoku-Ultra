/**
 * FriendsScreen — three-tab social hub.
 *
 * Tabs:
 *   Friends     — accepted friends list with Elo badges
 *   Requests    — incoming pending requests with accept / decline
 *   Leaderboard — friends + self ranked by Elo, self highlighted
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
    TextInput,
    View,
} from 'react-native';
import { FriendsScreenProps } from '../types/navigation';
import { colors } from '../theme/colors';

const API_BASE = process.env.EXPO_PUBLIC_API_URL ?? 'http://localhost:3001';
const API_TOKEN = process.env.EXPO_PUBLIC_API_TOKEN ?? '';

function authHeaders(): Record<string, string> {
    const h: Record<string, string> = { 'Content-Type': 'application/json' };
    if (API_TOKEN) h['Authorization'] = `Bearer ${API_TOKEN}`;
    return h;
}

// ─── Types ────────────────────────────────────────────────────────────────────

interface FriendEntry {
    userId: string;
    username: string;
    avatarUrl: string | null;
    friendshipId: string;
    since: string;
    eloRating: number | null;
}

interface PendingRequest {
    friendshipId: string;
    from: { userId: string; username: string; avatarUrl: string | null };
    createdAt: string;
}

interface LeaderboardEntry {
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

type Tab = 'friends' | 'requests' | 'leaderboard';

// ─── Component ────────────────────────────────────────────────────────────────

export default function FriendsScreen({ navigation }: FriendsScreenProps) {
    const [tab, setTab] = useState<Tab>('friends');
    const [friends, setFriends] = useState<FriendEntry[]>([]);
    const [requests, setRequests] = useState<PendingRequest[]>([]);
    const [leaderboard, setLeaderboard] = useState<LeaderboardEntry[]>([]);
    const [loading, setLoading] = useState(true);
    const [refreshing, setRefreshing] = useState(false);
    const [addUsername, setAddUsername] = useState('');
    const [addError, setAddError] = useState('');
    const [addSuccess, setAddSuccess] = useState('');
    const [addBusy, setAddBusy] = useState(false);

    const fetchAll = useCallback(async () => {
        const [fr, rq, lb] = await Promise.allSettled([
            fetch(`${API_BASE}/api/friends`, { headers: authHeaders() }).then((r) => r.json()),
            fetch(`${API_BASE}/api/friends/pending`, { headers: authHeaders() }).then((r) => r.json()),
            fetch(`${API_BASE}/api/friends/leaderboard`, { headers: authHeaders() }).then((r) => r.json()),
        ]);

        if (fr.status === 'fulfilled') setFriends(fr.value.friends ?? []);
        if (rq.status === 'fulfilled') setRequests(rq.value.requests ?? []);
        if (lb.status === 'fulfilled') setLeaderboard(lb.value.entries ?? []);
    }, []);

    useEffect(() => {
        fetchAll().finally(() => setLoading(false));
    }, [fetchAll]);

    const onRefresh = useCallback(async () => {
        setRefreshing(true);
        await fetchAll();
        setRefreshing(false);
    }, [fetchAll]);

    // ── Add friend by username ─────────────────────────────────────────────────

    const handleAddFriend = useCallback(async () => {
        const trimmed = addUsername.trim();
        if (!trimmed) return;
        setAddBusy(true);
        setAddError('');
        setAddSuccess('');
        try {
            // Resolve username → userId via auth search (fallback: direct UUID attempt)
            // The game-service does not have a user-search endpoint yet, so we send
            // the raw input as addresseeId and surface the error if it's not a UUID.
            const res = await fetch(`${API_BASE}/api/friends/request`, {
                method: 'POST',
                headers: authHeaders(),
                body: JSON.stringify({ addresseeId: trimmed }),
            });
            if (res.ok) {
                setAddSuccess('Friend request sent!');
                setAddUsername('');
                fetchAll();
            } else {
                const body = await res.json();
                setAddError(body.error ?? 'Could not send request.');
            }
        } catch {
            setAddError('Network error. Try again.');
        } finally {
            setAddBusy(false);
        }
    }, [addUsername, fetchAll]);

    // ── Accept / Decline ───────────────────────────────────────────────────────

    const respond = useCallback(
        async (friendshipId: string, action: 'accept' | 'decline') => {
            await fetch(`${API_BASE}/api/friends/${friendshipId}/${action}`, {
                method: 'POST',
                headers: authHeaders(),
            });
            fetchAll();
        },
        [fetchAll],
    );

    if (loading) {
        return (
            <SafeAreaView style={[styles.container, styles.center]}>
                <ActivityIndicator size="large" color="#22d3ee" />
            </SafeAreaView>
        );
    }

    return (
        <SafeAreaView style={styles.container}>
            {/* ── Tab bar ─────────────────────────────────────────────────── */}
            <View style={styles.tabBar}>
                {(['friends', 'requests', 'leaderboard'] as Tab[]).map((t) => (
                    <Pressable
                        key={t}
                        style={[styles.tab, tab === t && styles.tabActive]}
                        onPress={() => setTab(t)}
                    >
                        <Text style={[styles.tabText, tab === t && styles.tabTextActive]}>
                            {t === 'friends' && `Friends${friends.length ? ` (${friends.length})` : ''}`}
                            {t === 'requests' && `Requests${requests.length ? ` (${requests.length})` : ''}`}
                            {t === 'leaderboard' && 'Leaderboard'}
                        </Text>
                    </Pressable>
                ))}
            </View>

            <ScrollView
                contentContainerStyle={styles.scroll}
                showsVerticalScrollIndicator={false}
                refreshControl={
                    <RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor="#22d3ee" />
                }
            >
                {/* ── Add friend ────────────────────────────────────────────── */}
                {tab === 'friends' && (
                    <View style={styles.addRow}>
                        <TextInput
                            style={styles.addInput}
                            placeholder="User ID to add..."
                            placeholderTextColor={colors.text.muted}
                            value={addUsername}
                            onChangeText={(v) => { setAddUsername(v); setAddError(''); setAddSuccess(''); }}
                            autoCapitalize="none"
                        />
                        <Pressable
                            style={({ pressed }) => [styles.addButton, pressed && styles.pressed]}
                            onPress={handleAddFriend}
                            disabled={addBusy}
                        >
                            {addBusy ? (
                                <ActivityIndicator size="small" color="#fff" />
                            ) : (
                                <Text style={styles.addButtonText}>Add</Text>
                            )}
                        </Pressable>
                    </View>
                )}
                {addError ? <Text style={styles.errorText}>{addError}</Text> : null}
                {addSuccess ? <Text style={styles.successText}>{addSuccess}</Text> : null}

                {/* ── Friends list ──────────────────────────────────────────── */}
                {tab === 'friends' && (
                    <>
                        {friends.length === 0 ? (
                            <Text style={styles.emptyText}>No friends yet. Add one above.</Text>
                        ) : (
                            friends.map((f) => (
                                <View key={f.friendshipId} style={styles.card}>
                                    <View style={styles.avatar}>
                                        <Text style={styles.avatarLetter}>
                                            {f.username[0].toUpperCase()}
                                        </Text>
                                    </View>
                                    <View style={styles.cardInfo}>
                                        <Text style={styles.cardName}>{f.username}</Text>
                                        <Text style={styles.cardSub}>
                                            Friends since {new Date(f.since).toLocaleDateString()}
                                        </Text>
                                    </View>
                                    {f.eloRating !== null && (
                                        <View style={styles.eloBadge}>
                                            <Text style={styles.eloText}>{f.eloRating}</Text>
                                            <Text style={styles.eloLabel}>Elo</Text>
                                        </View>
                                    )}
                                </View>
                            ))
                        )}

                        {/* Activity feed shortcut */}
                        {friends.length > 0 && (
                            <Pressable
                                style={({ pressed }) => [styles.feedButton, pressed && styles.pressed]}
                                onPress={() => navigation.navigate('ActivityFeed')}
                            >
                                <Text style={styles.feedButtonText}>📜  View Activity Feed</Text>
                            </Pressable>
                        )}
                    </>
                )}

                {/* ── Pending requests ──────────────────────────────────────── */}
                {tab === 'requests' && (
                    <>
                        {requests.length === 0 ? (
                            <Text style={styles.emptyText}>No pending requests.</Text>
                        ) : (
                            requests.map((r) => (
                                <View key={r.friendshipId} style={styles.card}>
                                    <View style={styles.avatar}>
                                        <Text style={styles.avatarLetter}>
                                            {r.from.username[0].toUpperCase()}
                                        </Text>
                                    </View>
                                    <View style={styles.cardInfo}>
                                        <Text style={styles.cardName}>{r.from.username}</Text>
                                        <Text style={styles.cardSub}>
                                            {new Date(r.createdAt).toLocaleDateString()}
                                        </Text>
                                    </View>
                                    <View style={styles.requestActions}>
                                        <Pressable
                                            style={({ pressed }) => [styles.acceptBtn, pressed && styles.pressed]}
                                            onPress={() => respond(r.friendshipId, 'accept')}
                                        >
                                            <Text style={styles.acceptBtnText}>Accept</Text>
                                        </Pressable>
                                        <Pressable
                                            style={({ pressed }) => [styles.declineBtn, pressed && styles.pressed]}
                                            onPress={() => respond(r.friendshipId, 'decline')}
                                        >
                                            <Text style={styles.declineBtnText}>Decline</Text>
                                        </Pressable>
                                    </View>
                                </View>
                            ))
                        )}
                    </>
                )}

                {/* ── Leaderboard ───────────────────────────────────────────── */}
                {tab === 'leaderboard' && (
                    <>
                        {leaderboard.length === 0 ? (
                            <Text style={styles.emptyText}>Add friends to see the leaderboard.</Text>
                        ) : (
                            leaderboard.map((e) => (
                                <View
                                    key={e.userId}
                                    style={[styles.lbRow, e.isMe && styles.lbRowMe]}
                                >
                                    <Text style={[styles.lbRank, e.rank <= 3 && styles.lbRankTop]}>
                                        {e.rank === 1 ? '🥇' : e.rank === 2 ? '🥈' : e.rank === 3 ? '🥉' : `#${e.rank}`}
                                    </Text>
                                    <View style={styles.avatar}>
                                        <Text style={styles.avatarLetter}>
                                            {e.username[0].toUpperCase()}
                                        </Text>
                                    </View>
                                    <View style={styles.cardInfo}>
                                        <Text style={[styles.cardName, e.isMe && styles.lbNameMe]}>
                                            {e.username}{e.isMe ? ' (you)' : ''}
                                        </Text>
                                        <Text style={styles.cardSub}>
                                            {e.wins}W · {e.losses}L · {(e.winRate * 100).toFixed(0)}% WR
                                        </Text>
                                    </View>
                                    <View style={styles.eloBadge}>
                                        <Text style={styles.eloText}>{e.eloRating}</Text>
                                        <Text style={styles.eloLabel}>Elo</Text>
                                    </View>
                                </View>
                            ))
                        )}
                    </>
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

    tabBar: {
        flexDirection: 'row',
        backgroundColor: colors.surface.darkAlt,
        borderBottomWidth: 1,
        borderBottomColor: colors.grid.cellBorder,
    },
    tab: {
        flex: 1,
        paddingVertical: 12,
        alignItems: 'center',
    },
    tabActive: {
        borderBottomWidth: 2,
        borderBottomColor: CYAN,
    },
    tabText: {
        fontSize: 13,
        fontWeight: '600',
        color: colors.text.muted,
    },
    tabTextActive: {
        color: CYAN,
    },

    // Add friend row
    addRow: {
        flexDirection: 'row',
        gap: 10,
        marginBottom: 8,
    },
    addInput: {
        flex: 1,
        backgroundColor: colors.surface.darkAlt,
        borderRadius: 10,
        paddingHorizontal: 14,
        paddingVertical: 10,
        color: colors.text.primary,
        fontSize: 14,
        borderWidth: 1,
        borderColor: colors.grid.cellBorder,
    },
    addButton: {
        backgroundColor: CYAN,
        borderRadius: 10,
        paddingHorizontal: 18,
        justifyContent: 'center',
    },
    addButtonText: {
        color: '#000',
        fontWeight: '700',
        fontSize: 14,
    },
    errorText: { color: '#f87171', fontSize: 12, marginBottom: 8 },
    successText: { color: '#4ade80', fontSize: 12, marginBottom: 8 },

    emptyText: {
        color: colors.text.muted,
        textAlign: 'center',
        marginTop: 40,
        fontSize: 14,
    },

    // Card
    card: {
        flexDirection: 'row',
        alignItems: 'center',
        backgroundColor: colors.surface.darkAlt,
        borderRadius: 12,
        padding: 14,
        marginBottom: 10,
        borderWidth: 1,
        borderColor: colors.grid.cellBorder,
        gap: 12,
    },
    avatar: {
        width: 42,
        height: 42,
        borderRadius: 21,
        backgroundColor: 'rgba(34,211,238,0.15)',
        borderWidth: 1,
        borderColor: CYAN,
        alignItems: 'center',
        justifyContent: 'center',
    },
    avatarLetter: {
        color: CYAN,
        fontWeight: '700',
        fontSize: 18,
    },
    cardInfo: { flex: 1 },
    cardName: { color: colors.text.primary, fontWeight: '600', fontSize: 15 },
    cardSub: { color: colors.text.muted, fontSize: 12, marginTop: 2 },

    // Elo badge
    eloBadge: {
        alignItems: 'center',
        backgroundColor: 'rgba(34,211,238,0.08)',
        borderRadius: 8,
        paddingHorizontal: 10,
        paddingVertical: 6,
        borderWidth: 1,
        borderColor: 'rgba(34,211,238,0.3)',
    },
    eloText: { color: CYAN, fontWeight: '800', fontSize: 16 },
    eloLabel: { color: colors.text.muted, fontSize: 10, marginTop: 1 },

    // Request actions
    requestActions: { flexDirection: 'row', gap: 8 },
    acceptBtn: {
        backgroundColor: '#22c55e',
        borderRadius: 8,
        paddingHorizontal: 12,
        paddingVertical: 6,
    },
    acceptBtnText: { color: '#fff', fontWeight: '700', fontSize: 13 },
    declineBtn: {
        backgroundColor: colors.surface.darkAlt,
        borderRadius: 8,
        paddingHorizontal: 12,
        paddingVertical: 6,
        borderWidth: 1,
        borderColor: '#f87171',
    },
    declineBtnText: { color: '#f87171', fontWeight: '600', fontSize: 13 },

    // Leaderboard row
    lbRow: {
        flexDirection: 'row',
        alignItems: 'center',
        backgroundColor: colors.surface.darkAlt,
        borderRadius: 12,
        padding: 12,
        marginBottom: 8,
        borderWidth: 1,
        borderColor: colors.grid.cellBorder,
        gap: 10,
    },
    lbRowMe: {
        borderColor: CYAN,
        backgroundColor: 'rgba(34,211,238,0.05)',
    },
    lbRank: { width: 32, textAlign: 'center', color: colors.text.muted, fontWeight: '700', fontSize: 14 },
    lbRankTop: { fontSize: 18 },
    lbNameMe: { color: CYAN },

    // Feed button
    feedButton: {
        marginTop: 16,
        backgroundColor: 'rgba(34,211,238,0.08)',
        borderRadius: 12,
        paddingVertical: 14,
        alignItems: 'center',
        borderWidth: 1,
        borderColor: 'rgba(34,211,238,0.3)',
    },
    feedButtonText: { color: CYAN, fontWeight: '600', fontSize: 15 },
});
