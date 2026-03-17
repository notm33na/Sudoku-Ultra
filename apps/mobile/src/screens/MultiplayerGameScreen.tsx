/**
 * MultiplayerGameScreen.tsx
 *
 * Real-time multiplayer Sudoku game over WebSocket.
 *
 * State machine (mirrors server room states):
 *   waiting   — connected, opponent not yet joined or both not ready
 *   countdown — 3-2-1 overlay before game starts
 *   playing   — active game; own board is interactive
 *   finished  — game ended; navigate to MatchResultScreen
 *
 * WS messages handled:
 *   room_state         → initial state; detect if game is already in_progress
 *   player_joined      → update player list display
 *   countdown          → show countdown overlay
 *   game_start         → receive puzzle, switch to playing state
 *   opponent_progress  → update opponent's progress bar
 *   game_end           → navigate to MatchResultScreen
 *   chat_message       → add message to chat list
 *   chat_muted         → set muted flag
 *   reconnected        → re-sync state
 *
 * WS messages sent:
 *   ready       — sent on connect
 *   cell_fill   — {cell_index, value}
 *   chat        — {text}
 *   forfeit     — user surrenders
 */

import React, {
    useCallback,
    useEffect,
    useRef,
    useState,
} from 'react';
import {
    ActivityIndicator,
    Alert,
    Pressable,
    SafeAreaView,
    StyleSheet,
    Text,
    View,
} from 'react-native';
import { MultiplayerGameScreenProps } from '../types/navigation';
import { SudokuBoard } from '../components/SudokuBoard';
import { NumberPad } from '../components/NumberPad';
import { ChatDrawer, ChatMessage } from '../components/ChatDrawer';
import { colors } from '../theme/colors';

// ── Config ─────────────────────────────────────────────────────────────────────

const MP_WS_BASE = (process.env.EXPO_PUBLIC_WS_URL ?? 'http://localhost:8080')
    .replace(/^http/, 'ws');
const AUTH_TOKEN = process.env.EXPO_PUBLIC_API_TOKEN ?? '';

// ── Types ──────────────────────────────────────────────────────────────────────

type GameState = 'waiting' | 'countdown' | 'playing' | 'finished';

interface PlayerInfo {
    userId: string;
    displayName: string;
    cellsFilled: number;
    connected: boolean;
    isBot: boolean;
}

// ── Component ──────────────────────────────────────────────────────────────────

