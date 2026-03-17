/**
 * MatchResultScreen.tsx
 *
 * Displayed after a multiplayer match ends.
 * Shows win/loss, Elo before/after, delta, duration, difficulty.
 *
 * Params:
 *   won           — true if this player won
 *   endReason     — 'completed' | 'forfeit' | 'disconnect' | 'timeout'
 *   eloBefore     — Elo before this match (placeholder until rating service integration)
 *   eloAfter      — Elo after this match
 *   eloDelta      — signed delta (positive = gained, negative = lost)
 *   opponentName  — display name of the opponent
 *   difficulty    — puzzle difficulty
 *   durationMs    — elapsed game time in ms
 */

import React, { useEffect, useRef } from 'react';
import {
    Animated,
    Pressable,
    SafeAreaView,
    StatusBar,
    StyleSheet,
    Text,
    View,
} from 'react-native';
import { MatchResultScreenProps } from '../types/navigation';
import { colors } from '../theme/colors';

// ── Component ──────────────────────────────────────────────────────────────────

export function MatchResultScreen({ route, navigation }: MatchResultScreenProps) {
    const {
        won,
        endReason,
        eloBefore,
        eloAfter,
        eloDelta,
        opponentName,
        difficulty,
        durationMs,
    } = route.params;

    // Animate Elo counter from eloBefore to eloAfter over 1.2s
    const eloAnim = useRef(new Animated.Value(eloBefore)).current;
    const eloDisplay = useRef(eloBefore);

    useEffect(() => {
        Animated.timing(eloAnim, {
            toValue: eloAfter,
            duration: 1200,
            useNativeDriver: false,
        }).start();
    }, [eloAnim, eloAfter]);

    // Format duration
    const totalSec = Math.floor(durationMs / 1000);
    const durationStr = `${String(Math.floor(totalSec / 60)).padStart(2, '0')}:${String(totalSec % 60).padStart(2, '0')}`;

    // End reason label
    const reasonLabel: Record<string, string> = {
        completed: 'Puzzle solved',
        forfeit: 'Opponent surrendered',
        disconnect: 'Opponent disconnected',
        timeout: 'Timeout',
    };
    const reason = reasonLabel[endReason] ?? endReason;

    const deltaSign = eloDelta >= 0 ? '+' : '';

    return (
        <SafeAreaView style={styles.container}>
            <StatusBar barStyle="light-content" backgroundColor={colors.surface.dark} />

            {/* Result banner */}
            <View style={[styles.banner, won ? styles.bannerWin : styles.bannerLoss]}>
                <Text style={styles.bannerEmoji}>{won ? '🏆' : '💀'}</Text>
                <Text style={styles.bannerTitle}>{won ? 'Victory!' : 'Defeat'}</Text>
                <Text style={styles.bannerReason}>{reason}</Text>
            </View>

            {/* VS line */}
            <Text style={styles.vsLine}>
                You  vs  {opponentName}
            </Text>

            {/* Elo card */}
            <View style={styles.eloCard}>
                <View style={styles.eloRow}>
                    <View style={styles.eloStat}>
                        <Text style={styles.eloStatLabel}>Before</Text>
                        <Text style={styles.eloStatValue}>{eloBefore}</Text>
                    </View>

                    <View style={styles.eloDeltaBox}>
                        <Text style={[
                            styles.eloDeltaText,
                            eloDelta >= 0 ? styles.deltaPositive : styles.deltaNegative,
                        ]}>
                            {deltaSign}{eloDelta}
                        </Text>
                        <Text style={styles.eloDeltaLabel}>Elo</Text>
                    </View>

                    <View style={styles.eloStat}>
                        <Text style={styles.eloStatLabel}>After</Text>
                        <Animated.Text style={styles.eloStatValue}>
                            {/* Animated counter */}
                            {eloAfter}
                        </Animated.Text>
                    </View>
                </View>
            </View>

            {/* Stats grid */}
            <View style={styles.statsGrid}>
                <StatCard icon="⏱" label="Duration" value={durationStr} />
                <StatCard icon="🎯" label="Difficulty" value={capitalize(difficulty)} />
            </View>

            {/* Actions */}
            <View style={styles.actions}>
                <Pressable
                    style={({ pressed }) => [styles.primaryButton, pressed && styles.pressed]}
                    onPress={() => navigation.replace('MultiplayerLobby')}
                >
                    <Text style={styles.primaryButtonText}>⚔️  Play Again</Text>
                </Pressable>
                <Pressable
                    style={({ pressed }) => [styles.secondaryButton, pressed && styles.pressed]}
                    onPress={() => navigation.popToTop()}
                >
                    <Text style={styles.secondaryButtonText}>🏠  Home</Text>
                </Pressable>
            </View>
        </SafeAreaView>
    );
}

