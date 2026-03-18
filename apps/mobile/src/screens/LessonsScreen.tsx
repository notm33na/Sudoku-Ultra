/**
 * LessonsScreen — lesson library with XP progress bar.
 *
 * Shows all 15 lessons grouped by difficulty, each card with:
 *   - completion state (lock icon if prerequisites unmet)
 *   - XP reward badge
 *   - step progress bar
 *
 * Tapping a lesson navigates to LessonDetail.
 */

import React, { useCallback, useEffect, useState } from 'react';
import {
    View,
    Text,
    FlatList,
    TouchableOpacity,
    StyleSheet,
    ActivityIndicator,
    ScrollView,
} from 'react-native';
import { LessonsScreenProps } from '../types/navigation';

const API = process.env.EXPO_PUBLIC_API_URL ?? 'http://localhost:3001';
const TOKEN = process.env.EXPO_PUBLIC_API_TOKEN ?? '';

// ── Types (mirror lesson.service.ts) ─────────────────────────────────────────

interface LessonSummary {
    id: string;
    title: string;
    difficulty: 1 | 2 | 3 | 4 | 5;
    xpReward: number;
    estimatedMinutes: number;
    description: string;
    tags: string[];
    prerequisiteIds: string[];
    totalSteps: number;
    progress: {
        stepsComplete: number;
        completed: boolean;
        completedAt: string | null;
        xpAwarded: number;
    } | null;
}

