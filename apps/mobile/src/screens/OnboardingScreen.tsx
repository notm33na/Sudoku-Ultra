/**
 * OnboardingScreen — 9-step first-time tutorial.
 *
 * Steps:
 *   0  Welcome            info        — full-screen welcome
 *   1  The Grid           board-demo  — highlight rows/cols/boxes
 *   2  The Rules          board-demo  — show a completed 3×3 box
 *   3  Select a Cell      interactive — user must tap the highlighted cell
 *   4  Enter a Digit      interactive — user fills the selected cell
 *   5  Pencil Marks       info        — candidate note-taking
 *   6  Hints              info        — hint system
 *   7  Difficulty Levels  info        — easy → extreme
 *   8  You're Ready!      complete    — final congratulations
 *
 * Each step fetches an LLM-generated tip from ml-service.
 * Progress is persisted via game-service after each step.
 * Users can skip at any time.
 */

import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
    View,
    Text,
    TouchableOpacity,
    StyleSheet,
    Animated,
    Dimensions,
    ScrollView,
    ActivityIndicator,
} from 'react-native';
import { OnboardingScreenProps } from '../types/navigation';

const { width: SW } = Dimensions.get('window');

const GAME_API = process.env.EXPO_PUBLIC_API_URL ?? 'http://localhost:3001';
const ML_API = process.env.EXPO_PUBLIC_ML_URL ?? 'http://localhost:3003';
const TOKEN = process.env.EXPO_PUBLIC_API_TOKEN ?? '';

const TOTAL_STEPS = 9;

// ── Step definitions ──────────────────────────────────────────────────────────

type StepType = 'info' | 'board-demo' | 'interactive' | 'complete';

interface StepDef {
    title: string;
    content: string;
    type: StepType;
    emoji: string;
    /** For board-demo: cell indices to highlight */
    highlightCells?: number[];
    /** For board-demo: board values (0 = empty shown as dot) */
    demoBoard?: number[];
    /** For interactive: cell index the user must tap */
    targetCell?: number;
    /** For interactive step 4: digit the user must enter */
    targetDigit?: number;
}

// Simple demo board — a mostly-solved grid
const DEMO_BOARD = [
    1, 2, 3,  4, 5, 6,  7, 8, 9,
    4, 5, 6,  7, 8, 9,  1, 2, 3,
    7, 8, 9,  1, 2, 3,  4, 5, 6,
    2, 1, 4,  3, 6, 5,  8, 9, 7,
    3, 6, 5,  8, 9, 7,  2, 1, 4,
    8, 9, 7,  2, 1, 4,  3, 6, 5,
    5, 3, 1,  6, 4, 2,  9, 7, 8,
    6, 4, 2,  9, 7, 8,  5, 3, 1,
    9, 7, 8,  5, 3, 0,  6, 4, 2,   // cell 77 empty for interaction
];