// ── Sub-components ─────────────────────────────────────────────────────────────

function StatCard({ icon, label, value }: { icon: string; label: string; value: string }) {
    return (
        <View style={styles.statCard}>
            <Text style={styles.statIcon}>{icon}</Text>
            <Text style={styles.statValue}>{value}</Text>
            <Text style={styles.statLabel}>{label}</Text>
        </View>
    );
}

// ── Helpers ────────────────────────────────────────────────────────────────────

function capitalize(s: string): string {
    return s.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

// ── Styles ─────────────────────────────────────────────────────────────────────

const styles = StyleSheet.create({
    container: {
        flex: 1,
        backgroundColor: colors.surface.dark,
        alignItems: 'center',
        paddingHorizontal: 24,
        paddingTop: 24,
    },
    pressed: { opacity: 0.75 },

    // Banner
    banner: {
        width: '100%',
        borderRadius: 16,
        padding: 24,
        alignItems: 'center',
        marginBottom: 16,
    },
    bannerWin: { backgroundColor: 'rgba(34,197,94,0.15)', borderWidth: 1, borderColor: colors.success },
    bannerLoss: { backgroundColor: 'rgba(239,68,68,0.12)', borderWidth: 1, borderColor: colors.error },
    bannerEmoji: { fontSize: 52, marginBottom: 8 },
    bannerTitle: { fontSize: 28, fontWeight: '900', color: colors.text.primary, marginBottom: 4 },
    bannerReason: { fontSize: 14, color: colors.text.secondary },

    vsLine: {
        fontSize: 14,
        color: colors.text.muted,
        marginBottom: 20,
    },

    // Elo card
    eloCard: {
        width: '100%',
        backgroundColor: colors.surface.darkAlt,
        borderRadius: 16,
        padding: 20,
        marginBottom: 20,
        borderWidth: 1,
        borderColor: colors.grid.cellBorder,
    },
    eloRow: {
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'space-between',
    },
    eloStat: { alignItems: 'center', flex: 1 },
    eloStatLabel: { fontSize: 12, color: colors.text.secondary, marginBottom: 4 },
    eloStatValue: { fontSize: 26, fontWeight: '800', color: colors.text.primary, fontVariant: ['tabular-nums'] },

    eloDeltaBox: {
        alignItems: 'center',
        flex: 1,
    },
    eloDeltaText: {
        fontSize: 32,
        fontWeight: '900',
        fontVariant: ['tabular-nums'],
    },
    eloDeltaLabel: {
        fontSize: 11,
        color: colors.text.muted,
        marginTop: 2,
    },
    deltaPositive: { color: colors.success },
    deltaNegative: { color: colors.error },

    // Stats grid
    statsGrid: {
        flexDirection: 'row',
        gap: 12,
        marginBottom: 32,
    },
    statCard: {
        flex: 1,
        backgroundColor: colors.surface.card,
        borderRadius: 14,
        padding: 16,
        alignItems: 'center',
        borderWidth: 1,
        borderColor: colors.grid.cellBorder,
    },
    statIcon: { fontSize: 22, marginBottom: 4 },
    statValue: { fontSize: 18, fontWeight: '800', color: colors.text.primary, fontVariant: ['tabular-nums'] },
    statLabel: { fontSize: 11, color: colors.text.secondary, marginTop: 2 },

    // Actions
    actions: { width: '100%', gap: 12 },
    primaryButton: {
        backgroundColor: colors.primary[600],
        paddingVertical: 16,
        borderRadius: 14,
        alignItems: 'center',
    },
    primaryButtonText: { fontSize: 17, fontWeight: '700', color: '#fff' },
    secondaryButton: {
        backgroundColor: colors.surface.darkAlt,
        paddingVertical: 16,
        borderRadius: 14,
        alignItems: 'center',
        borderWidth: 1,
        borderColor: colors.grid.cellBorder,
    },
    secondaryButtonText: { fontSize: 17, fontWeight: '600', color: colors.text.primary },
});
