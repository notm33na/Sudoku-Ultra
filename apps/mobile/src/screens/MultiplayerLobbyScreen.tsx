/**
 * MultiplayerLobbyScreen.tsx
 *
 * Three multiplayer entry points:
 *   1. Play vs Bot  — POST /rooms type=bot → navigate to game immediately.
 *   2. Invite Friend — POST /rooms type=private → show 6-char invite code.
 *   3. Join by Code  — enter invite code → POST /rooms/code/join → navigate.
 *
 * Env vars:
 *   EXPO_PUBLIC_WS_URL   base URL for multiplayer service (default: http://localhost:8080)
 *   EXPO_PUBLIC_USER_ID  dev placeholder user-id
 *   EXPO_PUBLIC_USER_NAME dev placeholder display name
 *   EXPO_PUBLIC_API_TOKEN dev JWT token
 */

import React, { useCallback, useState } from 'react';
import {
    ActivityIndicator,
    Alert,
    KeyboardAvoidingView,
    Platform,
    Pressable,
    SafeAreaView,
    ScrollView,
    StatusBar,
    StyleSheet,
    Text,
    TextInput,
    View,
} from 'react-native';
import { MultiplayerLobbyScreenProps } from '../types/navigation';
import { colors } from '../theme/colors';

// ── Config ─────────────────────────────────────────────────────────────────────

const MP_BASE = process.env.EXPO_PUBLIC_WS_URL ?? 'http://localhost:8080';
const MY_USER_ID = process.env.EXPO_PUBLIC_USER_ID ?? 'dev-user-1';
const MY_DISPLAY_NAME = process.env.EXPO_PUBLIC_USER_NAME ?? 'Player';
const AUTH_TOKEN = process.env.EXPO_PUBLIC_API_TOKEN ?? `${MY_USER_ID}:${MY_DISPLAY_NAME}`;

const DIFFICULTIES = ['easy', 'medium', 'hard', 'super_hard'] as const;
type Diff = typeof DIFFICULTIES[number];

const DIFF_LABELS: Record<Diff, string> = {
    easy: 'Easy',
    medium: 'Medium',
    hard: 'Hard',
    super_hard: 'Super Hard',
};

// ── Helpers ────────────────────────────────────────────────────────────────────

async function postRoom(body: object): Promise<Response> {
    return fetch(`${MP_BASE}/rooms`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            Authorization: `Bearer ${AUTH_TOKEN}`,
        },
        body: JSON.stringify(body),
    });
}

async function joinByCode(code: string): Promise<Response> {
    // Pass "code" as placeholder room ID; server falls through to GetByCode.
    return fetch(`${MP_BASE}/rooms/code/join`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            Authorization: `Bearer ${AUTH_TOKEN}`,
        },
        body: JSON.stringify({ code }),
    });
}

// ── Component ──────────────────────────────────────────────────────────────────