const STEPS: StepDef[] = [
    {
        title: 'Welcome to Sudoku Ultra',
        content:
            'Sudoku is the world\'s most popular logic puzzle. ' +
            'No maths, no guessing — just pure deduction. ' +
            'This short tutorial will have you solving puzzles in minutes.',
        type: 'info',
        emoji: '👋',
    },
    {
        title: 'The 9×9 Grid',
        content:
            'Every puzzle is a 9×9 grid split into nine 3×3 boxes. ' +
            'You\'ll work with rows (left→right), columns (top→bottom), ' +
            'and boxes (the thick-bordered 3×3 regions).',
        type: 'board-demo',
        emoji: '🔲',
        demoBoard: DEMO_BOARD,
        // Highlight top-left box
        highlightCells: [0,1,2, 9,10,11, 18,19,20],
    },
    {
        title: 'The Golden Rule',
        content:
            'Each row, each column, and each 3×3 box must contain ' +
            'every digit from 1 to 9 exactly once. ' +
            'That\'s the only rule — everything else follows from logic.',
        type: 'board-demo',
        emoji: '📏',
        demoBoard: DEMO_BOARD,
        // Highlight row 0
        highlightCells: [0,1,2,3,4,5,6,7,8],
    },
    {
        title: 'Tap to Select a Cell',
        content:
            'Tap the highlighted cell to select it. ' +
            'The cell\'s row, column, and box will light up to show you its constraint zone.',
        type: 'interactive',
        emoji: '👆',
        demoBoard: DEMO_BOARD,
        targetCell: 77,  // the empty cell
    },
    {
        title: 'Enter a Digit',
        content:
            'The highlighted cell is empty. Use the number pad below to fill it in with the correct digit. ' +
            'Check its row, column, and box — only one digit fits!',
        type: 'interactive',
        emoji: '✏️',
        demoBoard: DEMO_BOARD,
        targetCell: 77,
        targetDigit: 1,
    },
    {
        title: 'Pencil Marks',
        content:
            'Not sure which digit goes where? Tap the pencil icon to enter candidate mode. ' +
            'You can jot multiple possible digits in a cell without committing to one.',
        type: 'info',
        emoji: '✏️',
    },
    {
        title: 'Stuck? Use a Hint',
        content:
            'The hint button analyses your board and suggests the next logical technique — ' +
            'it points you in the right direction without giving away the answer.',
        type: 'info',
        emoji: '💡',
    },
    {
        title: 'Choose Your Challenge',
        content:
            'Puzzles range from Easy (naked singles only) to Extreme (advanced chains). ' +
            'Start with Easy and work your way up as your skills grow.',
        type: 'info',
        emoji: '🏆',
    },
    {
        title: "You're Ready!",
        content:
            'You know everything you need to start solving. ' +
            'Remember — every puzzle has exactly one solution reachable by pure logic. ' +
            'Good luck!',
        type: 'complete',
        emoji: '🎉',
    },
];

// ── Mini demo board ───────────────────────────────────────────────────────────

const MINI = 28;

function DemoBoard({
    board,
    highlightCells,
    targetCell,
    selectedCell,
    onCellPress,
}: {
    board: number[];
    highlightCells?: number[];
    targetCell?: number;
    selectedCell?: number | null;
    onCellPress?: (idx: number) => void;
}) {
    const hl = new Set(highlightCells ?? []);

    // If a cell is selected, also highlight its row, col, and box
    const selected = selectedCell ?? -1;
    const selPeers = new Set<number>();
    if (selected >= 0) {
        const sr = Math.floor(selected / 9);
        const sc = selected % 9;
        const br = Math.floor(sr / 3) * 3;
        const bc = Math.floor(sc / 3) * 3;
        for (let i = 0; i < 9; i++) selPeers.add(sr * 9 + i);
        for (let i = 0; i < 9; i++) selPeers.add(i * 9 + sc);
        for (let dr = 0; dr < 3; dr++)
            for (let dc = 0; dc < 3; dc++)
                selPeers.add((br + dr) * 9 + (bc + dc));
    }

    return (
        <View style={demoStyles.board}>
            {Array.from({ length: 9 }, (_, row) => (
                <View key={row} style={demoStyles.row}>
                    {Array.from({ length: 9 }, (_, col) => {
                        const idx = row * 9 + col;
                        const val = board[idx];
                        const isHL = hl.has(idx);
                        const isSel = idx === selected;
                        const isPeer = selPeers.has(idx) && !isSel;
                        const isTarget = idx === targetCell;
                        const thick = (col === 2 || col === 5);
                        const thickB = (row === 2 || row === 5);
                        return (
                            <TouchableOpacity
                                key={col}
                                style={[
                                    demoStyles.cell,
                                    isHL && demoStyles.cellHL,
                                    isPeer && demoStyles.cellPeer,
                                    isSel && demoStyles.cellSel,
                                    isTarget && !isSel && demoStyles.cellTarget,
                                    thick && demoStyles.borderR,
                                    thickB && demoStyles.borderB,
                                ]}
                                onPress={() => onCellPress?.(idx)}
                                disabled={!onCellPress}
                            >
                                <Text style={[
                                    demoStyles.cellText,
                                    isSel && demoStyles.cellTextSel,
                                    isTarget && !isSel && demoStyles.cellTextTarget,
                                ]}>
                                    {val !== 0 ? val : isTarget ? '?' : ''}
                                </Text>
                            </TouchableOpacity>
                        );
                    })}
                </View>
            ))}
        </View>
    );
}