interface BadgeSummary {
    id: string;
    title: string;
    description: string;
    icon: string;
    awardedAt: string;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

const DIFFICULTY_LABELS: Record<number, string> = {
    1: 'Beginner',
    2: 'Intermediate',
    3: 'Advanced',
    4: 'Expert',
    5: 'Master',
};

const DIFFICULTY_COLORS: Record<number, string> = {
    1: '#22c55e',
    2: '#3b82f6',
    3: '#f59e0b',
    4: '#ef4444',
    5: '#8b5cf6',
};

function totalXp(lessons: LessonSummary[]): number {
    return lessons.reduce((sum, l) => sum + (l.progress?.xpAwarded ?? 0), 0);
}

function maxXp(lessons: LessonSummary[]): number {
    return lessons.reduce((sum, l) => sum + l.xpReward, 0);
}

function isUnlocked(lesson: LessonSummary, completedIds: Set<string>): boolean {
    return lesson.prerequisiteIds.every((id) => completedIds.has(id));
}

// ── Sub-components ────────────────────────────────────────────────────────────

function XpBar({ earned, total }: { earned: number; total: number }) {
    const pct = total > 0 ? Math.min(earned / total, 1) : 0;
    return (
        <View style={styles.xpBarContainer}>
            <View style={styles.xpBarTrack}>
                <View style={[styles.xpBarFill, { width: `${pct * 100}%` as any }]} />
            </View>
            <Text style={styles.xpText}>{earned} / {total} XP</Text>
        </View>
    );
}

function BadgePill({ badge }: { badge: BadgeSummary }) {
    return (
        <View style={styles.badgePill}>
            <Text style={styles.badgeIcon}>{badge.icon}</Text>
            <Text style={styles.badgeTitle}>{badge.title}</Text>
        </View>
    );
}

function LessonCard({
    lesson,
    unlocked,
    onPress,
}: {
    lesson: LessonSummary;
    unlocked: boolean;
    onPress: () => void;
}) {
    const completed = lesson.progress?.completed ?? false;
    const stepsComplete = lesson.progress?.stepsComplete ?? 0;
    const color = DIFFICULTY_COLORS[lesson.difficulty];

    return (
        <TouchableOpacity
            style={[
                styles.card,
                completed && styles.cardCompleted,
                !unlocked && styles.cardLocked,
            ]}
            onPress={onPress}
            disabled={!unlocked}
            activeOpacity={0.85}
        >
            {/* Left accent bar */}
            <View style={[styles.cardAccent, { backgroundColor: unlocked ? color : '#374151' }]} />

            <View style={styles.cardBody}>
                <View style={styles.cardHeader}>
                    <Text style={[styles.cardTitle, !unlocked && styles.textDim]}
                          numberOfLines={1}>
                        {!unlocked ? '🔒 ' : completed ? '✅ ' : ''}{lesson.title}
                    </Text>
                    <View style={[styles.xpBadge, { backgroundColor: color + '22', borderColor: color }]}>
                        <Text style={[styles.xpBadgeText, { color }]}>+{lesson.xpReward} XP</Text>
                    </View>
                </View>

                <Text style={[styles.cardDesc, !unlocked && styles.textDim]} numberOfLines={2}>
                    {lesson.description}
                </Text>

                {/* Step progress */}
                <View style={styles.stepRow}>
                    <View style={styles.stepTrack}>
                        <View
                            style={[
                                styles.stepFill,
                                {
                                    backgroundColor: color,
                                    width: `${(stepsComplete / lesson.totalSteps) * 100}%` as any,
                                },
                            ]}
                        />
                    </View>
                    <Text style={styles.stepLabel}>
                        {stepsComplete}/{lesson.totalSteps} steps
                    </Text>
                    <Text style={styles.timeLabel}>{lesson.estimatedMinutes} min</Text>
                </View>
            </View>
        </TouchableOpacity>
    );
}

// ── Main screen ───────────────────────────────────────────────────────────────

export default function LessonsScreen({ navigation }: LessonsScreenProps) {
    const [lessons, setLessons] = useState<LessonSummary[]>([]);
    const [badges, setBadges] = useState<BadgeSummary[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    const load = useCallback(async () => {
        setLoading(true);
        setError(null);
        try {
            const [lRes, bRes] = await Promise.all([
                fetch(`${API}/api/lessons`, { headers: { Authorization: `Bearer ${TOKEN}` } }),
                fetch(`${API}/api/lessons/badges`, { headers: { Authorization: `Bearer ${TOKEN}` } }),
            ]);
            const lData = await lRes.json();
            const bData = await bRes.json();
            setLessons(lData.lessons ?? []);
            setBadges(bData.earned ?? []);
        } catch (e: any) {
            setError(e.message ?? 'Failed to load lessons.');
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        const unsub = navigation.addListener('focus', load);
        return unsub;
    }, [navigation, load]);

    if (loading) {
        return (
            <View style={styles.center}>
                <ActivityIndicator size="large" color="#6366f1" />
            </View>
        );
    }

    if (error) {
        return (
            <View style={styles.center}>
                <Text style={styles.errorText}>{error}</Text>
                <TouchableOpacity style={styles.retryBtn} onPress={load}>
                    <Text style={styles.retryBtnText}>Retry</Text>
                </TouchableOpacity>
            </View>
        );
    }

    const completedIds = new Set(lessons.filter((l) => l.progress?.completed).map((l) => l.id));
    const earned = totalXp(lessons);
    const maxTotal = maxXp(lessons);

    // Group by difficulty
    const grouped: Array<{ difficulty: number; items: LessonSummary[] }> = [1, 2, 3, 4, 5].map(
        (d) => ({ difficulty: d, items: lessons.filter((l) => l.difficulty === d) }),
    );

    return (
        <ScrollView style={styles.container} contentContainerStyle={styles.scrollContent}>
            {/* Header */}
            <View style={styles.header}>
                <Text style={styles.headerTitle}>Technique Lessons</Text>
                <Text style={styles.headerSub}>Master Sudoku step by step</Text>
                <XpBar earned={earned} total={maxTotal} />
            </View>

            {/* Badges */}
            {badges.length > 0 && (
                <View style={styles.badgesRow}>
                    {badges.map((b) => (
                        <BadgePill key={b.id} badge={b} />
                    ))}
                </View>
            )}

            {/* Lesson groups */}
            {grouped.map(({ difficulty, items }) => (
                items.length === 0 ? null : (
                    <View key={difficulty} style={styles.group}>
                        <Text style={[styles.groupTitle, { color: DIFFICULTY_COLORS[difficulty] }]}>
                            {DIFFICULTY_LABELS[difficulty]}
                        </Text>
                        {items.map((lesson) => (
                            <LessonCard
                                key={lesson.id}
                                lesson={lesson}
                                unlocked={isUnlocked(lesson, completedIds)}
                                onPress={() =>
                                    navigation.navigate('LessonDetail', {
                                        lessonId: lesson.id,
                                        title: lesson.title,
                                    })
                                }
                            />
                        ))}
                    </View>
                )
            ))}
        </ScrollView>
    );
}

// ── Styles ────────────────────────────────────────────────────────────────────

const styles = StyleSheet.create({
    container: { flex: 1, backgroundColor: '#0f172a' },
    scrollContent: { paddingBottom: 40 },
    center: { flex: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: '#0f172a' },

    header: { padding: 20, paddingTop: 12 },
    headerTitle: { fontSize: 24, fontWeight: '700', color: '#f1f5f9' },
    headerSub: { fontSize: 14, color: '#94a3b8', marginTop: 2, marginBottom: 12 },

    xpBarContainer: { flexDirection: 'row', alignItems: 'center', gap: 10 },
    xpBarTrack: {
        flex: 1, height: 8, backgroundColor: '#1e293b', borderRadius: 4, overflow: 'hidden',
    },
    xpBarFill: { height: '100%', backgroundColor: '#6366f1', borderRadius: 4 },
    xpText: { fontSize: 12, color: '#94a3b8', minWidth: 90, textAlign: 'right' },

    badgesRow: {
        flexDirection: 'row', flexWrap: 'wrap', paddingHorizontal: 16, gap: 8, marginBottom: 8,
    },
    badgePill: {
        flexDirection: 'row', alignItems: 'center', gap: 4,
        backgroundColor: '#1e293b', borderRadius: 20, paddingHorizontal: 10, paddingVertical: 4,
    },
    badgeIcon: { fontSize: 14 },
    badgeTitle: { fontSize: 12, color: '#f1f5f9', fontWeight: '600' },

    group: { paddingHorizontal: 16, marginBottom: 4 },
    groupTitle: { fontSize: 12, fontWeight: '700', letterSpacing: 1, marginBottom: 8, marginTop: 12 },

    card: {
        flexDirection: 'row', backgroundColor: '#1e293b', borderRadius: 10,
        marginBottom: 10, overflow: 'hidden',
    },
    cardCompleted: { opacity: 0.75 },
    cardLocked: { opacity: 0.45 },
    cardAccent: { width: 4 },
    cardBody: { flex: 1, padding: 12 },
    cardHeader: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 4 },
    cardTitle: { fontSize: 15, fontWeight: '600', color: '#f1f5f9', flex: 1, marginRight: 8 },
    cardDesc: { fontSize: 12, color: '#94a3b8', marginBottom: 8 },
    textDim: { color: '#475569' },

    xpBadge: {
        paddingHorizontal: 7, paddingVertical: 2, borderRadius: 10, borderWidth: 1,
    },
    xpBadgeText: { fontSize: 11, fontWeight: '700' },

    stepRow: { flexDirection: 'row', alignItems: 'center', gap: 8 },
    stepTrack: {
        flex: 1, height: 4, backgroundColor: '#0f172a', borderRadius: 2, overflow: 'hidden',
    },
    stepFill: { height: '100%', borderRadius: 2 },
    stepLabel: { fontSize: 11, color: '#64748b' },
    timeLabel: { fontSize: 11, color: '#475569' },

    errorText: { color: '#ef4444', textAlign: 'center', marginBottom: 12 },
    retryBtn: { backgroundColor: '#6366f1', paddingHorizontal: 20, paddingVertical: 8, borderRadius: 8 },
    retryBtnText: { color: '#fff', fontWeight: '600' },
});