export function MultiplayerLobbyScreen({ navigation }: MultiplayerLobbyScreenProps) {
    const [selectedDiff, setSelectedDiff] = useState<Diff>('medium');
    const [loading, setLoading] = useState<string | null>(null);
    const [inviteCode, setInviteCode] = useState<string | null>(null);
    const [joinCode, setJoinCode] = useState('');

    // ── Play vs Bot ──────────────────────────────────────────────────────────

    const handleBotMatch = useCallback(async () => {
        setLoading('bot');
        try {
            const res = await postRoom({ type: 'bot', difficulty: selectedDiff, bot_tier: 'medium' });
            if (!res.ok) {
                const err = await res.json().catch(() => ({}));
                Alert.alert('Error', err.message ?? 'Could not create bot room.');
                return;
            }
            const data = await res.json();
            navigation.replace('MultiplayerGame', {
                roomId: data.room_id,
                myUserId: MY_USER_ID,
                myDisplayName: MY_DISPLAY_NAME,
                difficulty: selectedDiff,
            });
        } catch {
            Alert.alert('Error', 'Could not reach multiplayer service.');
        } finally {
            setLoading(null);
        }
    }, [navigation, selectedDiff]);

    // ── Invite Friend ────────────────────────────────────────────────────────

    const handleCreatePrivate = useCallback(async () => {
        setLoading('private');
        setInviteCode(null);
        try {
            const res = await postRoom({ type: 'private', difficulty: selectedDiff });
            if (!res.ok) {
                const err = await res.json().catch(() => ({}));
                Alert.alert('Error', err.message ?? 'Could not create room.');
                return;
            }
            const data = await res.json();
            setInviteCode(data.code ?? null);
            if (data.room_id) {
                // Navigate only after opponent joins (handled by WS room_state in game screen)
                navigation.replace('MultiplayerGame', {
                    roomId: data.room_id,
                    myUserId: MY_USER_ID,
                    myDisplayName: MY_DISPLAY_NAME,
                    difficulty: selectedDiff,
                });
            }
        } catch {
            Alert.alert('Error', 'Could not reach multiplayer service.');
        } finally {
            setLoading(null);
        }
    }, [navigation, selectedDiff]);

    // ── Join by Code ─────────────────────────────────────────────────────────

    const handleJoinByCode = useCallback(async () => {
        const code = joinCode.trim().toUpperCase();
        if (code.length !== 6) {
            Alert.alert('Invalid Code', 'Enter the 6-character invite code.');
            return;
        }
        setLoading('join');
        try {
            const res = await joinByCode(code);
            if (!res.ok) {
                const err = await res.json().catch(() => ({}));
                Alert.alert('Error', err.message ?? 'Room not found or already started.');
                return;
            }
            const data = await res.json();
            navigation.replace('MultiplayerGame', {
                roomId: data.id,
                myUserId: MY_USER_ID,
                myDisplayName: MY_DISPLAY_NAME,
                difficulty: data.difficulty ?? selectedDiff,
            });
        } catch {
            Alert.alert('Error', 'Could not reach multiplayer service.');
        } finally {
            setLoading(null);
        }
    }, [navigation, joinCode, selectedDiff]);

    // ── Render ───────────────────────────────────────────────────────────────

    return (
        <SafeAreaView style={styles.container}>
            <StatusBar barStyle="light-content" backgroundColor={colors.surface.dark} />
            <KeyboardAvoidingView
                style={styles.flex}
                behavior={Platform.OS === 'ios' ? 'padding' : undefined}
            >
                <ScrollView
                    contentContainerStyle={styles.scroll}
                    keyboardShouldPersistTaps="handled"
                    showsVerticalScrollIndicator={false}
                >
                    {/* Header */}
                    <View style={styles.header}>
                        <Text style={styles.emoji}>⚔️</Text>
                        <Text style={styles.title}>Multiplayer</Text>
                        <Text style={styles.subtitle}>Challenge opponents in real-time</Text>
                    </View>

                    {/* Difficulty selector */}
                    <Text style={styles.label}>Difficulty</Text>
                    <View style={styles.chipRow}>
                        {DIFFICULTIES.map((d) => (
                            <Pressable
                                key={d}
                                style={[styles.chip, selectedDiff === d && styles.chipSelected]}
                                onPress={() => setSelectedDiff(d)}
                            >
                                <Text style={[styles.chipText, selectedDiff === d && styles.chipTextSelected]}>
                                    {DIFF_LABELS[d]}
                                </Text>
                            </Pressable>
                        ))}
                    </View>

                    {/* Bot match */}
                    <View style={styles.section}>
                        <Text style={styles.sectionTitle}>Practice</Text>
                        <Pressable
                            style={({ pressed }) => [styles.primaryButton, pressed && styles.pressed,
                                loading === 'bot' && styles.buttonLoading]}
                            onPress={handleBotMatch}
                            disabled={loading !== null}
                        >
                            {loading === 'bot'
                                ? <ActivityIndicator color="#fff" />
                                : <Text style={styles.primaryButtonText}>🤖  Play vs Bot</Text>
                            }
                        </Pressable>
                    </View>

                    {/* Private room */}
                    <View style={styles.section}>
                        <Text style={styles.sectionTitle}>Invite a Friend</Text>
                        <Pressable
                            style={({ pressed }) => [styles.secondaryButton, pressed && styles.pressed,
                                loading === 'private' && styles.buttonLoading]}
                            onPress={handleCreatePrivate}
                            disabled={loading !== null}
                        >
                            {loading === 'private'
                                ? <ActivityIndicator color={colors.text.primary} />
                                : <Text style={styles.secondaryButtonText}>🔗  Create Private Room</Text>
                            }
                        </Pressable>

                        {inviteCode ? (
                            <View style={styles.codeCard}>
                                <Text style={styles.codeLabel}>Share this code:</Text>
                                <Text style={styles.codeValue}>{inviteCode}</Text>
                            </View>
                        ) : null}
                    </View>

                    {/* Join by code */}
                    <View style={styles.section}>
                        <Text style={styles.sectionTitle}>Join a Room</Text>
                        <View style={styles.joinRow}>
                            <TextInput
                                style={styles.codeInput}
                                value={joinCode}
                                onChangeText={(t) => setJoinCode(t.toUpperCase().slice(0, 6))}
                                placeholder="INVITE CODE"
                                placeholderTextColor={colors.text.muted}
                                autoCapitalize="characters"
                                autoCorrect={false}
                                maxLength={6}
                                returnKeyType="go"
                                onSubmitEditing={handleJoinByCode}
                            />
                            <Pressable
                                style={({ pressed }) => [styles.joinButton, pressed && styles.pressed,
                                    loading === 'join' && styles.buttonLoading]}
                                onPress={handleJoinByCode}
                                disabled={loading !== null}
                            >
                                {loading === 'join'
                                    ? <ActivityIndicator color="#fff" size="small" />
                                    : <Text style={styles.joinButtonText}>Join</Text>
                                }
                            </Pressable>
                        </View>
                    </View>
                </ScrollView>
            </KeyboardAvoidingView>
        </SafeAreaView>
    );
}