const demoStyles = StyleSheet.create({
    board: { borderWidth: 2, borderColor: '#475569', alignSelf: 'center', marginVertical: 12 },
    row: { flexDirection: 'row' },
    cell: {
        width: MINI, height: MINI, borderWidth: 0.5, borderColor: '#334155',
        justifyContent: 'center', alignItems: 'center', backgroundColor: '#1e293b',
    },
    cellHL: { backgroundColor: 'rgba(99,102,241,0.2)' },
    cellPeer: { backgroundColor: 'rgba(99,102,241,0.08)' },
    cellSel: { backgroundColor: 'rgba(99,102,241,0.5)', borderColor: '#6366f1', borderWidth: 1.5 },
    cellTarget: { backgroundColor: 'rgba(245,158,11,0.3)', borderColor: '#f59e0b', borderWidth: 1.5 },
    cellText: { fontSize: 10, color: '#94a3b8', fontWeight: '500' },
    cellTextSel: { color: '#fff', fontWeight: '700' },
    cellTextTarget: { color: '#f59e0b', fontWeight: '700' },
    borderR: { borderRightWidth: 2, borderRightColor: '#475569' },
    borderB: { borderBottomWidth: 2, borderBottomColor: '#475569' },
});

// ── Number pad (step 4 only) ───────────────────────────────────────────────────

function NumberPad({ onPress }: { onPress: (d: number) => void }) {
    return (
        <View style={padStyles.row}>
            {[1, 2, 3, 4, 5, 6, 7, 8, 9].map((d) => (
                <TouchableOpacity key={d} style={padStyles.btn} onPress={() => onPress(d)}>
                    <Text style={padStyles.btnText}>{d}</Text>
                </TouchableOpacity>
            ))}
        </View>
    );
}

const padStyles = StyleSheet.create({
    row: { flexDirection: 'row', justifyContent: 'center', flexWrap: 'wrap', gap: 8, marginTop: 8 },
    btn: {
        width: 36, height: 36, borderRadius: 8,
        backgroundColor: '#1e293b', borderWidth: 1, borderColor: '#334155',
        justifyContent: 'center', alignItems: 'center',
    },
    btnText: { fontSize: 16, fontWeight: '700', color: '#e2e8f0' },
});

// ── Tip bubble ────────────────────────────────────────────────────────────────

function TipBubble({ tip, loading }: { tip: string; loading: boolean }) {
    return (
        <View style={tipStyles.bubble}>
            <Text style={tipStyles.icon}>🤖</Text>
            {loading
                ? <ActivityIndicator size="small" color="#6366f1" style={{ flex: 1 }} />
                : <Text style={tipStyles.text}>{tip}</Text>
            }
        </View>
    );
}

const tipStyles = StyleSheet.create({
    bubble: {
        flexDirection: 'row', alignItems: 'flex-start', gap: 10,
        backgroundColor: '#1e293b', borderRadius: 12, padding: 12,
        borderLeftWidth: 3, borderLeftColor: '#6366f1', marginTop: 16,
    },
    icon: { fontSize: 18 },
    text: { flex: 1, fontSize: 13, color: '#94a3b8', lineHeight: 20, fontStyle: 'italic' },
});

// ── Main screen ───────────────────────────────────────────────────────────────

