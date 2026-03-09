import React from 'react';
import {
    View,
    Text,
    TouchableOpacity,
    StyleSheet,
    SafeAreaView,
} from 'react-native';
import { ResultScreenProps } from '../types/navigation';
import { colors } from '../theme/colors';

export function ResultScreen({ route, navigation }: ResultScreenProps) {
    const { score, timeMs, hintsUsed, errorsCount, difficulty } = route.params;

    const totalSeconds = Math.floor(timeMs / 1000);
    const minutes = Math.floor(totalSeconds / 60);
    const seconds = totalSeconds % 60;
    const timeStr = `${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
    const diffLabel = difficulty.charAt(0).toUpperCase() + difficulty.slice(1);

    // Star rating based on score thresholds
    const maxScore: Record<string, number> = {
        beginner: 100, easy: 200, medium: 400, hard: 800, expert: 1500, evil: 3000,
    };
    const ratio = score / (maxScore[difficulty] || 200);
    const stars = ratio >= 0.9 ? 3 : ratio >= 0.6 ? 2 : 1;

    return (
        <SafeAreaView style={styles.container}>
            {/* Stars */}
            <View style={styles.starsRow}>
                {[1, 2, 3].map((n) => (
                    <Text key={n} style={[styles.star, n <= stars ? styles.starFilled : styles.starEmpty]}>
                        ★
                    </Text>
                ))}
            </View>

            <Text style={styles.title}>Puzzle Complete!</Text>
            <Text style={styles.diffBadge}>{diffLabel}</Text>

            {/* Stats Grid */}
            <View style={styles.statsGrid}>
                <StatCard label="Score" value={score.toString()} icon="🏆" />
                <StatCard label="Time" value={timeStr} icon="⏱" />
                <StatCard label="Hints" value={hintsUsed.toString()} icon="💡" />
                <StatCard label="Errors" value={errorsCount.toString()} icon="❌" />
            </View>

            {/* Actions */}
            <View style={styles.actions}>
                <TouchableOpacity
                    style={styles.primaryButton}
                    onPress={() => navigation.replace('Game', { difficulty })}
                    activeOpacity={0.8}
                >
                    <Text style={styles.primaryButtonText}>🔄  Play Again</Text>
                </TouchableOpacity>

                <TouchableOpacity
                    style={styles.secondaryButton}
                    onPress={() => navigation.popToTop()}
                    activeOpacity={0.8}
                >
                    <Text style={styles.secondaryButtonText}>🏠  Home</Text>
                </TouchableOpacity>
            </View>
        </SafeAreaView>
    );
}

function StatCard({ label, value, icon }: { label: string; value: string; icon: string }) {
    return (
        <View style={styles.statCard}>
            <Text style={styles.statIcon}>{icon}</Text>
            <Text style={styles.statValue}>{value}</Text>
            <Text style={styles.statLabel}>{label}</Text>
        </View>
    );
}

const styles = StyleSheet.create({
    container: {
        flex: 1,
        backgroundColor: colors.surface.dark,
        alignItems: 'center',
        justifyContent: 'center',
        paddingHorizontal: 24,
    },
    starsRow: {
        flexDirection: 'row',
        gap: 8,
        marginBottom: 16,
    },
    star: {
        fontSize: 48,
    },
    starFilled: {
        color: '#fbbf24',
    },
    starEmpty: {
        color: colors.text.muted,
    },
    title: {
        fontSize: 28,
        fontWeight: '800',
        color: colors.text.primary,
        marginBottom: 8,
    },
    diffBadge: {
        fontSize: 14,
        fontWeight: '700',
        color: colors.primary[400],
        backgroundColor: colors.primary[900],
        paddingHorizontal: 16,
        paddingVertical: 6,
        borderRadius: 8,
        overflow: 'hidden',
        marginBottom: 32,
    },
    statsGrid: {
        flexDirection: 'row',
        flexWrap: 'wrap',
        gap: 12,
        marginBottom: 40,
        justifyContent: 'center',
    },
    statCard: {
        width: 140,
        backgroundColor: colors.surface.card,
        borderRadius: 14,
        padding: 16,
        alignItems: 'center',
        borderWidth: 1,
        borderColor: colors.grid.cellBorder,
    },
    statIcon: {
        fontSize: 24,
        marginBottom: 4,
    },
    statValue: {
        fontSize: 22,
        fontWeight: '800',
        color: colors.text.primary,
        fontVariant: ['tabular-nums'],
    },
    statLabel: {
        fontSize: 12,
        color: colors.text.secondary,
        marginTop: 2,
    },
    actions: {
        width: '100%',
        gap: 12,
    },
    primaryButton: {
        backgroundColor: colors.primary[600],
        paddingVertical: 16,
        borderRadius: 14,
        alignItems: 'center',
    },
    primaryButtonText: {
        fontSize: 17,
        fontWeight: '700',
        color: '#ffffff',
    },
    secondaryButton: {
        backgroundColor: colors.surface.darkAlt,
        paddingVertical: 16,
        borderRadius: 14,
        alignItems: 'center',
        borderWidth: 1,
        borderColor: colors.grid.cellBorder,
    },
    secondaryButtonText: {
        fontSize: 17,
        fontWeight: '600',
        color: colors.text.primary,
    },
});