// ── Styles ─────────────────────────────────────────────────────────────────────

const styles = StyleSheet.create({
    flex: { flex: 1 },
    container: {
        flex: 1,
        backgroundColor: colors.surface.dark,
    },
    scroll: {
        paddingHorizontal: 24,
        paddingTop: 24,
        paddingBottom: 48,
    },
    pressed: { opacity: 0.75 },
    buttonLoading: { opacity: 0.6 },

    header: {
        alignItems: 'center',
        marginBottom: 32,
    },
    emoji: { fontSize: 52, marginBottom: 8 },
    title: {
        fontSize: 28,
        fontWeight: '800',
        color: colors.text.primary,
        marginBottom: 6,
    },
    subtitle: {
        fontSize: 13,
        color: colors.text.secondary,
    },

    label: {
        fontSize: 12,
        fontWeight: '700',
        color: colors.text.secondary,
        letterSpacing: 0.6,
        textTransform: 'uppercase',
        marginBottom: 10,
    },
    chipRow: {
        flexDirection: 'row',
        flexWrap: 'wrap',
        gap: 8,
        marginBottom: 28,
    },
    chip: {
        paddingHorizontal: 16,
        paddingVertical: 8,
        borderRadius: 20,
        backgroundColor: colors.surface.darkAlt,
        borderWidth: 1,
        borderColor: colors.grid.cellBorder,
    },
    chipSelected: {
        backgroundColor: colors.primary[700],
        borderColor: colors.primary[500],
    },
    chipText: {
        fontSize: 13,
        fontWeight: '600',
        color: colors.text.secondary,
    },
    chipTextSelected: {
        color: '#fff',
    },

    section: { marginBottom: 28 },
    sectionTitle: {
        fontSize: 12,
        fontWeight: '700',
        color: colors.text.secondary,
        letterSpacing: 0.6,
        textTransform: 'uppercase',
        marginBottom: 12,
    },

    primaryButton: {
        backgroundColor: colors.primary[600],
        paddingVertical: 16,
        borderRadius: 14,
        alignItems: 'center',
        shadowColor: colors.primary[500],
        shadowOffset: { width: 0, height: 3 },
        shadowOpacity: 0.3,
        shadowRadius: 6,
        elevation: 4,
    },
    primaryButtonText: {
        fontSize: 17,
        fontWeight: '700',
        color: '#fff',
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

    codeCard: {
        marginTop: 16,
        backgroundColor: colors.surface.darkAlt,
        borderRadius: 12,
        paddingVertical: 16,
        alignItems: 'center',
        borderWidth: 1,
        borderColor: '#a78bfa',
    },
    codeLabel: {
        fontSize: 12,
        color: colors.text.secondary,
        marginBottom: 6,
    },
    codeValue: {
        fontSize: 28,
        fontWeight: '800',
        color: '#a78bfa',
        letterSpacing: 6,
    },

    joinRow: {
        flexDirection: 'row',
        gap: 10,
    },
    codeInput: {
        flex: 1,
        height: 52,
        backgroundColor: colors.surface.darkAlt,
        borderRadius: 12,
        paddingHorizontal: 16,
        fontSize: 18,
        fontWeight: '700',
        color: colors.text.primary,
        letterSpacing: 4,
        borderWidth: 1,
        borderColor: colors.grid.cellBorder,
    },
    joinButton: {
        width: 80,
        height: 52,
        backgroundColor: colors.primary[600],
        borderRadius: 12,
        alignItems: 'center',
        justifyContent: 'center',
    },
    joinButtonText: {
        fontSize: 15,
        fontWeight: '700',
        color: '#fff',
    },
});