export default function OnboardingScreen({ navigation }: OnboardingScreenProps) {
    const [stepIdx, setStepIdx] = useState(0);
    const [tip, setTip] = useState('');
    const [tipLoading, setTipLoading] = useState(false);
    const [selectedCell, setSelectedCell] = useState<number | null>(null);
    const [cellFilled, setCellFilled] = useState(false);
    const [board, setBoard] = useState<number[]>([...DEMO_BOARD]);
    const [submitting, setSubmitting] = useState(false);

    const slideAnim = useRef(new Animated.Value(0)).current;
    const fadeAnim = useRef(new Animated.Value(1)).current;

    const step = STEPS[stepIdx];

    // Fetch LLM narration tip for current step
    const fetchTip = useCallback(async (idx: number) => {
        setTipLoading(true);
        setTip('');
        try {
            const s = STEPS[idx];
            const res = await fetch(`${ML_API}/api/v1/onboarding/narrate`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    step_index: idx,
                    step_title: s.title,
                    step_content: s.content,
                }),
            });
            const data = await res.json();
            setTip(data.tip ?? '');
        } catch {
            setTip(STEPS[idx].content);
        } finally {
            setTipLoading(false);
        }
    }, []);

    useEffect(() => {
        fetchTip(stepIdx);
        // Reset interactive state on step change
        setSelectedCell(null);
        setCellFilled(false);
        setBoard([...DEMO_BOARD]);
    }, [stepIdx, fetchTip]);

    const persistStep = useCallback(async (idx: number) => {
        setSubmitting(true);
        try {
            await fetch(`${GAME_API}/api/onboarding/steps/${idx}/complete`, {
                method: 'POST',
                headers: { Authorization: `Bearer ${TOKEN}`, 'Content-Type': 'application/json' },
            });
        } catch { /* non-blocking */ }
        finally { setSubmitting(false); }
    }, []);

    const skipOnboarding = useCallback(async () => {
        try {
            await fetch(`${GAME_API}/api/onboarding/skip`, {
                method: 'POST',
                headers: { Authorization: `Bearer ${TOKEN}` },
            });
        } catch { /* non-blocking */ }
        navigation.replace('Home');
    }, [navigation]);

    const animateTransition = useCallback((cb: () => void) => {
        Animated.parallel([
            Animated.timing(fadeAnim, { toValue: 0, duration: 180, useNativeDriver: true }),
            Animated.timing(slideAnim, { toValue: -30, duration: 180, useNativeDriver: true }),
        ]).start(() => {
            cb();
            slideAnim.setValue(30);
            Animated.parallel([
                Animated.timing(fadeAnim, { toValue: 1, duration: 220, useNativeDriver: true }),
                Animated.timing(slideAnim, { toValue: 0, duration: 220, useNativeDriver: true }),
            ]).start();
        });
    }, [fadeAnim, slideAnim]);

    const advance = useCallback(async () => {
        await persistStep(stepIdx);
        if (stepIdx >= TOTAL_STEPS - 1) {
            navigation.replace('Home');
        } else {
            animateTransition(() => setStepIdx((i) => i + 1));
        }
    }, [stepIdx, persistStep, navigation, animateTransition]);

    // Interaction: step 3 — select a cell
    const handleCellPress = useCallback((idx: number) => {
        if (step.type !== 'interactive') return;
        setSelectedCell(idx);
        if (idx === step.targetCell && step.targetDigit === undefined) {
            // Step 3 complete: cell selected
            setTimeout(advance, 600);
        }
    }, [step, advance]);

    // Interaction: step 4 — enter a digit
    const handleDigitPress = useCallback((d: number) => {
        if (step.targetDigit === undefined) return;
        if (d === step.targetDigit) {
            const newBoard = [...board];
            newBoard[step.targetCell!] = d;
            setBoard(newBoard);
            setCellFilled(true);
            setTimeout(advance, 700);
        }
    }, [step, board, advance]);

    // Can the user press Next?
    const canAdvance =
        step.type !== 'interactive' ||
        (step.targetDigit === undefined ? selectedCell === step.targetCell : cellFilled);

    return (
        <View style={styles.container}>
            {/* Skip */}
            <TouchableOpacity style={styles.skipBtn} onPress={skipOnboarding}>
                <Text style={styles.skipText}>Skip</Text>
            </TouchableOpacity>

            {/* Progress dots */}
            <View style={styles.dots}>
                {Array.from({ length: TOTAL_STEPS }, (_, i) => (
                    <View
                        key={i}
                        style={[
                            styles.dot,
                            i < stepIdx && styles.dotDone,
                            i === stepIdx && styles.dotActive,
                        ]}
                    />
                ))}
            </View>

            {/* Animated step content */}
            <Animated.View
                style={[
                    styles.stepCard,
                    { opacity: fadeAnim, transform: [{ translateY: slideAnim }] },
                ]}
            >
                <ScrollView
                    contentContainerStyle={styles.scrollContent}
                    showsVerticalScrollIndicator={false}
                >
                    <Text style={styles.emoji}>{step.emoji}</Text>
                    <Text style={styles.title}>{step.title}</Text>
                    <Text style={styles.content}>{step.content}</Text>

                    {/* Board demo / interactive */}
                    {(step.type === 'board-demo' || step.type === 'interactive') && step.demoBoard && (
                        <DemoBoard
                            board={board}
                            highlightCells={step.highlightCells}
                            targetCell={step.targetCell}
                            selectedCell={selectedCell}
                            onCellPress={step.type === 'interactive' ? handleCellPress : undefined}
                        />
                    )}

                    {/* Number pad for step 4 */}
                    {step.type === 'interactive' && step.targetDigit !== undefined && selectedCell === step.targetCell && (
                        <>
                            <Text style={styles.pickLabel}>What digit goes here?</Text>
                            <NumberPad onPress={handleDigitPress} />
                        </>
                    )}

                    {/* Interactive prompt */}
                    {step.type === 'interactive' && selectedCell !== step.targetCell && (
                        <Text style={styles.interactivePrompt}>
                            {step.targetDigit === undefined
                                ? '👆 Tap the highlighted cell'
                                : '👆 Tap the highlighted cell first'}
                        </Text>
                    )}

                    {/* LLM tip bubble */}
                    <TipBubble tip={tip} loading={tipLoading} />
                </ScrollView>
            </Animated.View>

            {/* Bottom nav */}
            <View style={styles.bottomBar}>
                {stepIdx > 0 && (
                    <TouchableOpacity
                        style={styles.backBtn}
                        onPress={() => animateTransition(() => setStepIdx((i) => i - 1))}
                    >
                        <Text style={styles.backBtnText}>← Back</Text>
                    </TouchableOpacity>
                )}
                <View style={{ flex: 1 }} />
                <TouchableOpacity
                    style={[styles.nextBtn, !canAdvance && styles.nextBtnDisabled]}
                    onPress={advance}
                    disabled={!canAdvance || submitting}
                >
                    <Text style={styles.nextBtnText}>
                        {stepIdx >= TOTAL_STEPS - 1
                            ? "Let's Play! 🎮"
                            : step.type === 'interactive'
                                ? canAdvance ? 'Next →' : '...'
                                : 'Next →'}
                    </Text>
                </TouchableOpacity>
            </View>
        </View>
    );
}

