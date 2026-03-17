import React, { useCallback, useEffect, useState } from 'react';
import {
    ActivityIndicator,
    Pressable,
    RefreshControl,
    SafeAreaView,
    ScrollView,
    StatusBar,
    StyleSheet,
    Text,
    View,
} from 'react-native';
import { HomeScreenProps } from '../types/navigation';
import { colors } from '../theme/colors';

const API_BASE_URL = process.env.EXPO_PUBLIC_API_URL ?? 'http://localhost:3001';
// In development, set EXPO_PUBLIC_API_TOKEN to a valid JWT.
// A login screen (Phase 3) will populate this via secure storage.
const API_TOKEN = process.env.EXPO_PUBLIC_API_TOKEN ?? '';

// ─── Types ────────────────────────────────────────────────────────────────────

interface PuzzleRecommendation {
    id: string;
    difficulty: string;
    clueCount: number;
    createdAt: string;
}

interface HomeData {
    skillCluster: string | null;
    clusterMessage: string;
    recommendedDifficulties: string[];
    recommendations: PuzzleRecommendation[];
    dailyPuzzle: {
        id: string;
        puzzleId: string;
        date: string;
        difficulty: string;
    } | null;
    streak: {
        currentStreak: number;
        longestStreak: number;
        freezeCount: number;
        newMilestone: number | null;
    } | null;
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

const DIFFICULTY_EMOJI: Record<string, string> = {
    super_easy: '🟢',
    easy:       '🟡',
    medium:     '🟠',
    hard:       '🔴',
    super_hard: '🟣',
    extreme:    '⚫',
};

function difficultyLabel(d: string): string {
    return d.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

// ─── Component ────────────────────────────────────────────────────────────────

export function HomeScreen({ navigation }: HomeScreenProps) {
    const [homeData, setHomeData] = useState<HomeData | null>(null);
    const [loading, setLoading] = useState(true);
    const [refreshing, setRefreshing] = useState(false);

    const fetchHomeData = useCallback(async (): Promise<void> => {
        try {
            const headers: Record<string, string> = { 'Content-Type': 'application/json' };
            if (API_TOKEN) {
                headers['Authorization'] = `Bearer ${API_TOKEN}`;
            }
            const response = await fetch(`${API_BASE_URL}/api/home`, { headers });
            if (!response.ok) {
                // 401 (no token yet) or server error — degrade gracefully.
                setHomeData(null);
                return;
            }
            const json = await response.json();
            setHomeData(json.data as HomeData);
        } catch {
            // Network unavailable — degrade gracefully, static UI still usable.
            setHomeData(null);
        }
    }, []);

    useEffect(() => {
        fetchHomeData().finally(() => setLoading(false));
    }, [fetchHomeData]);

    const onRefresh = useCallback(async () => {
        setRefreshing(true);
        await fetchHomeData();
        setRefreshing(false);
    }, [fetchHomeData]);

    // ── Loading splash ────────────────────────────────────────────────────────

    if (loading) {
        return (
            <SafeAreaView style={[styles.container, styles.center]}>
                <StatusBar barStyle="light-content" backgroundColor={colors.surface.dark} />
                <ActivityIndicator size="large" color="#a78bfa" />
            </SafeAreaView>
        );
    }

    // ── Full screen ───────────────────────────────────────────────────────────

    return (
        <SafeAreaView style={styles.container}>
            <StatusBar barStyle="light-content" backgroundColor={colors.surface.dark} />

            <ScrollView
                contentContainerStyle={styles.scroll}
                showsVerticalScrollIndicator={false}
                refreshControl={
                    <RefreshControl
                        refreshing={refreshing}
                        onRefresh={onRefresh}
                        tintColor="#a78bfa"
                    />
                }
            >
                {/* ── Header ─────────────────────────────────────────────── */}
                <View style={styles.header}>
                    <Text style={styles.heroEmoji}>🧩</Text>
                    <Text style={styles.title}>Sudoku Ultra</Text>

                    {homeData?.skillCluster ? (
                        <View style={styles.clusterBadge}>
                            <Text style={styles.clusterText}>{homeData.skillCluster}</Text>
                        </View>
                    ) : (
                        <Text style={styles.subtitle}>ML-Powered Sudoku Platform</Text>
                    )}
                </View>

                {/* ── Cluster message ─────────────────────────────────────── */}
                {homeData?.clusterMessage ? (
                    <View style={styles.messageCard}>
                        <Text style={styles.messageText}>{homeData.clusterMessage}</Text>
                    </View>
                ) : null}

                {/* ── Streak bar ──────────────────────────────────────────── */}
                {homeData?.streak ? (
                    <View style={styles.streakBar}>
                        <View style={styles.streakItem}>
                            <Text style={styles.streakNumber}>
                                {homeData.streak.currentStreak}
                            </Text>
                            <Text style={styles.streakLabel}>Day Streak</Text>
                        </View>
                        <View style={styles.streakDivider} />
                        <View style={styles.streakItem}>
                            <Text style={styles.streakNumber}>
                                {homeData.streak.longestStreak}
                            </Text>
                            <Text style={styles.streakLabel}>Best</Text>
                        </View>
                        <View style={styles.streakDivider} />
                        <View style={styles.streakItem}>
                            <Text style={styles.streakNumber}>
                                {homeData.streak.freezeCount}
                            </Text>
                            <Text style={styles.streakLabel}>Freezes</Text>
                        </View>
                    </View>
                ) : null}

                {/* ── Primary actions ─────────────────────────────────────── */}
                <View style={styles.actions}>
                    <Pressable
                        style={({ pressed }) => [styles.primaryButton, pressed && styles.pressed]}
                        onPress={() => navigation.navigate('Difficulty')}
                    >
                        <Text style={styles.primaryButtonText}>🎮  New Game</Text>
                    </Pressable>

                    {homeData?.dailyPuzzle ? (
                        <Pressable
                            style={({ pressed }) => [styles.dailyButton, pressed && styles.pressed]}
                            onPress={() => navigation.navigate('Difficulty')}
                        >
                            <Text style={styles.dailyButtonTitle}>📅  Daily Puzzle</Text>
                            <Text style={styles.dailyButtonSub}>
                                {difficultyLabel(homeData.dailyPuzzle.difficulty)}
                                {'  ·  '}
                                {homeData.dailyPuzzle.date}
                            </Text>
                        </Pressable>
                    ) : (
                        <Pressable
                            style={({ pressed }) => [styles.secondaryButton, pressed && styles.pressed]}
                            onPress={() => navigation.navigate('Difficulty')}
                        >
                            <Text style={styles.secondaryButtonText}>📅  Daily Puzzle</Text>
                        </Pressable>
                    )}

                    <Pressable
                        style={({ pressed }) => [styles.secondaryButton, pressed && styles.pressed]}
                        onPress={() => navigation.navigate('ScanPuzzle')}
                    >
                        <Text style={styles.secondaryButtonText}>📷  Scan Puzzle</Text>
                    </Pressable>

                    <Pressable
                        style={({ pressed }) => [styles.multiplayerButton, pressed && styles.pressed]}
                        onPress={() => navigation.navigate('MultiplayerLobby')}
                    >
                        <Text style={styles.multiplayerButtonText}>⚔️  Multiplayer</Text>
                    </Pressable>
                </View>

                {/* ── Recommended difficulties ────────────────────────────── */}
                {homeData?.recommendedDifficulties && homeData.recommendedDifficulties.length > 0 ? (
                    <View style={styles.section}>
                        <Text style={styles.sectionTitle}>Recommended for you</Text>
                        <View style={styles.chipRow}>
                            {homeData.recommendedDifficulties.map((d) => (
                                <Pressable
                                    key={d}
                                    style={({ pressed }) => [styles.chip, pressed && styles.pressed]}
                                    onPress={() => navigation.navigate('Difficulty')}
                                >
                                    <Text style={styles.chipText}>
                                        {DIFFICULTY_EMOJI[d] ?? '⚪'} {difficultyLabel(d)}
                                    </Text>
                                </Pressable>
                            ))}
                        </View>
                    </View>
                ) : null}

                {/* ── Recent puzzle recommendations ────────────────────────── */}
                {homeData?.recommendations && homeData.recommendations.length > 0 ? (
                    <View style={styles.section}>
                        <Text style={styles.sectionTitle}>Recent puzzles</Text>
                        {homeData.recommendations.map((p) => (
                            <Pressable
                                key={p.id}
                                style={({ pressed }) => [styles.puzzleCard, pressed && styles.pressed]}
                                onPress={() => navigation.navigate('Difficulty')}
                            >
                                <Text style={styles.puzzleEmoji}>
                                    {DIFFICULTY_EMOJI[p.difficulty] ?? '⚪'}
                                </Text>
                                <View style={styles.puzzleInfo}>
                                    <Text style={styles.puzzleTitle}>
                                        {difficultyLabel(p.difficulty)}
                                    </Text>
                                    <Text style={styles.puzzleSub}>{p.clueCount} clues</Text>
                                </View>
                                <Text style={styles.puzzleArrow}>›</Text>
                            </Pressable>
                        ))}
                    </View>
                ) : null}

                <Text style={styles.version}>v0.0.1 — Phase 2</Text>
            </ScrollView>
        </SafeAreaView>
    );
}

// ─── Styles ───────────────────────────────────────────────────────────────────

const styles = StyleSheet.create({
    container: {
        flex: 1,
        backgroundColor: colors.surface.dark,
    },
    center: {
        justifyContent: 'center',
        alignItems: 'center',
    },
    scroll: {
        paddingHorizontal: 24,
        paddingTop: 32,
        paddingBottom: 48,
    },
    pressed: {
        opacity: 0.75,
    },

    // Header
    header: {
        alignItems: 'center',
        marginBottom: 20,
    },
    heroEmoji: {
        fontSize: 56,
        marginBottom: 12,
    },
    title: {
        fontSize: 32,
        fontWeight: '800',
        color: colors.text.primary,
        letterSpacing: 1,
        marginBottom: 8,
    },
    subtitle: {
        fontSize: 13,
        color: colors.text.secondary,
        letterSpacing: 0.4,
    },
    clusterBadge: {
        backgroundColor: 'rgba(167, 139, 250, 0.15)',
        borderWidth: 1,
        borderColor: '#a78bfa',
        borderRadius: 20,
        paddingHorizontal: 16,
        paddingVertical: 4,
    },
    clusterText: {
        color: '#a78bfa',
        fontSize: 13,
        fontWeight: '600',
        letterSpacing: 0.5,
    },

    // Cluster message
    messageCard: {
        backgroundColor: colors.surface.darkAlt,
        borderRadius: 12,
        padding: 14,
        marginBottom: 20,
        borderWidth: 1,
        borderColor: colors.grid.cellBorder,
    },
    messageText: {
        color: colors.text.secondary,
        fontSize: 13,
        lineHeight: 19,
        textAlign: 'center',
    },

    // Streak bar
    streakBar: {
        flexDirection: 'row',
        backgroundColor: colors.surface.darkAlt,
        borderRadius: 14,
        paddingVertical: 16,
        marginBottom: 24,
        borderWidth: 1,
        borderColor: colors.grid.cellBorder,
    },
    streakItem: {
        flex: 1,
        alignItems: 'center',
    },
    streakNumber: {
        fontSize: 24,
        fontWeight: '800',
        color: '#a78bfa',
    },
    streakLabel: {
        fontSize: 11,
        color: colors.text.muted,
        marginTop: 2,
    },
    streakDivider: {
        width: 1,
        backgroundColor: colors.grid.cellBorder,
    },

    // Actions
    actions: {
        gap: 12,
        marginBottom: 28,
    },
    primaryButton: {
        backgroundColor: colors.primary[600],
        paddingVertical: 18,
        borderRadius: 14,
        alignItems: 'center',
        shadowColor: colors.primary[500],
        shadowOffset: { width: 0, height: 4 },
        shadowOpacity: 0.3,
        shadowRadius: 8,
        elevation: 6,
    },
    primaryButtonText: {
        fontSize: 17,
        fontWeight: '700',
        color: '#ffffff',
        letterSpacing: 0.4,
    },
    dailyButton: {
        backgroundColor: colors.surface.darkAlt,
        paddingVertical: 14,
        paddingHorizontal: 20,
        borderRadius: 14,
        alignItems: 'center',
        borderWidth: 1,
        borderColor: '#a78bfa',
    },
    dailyButtonTitle: {
        fontSize: 16,
        fontWeight: '600',
        color: colors.text.primary,
        textAlign: 'center',
    },
    dailyButtonSub: {
        fontSize: 12,
        color: '#a78bfa',
        marginTop: 3,
        textAlign: 'center',
    },
    secondaryButton: {
        backgroundColor: colors.surface.darkAlt,
        paddingVertical: 18,
        borderRadius: 14,
        alignItems: 'center',
        borderWidth: 1,
        borderColor: colors.grid.cellBorder,
    },
    secondaryButtonText: {
        fontSize: 17,
        fontWeight: '600',
        color: colors.text.primary,
        letterSpacing: 0.4,
    },

    // Sections
    section: {
        marginBottom: 24,
    },
    sectionTitle: {
        fontSize: 14,
        fontWeight: '700',
        color: colors.text.secondary,
        letterSpacing: 0.6,
        textTransform: 'uppercase',
        marginBottom: 12,
    },

    // Difficulty chips
    chipRow: {
        flexDirection: 'row',
        flexWrap: 'wrap',
        gap: 8,
    },
    chip: {
        backgroundColor: colors.surface.darkAlt,
        borderRadius: 20,
        paddingHorizontal: 14,
        paddingVertical: 8,
        borderWidth: 1,
        borderColor: colors.grid.cellBorder,
    },
    chipText: {
        color: colors.text.primary,
        fontSize: 13,
        fontWeight: '500',
    },

    // Puzzle cards
    puzzleCard: {
        flexDirection: 'row',
        alignItems: 'center',
        backgroundColor: colors.surface.darkAlt,
        borderRadius: 12,
        padding: 14,
        marginBottom: 8,
        borderWidth: 1,
        borderColor: colors.grid.cellBorder,
    },
    puzzleEmoji: {
        fontSize: 22,
        marginRight: 12,
    },
    puzzleInfo: {
        flex: 1,
    },
    puzzleTitle: {
        fontSize: 15,
        fontWeight: '600',
        color: colors.text.primary,
    },
    puzzleSub: {
        fontSize: 12,
        color: colors.text.muted,
        marginTop: 2,
    },
    puzzleArrow: {
        fontSize: 22,
        color: colors.text.muted,
        marginLeft: 8,
    },

    // Multiplayer button
    multiplayerButton: {
        backgroundColor: 'rgba(167, 139, 250, 0.1)',
        paddingVertical: 18,
        borderRadius: 14,
        alignItems: 'center',
        borderWidth: 1,
        borderColor: '#a78bfa',
    },
    multiplayerButtonText: {
        fontSize: 17,
        fontWeight: '700',
        color: '#a78bfa',
        letterSpacing: 0.4,
    },

    // Footer
    version: {
        fontSize: 11,
        color: colors.text.muted,
        textAlign: 'center',
        marginTop: 8,
    },
});