export function MultiplayerGameScreen({ route, navigation }: MultiplayerGameScreenProps) {
    const { roomId, myUserId, myDisplayName, difficulty } = route.params;

    // Game state
    const [gameState, setGameState] = useState<GameState>('waiting');
    const [countdown, setCountdown] = useState(3);
    const [puzzle, setPuzzle] = useState<number[]>(Array(81).fill(0));
    const [myBoard, setMyBoard] = useState<number[]>(Array(81).fill(0));
    const [selectedCell, setSelectedCell] = useState<number | null>(null);

    // Players
    const [players, setPlayers] = useState<PlayerInfo[]>([]);
    const opponentRef = useRef<PlayerInfo | null>(null);
    const [opponentProgress, setOpponentProgress] = useState(0);
    const totalToFill = puzzle.filter((v) => v === 0).length;

    // Chat
    const [messages, setMessages] = useState<ChatMessage[]>([]);
    const [isMuted, setIsMuted] = useState(false);

    // Timer
    const [timerMs, setTimerMs] = useState(0);
    const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
    const gameStartTimeRef = useRef<number>(0);

    // WS
    const wsRef = useRef<WebSocket | null>(null);
    const [wsError, setWsError] = useState(false);

    // ── WS helpers ────────────────────────────────────────────────────────────

    const sendMsg = useCallback((type: string, payload?: object) => {
        const ws = wsRef.current;
        if (ws && ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ type, payload }));
        }
    }, []);

    // ── WS connection ─────────────────────────────────────────────────────────

    useEffect(() => {
        const token = AUTH_TOKEN || `${myUserId}:${myDisplayName}`;
        const url = `${MP_WS_BASE}/rooms/${roomId}/ws?token=${encodeURIComponent(token)}`;
        const ws = new WebSocket(url);
        wsRef.current = ws;

        ws.onopen = () => {
            setWsError(false);
            sendMsg('ready');
        };

        ws.onmessage = (event) => {
            try {
                const msg = JSON.parse(event.data as string);
                handleServerMessage(msg.type, msg.payload ?? {});
            } catch {
                // ignore malformed frames
            }
        };

        ws.onerror = () => setWsError(true);
        ws.onclose = () => {
            // Don't show error if game is finished
            if (gameState !== 'finished') {
                setWsError(true);
            }
        };

        return () => {
            ws.close();
            wsRef.current = null;
        };
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [roomId]);

    // ── Message dispatch ──────────────────────────────────────────────────────

    // eslint-disable-next-line react-hooks/exhaustive-deps
    const handleServerMessage = useCallback((type: string, payload: Record<string, unknown>) => {
        switch (type) {
            case 'room_state':
            case 'reconnected': {
                const state = payload.state as string;
                const rawPlayers = payload.players as Record<string, {
                    display_name: string;
                    cells_filled: number;
                    connected: boolean;
                    is_bot: boolean;
                }> | undefined;
                if (rawPlayers) {
                    const list: PlayerInfo[] = Object.entries(rawPlayers).map(([uid, p]) => ({
                        userId: uid,
                        displayName: p.display_name,
                        cellsFilled: p.cells_filled,
                        connected: p.connected,
                        isBot: p.is_bot,
                    }));
                    setPlayers(list);
                    opponentRef.current = list.find((p) => p.userId !== myUserId) ?? null;
                }
                if (state === 'in_progress') {
                    // Reconnect mid-game — puzzle should have been received earlier
                    setGameState('playing');
                    if (!gameStartTimeRef.current) gameStartTimeRef.current = Date.now();
                } else if (state === 'countdown') {
                    setGameState('countdown');
                } else {
                    setGameState('waiting');
                }
                break;
            }
            case 'player_joined': {
                const uid = payload.user_id as string;
                const name = payload.display_name as string;
                if (uid !== myUserId) {
                    const info: PlayerInfo = {
                        userId: uid,
                        displayName: name,
                        cellsFilled: 0,
                        connected: true,
                        isBot: false,
                    };
                    opponentRef.current = info;
                    setPlayers((prev) => [...prev.filter((p) => p.userId !== uid), info]);
                }
                break;
            }
            case 'countdown': {
                setGameState('countdown');
                setCountdown((payload.seconds as number) ?? 3);
                break;
            }
            case 'game_start': {
                const rawPuzzle = payload.puzzle as number[] | undefined;
                if (rawPuzzle) {
                    setPuzzle(rawPuzzle);
                    setMyBoard(rawPuzzle.slice());
                }
                setGameState('playing');
                gameStartTimeRef.current = Date.now();
                break;
            }
            case 'opponent_progress': {
                const uid = payload.user_id as string;
                if (uid !== myUserId) {
                    const filled = (payload.cells_filled as number) ?? 0;
                    setOpponentProgress(filled);
                    setPlayers((prev) =>
                        prev.map((p) =>
                            p.userId === uid ? { ...p, cellsFilled: filled } : p,
                        ),
                    );
                }
                break;
            }
            case 'game_end': {
                const winnerId = payload.winner_id as string;
                const reason = (payload.reason as string) ?? 'completed';
                setGameState('finished');
                if (timerRef.current) {
                    clearInterval(timerRef.current);
                    timerRef.current = null;
                }
                const durationMs = gameStartTimeRef.current
                    ? Date.now() - gameStartTimeRef.current
                    : 0;
                const opponent = opponentRef.current;
                navigation.replace('MatchResult', {
                    won: winnerId === myUserId,
                    endReason: reason,
                    eloBefore: 1200, // placeholder — real value fetched from rating service
                    eloAfter: 1200,
                    eloDelta: 0,
                    opponentName: opponent?.displayName ?? 'Opponent',
                    difficulty,
                    durationMs,
                });
                break;
            }
            case 'chat_message': {
                const msg: ChatMessage = {
                    id: `${payload.sender_id as string}-${payload.timestamp as string}`,
                    senderID: payload.sender_id as string,
                    displayName: payload.display_name as string,
                    text: payload.text as string,
                    timestamp: payload.timestamp as string,
                };
                setMessages((prev) => [...prev, msg]);
                break;
            }
            case 'chat_muted': {
                setIsMuted(true);
                break;
            }
            default:
                break;
        }
    }, [myUserId, navigation, difficulty]);

    // ── Timer ─────────────────────────────────────────────────────────────────

    useEffect(() => {
        if (gameState === 'playing') {
            timerRef.current = setInterval(() => {
                setTimerMs((ms) => ms + 1000);
            }, 1000);
        } else {
            if (timerRef.current) {
                clearInterval(timerRef.current);
                timerRef.current = null;
            }
        }
        return () => {
            if (timerRef.current) {
                clearInterval(timerRef.current);
                timerRef.current = null;
            }
        };
    }, [gameState]);

    // ── Game interactions ─────────────────────────────────────────────────────

    const handleCellPress = useCallback((row: number, col: number) => {
        const idx = row * 9 + col;
        if (puzzle[idx] !== 0) return; // given cell, not editable
        setSelectedCell(idx);
    }, [puzzle]);

    const handleNumberPress = useCallback((value: number) => {
        if (selectedCell === null || gameState !== 'playing') return;
        if (puzzle[selectedCell] !== 0) return;

        setMyBoard((prev) => {
            const next = [...prev];
            next[selectedCell] = value;
            return next;
        });
        sendMsg('cell_fill', { cell_index: selectedCell, value });
    }, [selectedCell, gameState, puzzle, sendMsg]);

    const handleClearPress = useCallback(() => {
        if (selectedCell === null || gameState !== 'playing') return;
        if (puzzle[selectedCell] !== 0) return;
        setMyBoard((prev) => {
            const next = [...prev];
            next[selectedCell] = 0;
            return next;
        });
        sendMsg('cell_fill', { cell_index: selectedCell, value: 0 });
    }, [selectedCell, gameState, puzzle, sendMsg]);

    const handleSendChat = useCallback((text: string) => {
        sendMsg('chat', { text });
    }, [sendMsg]);

    const handleForfeit = useCallback(() => {
        Alert.alert(
            'Forfeit',
            'Are you sure you want to surrender?',
            [
                { text: 'Cancel', style: 'cancel' },
                {
                    text: 'Forfeit',
                    style: 'destructive',
                    onPress: () => sendMsg('forfeit'),
                },
            ],
        );
    }, [sendMsg]);

    // ── Derived board for SudokuBoard (uses row/col not flat index) ───────────

    const boardGrid: number[][] = Array.from({ length: 9 }, (_, r) =>
        myBoard.slice(r * 9, r * 9 + 9),
    );
    const selectedRow = selectedCell !== null ? Math.floor(selectedCell / 9) : null;
    const selectedCol = selectedCell !== null ? selectedCell % 9 : null;

    // ── Timer format ──────────────────────────────────────────────────────────

    const totalSec = Math.floor(timerMs / 1000);
    const timerStr = `${String(Math.floor(totalSec / 60)).padStart(2, '0')}:${String(totalSec % 60).padStart(2, '0')}`;

    // ── Opponent info ─────────────────────────────────────────────────────────

    const opponent = players.find((p) => p.userId !== myUserId);
    const opponentName = opponent?.displayName ?? 'Waiting…';
    const progressPct = totalToFill > 0 ? Math.min(opponentProgress / totalToFill, 1) : 0;
    const myFilledCount = myBoard.filter((v, i) => puzzle[i] === 0 && v !== 0).length;
    const myProgressPct = totalToFill > 0 ? Math.min(myFilledCount / totalToFill, 1) : 0;

    // ── Renders ───────────────────────────────────────────────────────────────

    if (wsError) {
        return (
            <SafeAreaView style={[styles.container, styles.center]}>
                <Text style={styles.errorEmoji}>📡</Text>
                <Text style={styles.errorText}>Connection lost</Text>
                <Pressable style={styles.retryButton} onPress={() => navigation.goBack()}>
                    <Text style={styles.retryButtonText}>Back to Lobby</Text>
                </Pressable>
            </SafeAreaView>
        );
    }

    // ── Waiting overlay ───────────────────────────────────────────────────────

    if (gameState === 'waiting') {
        return (
            <SafeAreaView style={[styles.container, styles.center]}>
                <Text style={styles.waitingEmoji}>⏳</Text>
                <Text style={styles.waitingTitle}>Waiting for opponent…</Text>
                {inviteCodeFromPlayers(players) ? (
                    <View style={styles.codeCard}>
                        <Text style={styles.codeLabel}>Share this code:</Text>
                        <Text style={styles.codeValue}>{inviteCodeFromPlayers(players)}</Text>
                    </View>
                ) : null}
                <ActivityIndicator color="#a78bfa" style={styles.spinner} />
                <Pressable style={styles.forfeitButton} onPress={() => navigation.goBack()}>
                    <Text style={styles.forfeitText}>Cancel</Text>
                </Pressable>
            </SafeAreaView>
        );
    }

    // ── Countdown overlay ─────────────────────────────────────────────────────

    if (gameState === 'countdown') {
        return (
            <SafeAreaView style={[styles.container, styles.center]}>
                <Text style={styles.countdownNumber}>{countdown}</Text>
                <Text style={styles.countdownLabel}>Get Ready!</Text>
                <Text style={styles.vsText}>
                    {myDisplayName}  vs  {opponentName}
                </Text>
            </SafeAreaView>
        );
    }

    // ── Main game UI ──────────────────────────────────────────────────────────

    return (
        <SafeAreaView style={styles.container}>
            {/* Header */}
            <View style={styles.header}>
                <View style={styles.headerLeft}>
                    <Text style={styles.diffBadge}>{difficulty}</Text>
                </View>
                <Text style={styles.timer}>{timerStr}</Text>
                <Pressable style={styles.forfeitBtn} onPress={handleForfeit}>
                    <Text style={styles.forfeitBtnText}>⚑</Text>
                </Pressable>
            </View>

            {/* Opponent progress bar */}
            <View style={styles.opponentBar}>
                <Text style={styles.opponentName} numberOfLines={1}>
                    🤺 {opponentName}
                </Text>
                <View style={styles.progressTrack}>
                    <View style={[styles.progressFill, styles.progressEnemy, { width: `${progressPct * 100}%` as `${number}%` }]} />
                </View>
                <Text style={styles.progressLabel}>{opponentProgress}/{totalToFill}</Text>
            </View>

            {/* My progress bar */}
            <View style={styles.myBar}>
                <Text style={styles.myName} numberOfLines={1}>
                    🙋 {myDisplayName}
                </Text>
                <View style={styles.progressTrack}>
                    <View style={[styles.progressFill, styles.progressMine, { width: `${myProgressPct * 100}%` as `${number}%` }]} />
                </View>
                <Text style={styles.progressLabel}>{myFilledCount}/{totalToFill}</Text>
            </View>

            {/* Board */}
            <SudokuBoard
                grid={boardGrid}
                selectedRow={selectedRow}
                selectedCol={selectedCol}
                onCellPress={handleCellPress}
            />

            {/* Number Pad */}
            <NumberPad
                onNumberPress={handleNumberPress}
                onClearPress={handleClearPress}
                notesMode={false}
            />

            {/* Chat drawer */}
            <ChatDrawer
                messages={messages}
                isMuted={isMuted}
                myUserID={myUserId}
                onSend={handleSendChat}
            />
        </SafeAreaView>
    );
}