// ── Styles ────────────────────────────────────────────────────────────────────

const styles = StyleSheet.create({
    container: { flex: 1, backgroundColor: '#0f172a' },

    skipBtn: { position: 'absolute', top: 52, right: 20, zIndex: 10, padding: 6 },
    skipText: { color: '#475569', fontSize: 14 },

    dots: {
        flexDirection: 'row', justifyContent: 'center', gap: 6,
        marginTop: 56, marginBottom: 8,
    },
    dot: { width: 7, height: 7, borderRadius: 4, backgroundColor: '#334155' },
    dotDone: { backgroundColor: '#6366f1' },
    dotActive: { width: 20, backgroundColor: '#a78bfa' },

    stepCard: { flex: 1, marginHorizontal: 20 },
    scrollContent: { paddingBottom: 20 },

    emoji: { fontSize: 48, textAlign: 'center', marginTop: 16, marginBottom: 8 },
    title: { fontSize: 24, fontWeight: '800', color: '#f1f5f9', textAlign: 'center', marginBottom: 12 },
    content: { fontSize: 15, color: '#94a3b8', lineHeight: 24, textAlign: 'center' },

    interactivePrompt: {
        textAlign: 'center', color: '#f59e0b', fontWeight: '600',
        fontSize: 14, marginTop: 8,
    },
    pickLabel: { textAlign: 'center', color: '#94a3b8', fontSize: 13, marginTop: 8 },

    bottomBar: {
        flexDirection: 'row', alignItems: 'center',
        padding: 20, paddingBottom: 36,
        borderTopWidth: 1, borderTopColor: '#1e293b',
    },
    backBtn: { paddingHorizontal: 16, paddingVertical: 10 },
    backBtnText: { color: '#475569', fontSize: 15, fontWeight: '600' },
    nextBtn: {
        backgroundColor: '#6366f1', paddingHorizontal: 26, paddingVertical: 12,
        borderRadius: 12,
    },
    nextBtnDisabled: { backgroundColor: '#334155' },
    nextBtnText: { color: '#fff', fontWeight: '700', fontSize: 16 },
});