// ── Helpers ────────────────────────────────────────────────────────────────────

/** Extract room code if the room view has it (private rooms). */
function inviteCodeFromPlayers(_players: PlayerInfo[]): string | null {
    // Code is only present in the room view, not PlayerInfo.
    // If needed, it would be stored in a separate state variable.
    return null;
}

// ── Styles ─────────────────────────────────────────────────────────────────────

const styles = StyleSheet.create({
    container: {
        flex: 1,
        backgroundColor: colors.surface.dark,
    },
    center: {
        alignItems: 'center',
        justifyContent: 'center',
    },

    // Error state
    errorEmoji: { fontSize: 48, marginBottom: 12 },
    errorText: { fontSize: 18, color: colors.text.secondary, marginBottom: 24 },
    retryButton: {
        backgroundColor: colors.primary[600],
        paddingHorizontal: 24,
        paddingVertical: 12,
        borderRadius: 10,
    },
    retryButtonText: { color: '#fff', fontWeight: '700', fontSize: 15 },

    // Waiting
    waitingEmoji: { fontSize: 52, marginBottom: 16 },
    waitingTitle: { fontSize: 20, fontWeight: '700', color: colors.text.primary, marginBottom: 24 },
    spinner: { marginTop: 16 },
    codeCard: {
        backgroundColor: colors.surface.darkAlt,
        borderRadius: 12,
        padding: 16,
        alignItems: 'center',
        borderWidth: 1,
        borderColor: '#a78bfa',
        marginBottom: 8,
    },
    codeLabel: { fontSize: 12, color: colors.text.secondary, marginBottom: 6 },
    codeValue: { fontSize: 26, fontWeight: '800', color: '#a78bfa', letterSpacing: 6 },
    forfeitButton: { marginTop: 32, paddingHorizontal: 24, paddingVertical: 10 },
    forfeitText: { color: colors.text.muted, fontSize: 15 },

    // Countdown
    countdownNumber: {
        fontSize: 96,
        fontWeight: '900',
        color: colors.primary[400],
        lineHeight: 110,
    },
    countdownLabel: { fontSize: 22, fontWeight: '700', color: colors.text.primary, marginBottom: 16 },
    vsText: { fontSize: 16, color: colors.text.secondary },

    // Header
    header: {
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'space-between',
        paddingHorizontal: 16,
        paddingVertical: 8,
    },
    headerLeft: { flex: 1 },
    diffBadge: {
        fontSize: 13,
        fontWeight: '700',
        color: colors.primary[400],
        backgroundColor: colors.primary[900],
        paddingHorizontal: 10,
        paddingVertical: 4,
        borderRadius: 8,
        overflow: 'hidden',
        alignSelf: 'flex-start',
    },
    timer: {
        flex: 1,
        textAlign: 'center',
        fontSize: 20,
        fontWeight: '700',
        color: colors.text.primary,
        fontVariant: ['tabular-nums'],
    },
    forfeitBtn: { flex: 1, alignItems: 'flex-end', paddingRight: 4 },
    forfeitBtnText: { fontSize: 22, color: colors.text.muted },

    // Progress bars
    opponentBar: {
        flexDirection: 'row',
        alignItems: 'center',
        paddingHorizontal: 16,
        paddingVertical: 4,
        gap: 8,
    },
    myBar: {
        flexDirection: 'row',
        alignItems: 'center',
        paddingHorizontal: 16,
        paddingVertical: 4,
        gap: 8,
        marginBottom: 4,
    },
    opponentName: {
        width: 90,
        fontSize: 12,
        fontWeight: '600',
        color: colors.error,
    },
    myName: {
        width: 90,
        fontSize: 12,
        fontWeight: '600',
        color: colors.success,
    },
    progressTrack: {
        flex: 1,
        height: 6,
        backgroundColor: colors.surface.darkAlt,
        borderRadius: 3,
        overflow: 'hidden',
    },
    progressFill: {
        height: '100%',
        borderRadius: 3,
    },
    progressEnemy: { backgroundColor: colors.error },
    progressMine: { backgroundColor: colors.success },
    progressLabel: {
        width: 36,
        fontSize: 11,
        color: colors.text.muted,
        textAlign: 'right',
        fontVariant: ['tabular-nums'],
    },
});
