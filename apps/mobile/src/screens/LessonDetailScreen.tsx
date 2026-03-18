/**
 * LessonDetailScreen — step-by-step lesson flow.
 *
 * Three step types:
 *   read     — scrollable text card
 *   example  — text card with optional cell highlights on a mini board
 *   practice — mini 9×9 board; user taps the highlighted cell and picks a digit
 *
 * On completing the final step, shows an XP banner and navigates back.
 */

import React, { useCallback, useEffect, useState } from 'react';
import {
    View,
    Text,
    ScrollView,
    TouchableOpacity,
    StyleSheet,
    ActivityIndicator,
    Animated,
    Alert,
} from 'react-native';
import { LessonDetailScreenProps } from '../types/navigation';

const API = process.env.EXPO_PUBLIC_API_URL ?? 'http://localhost:3001';
const TOKEN = process.env.EXPO_PUBLIC_API_TOKEN ?? '';

// ── Types ─────────────────────────────────────────────────────────────────────

interface LessonStep {
    stepNumber: number;
    type: 'read' | 'example' | 'practice';
    title: string;
    content: string;
    puzzle?: number[];
    solution?: number[];
    targetCell?: number;
    targetValue?: number;
    highlightCells?: number[];
}

interface LessonDetail {
    id: string;
    title: string;
    difficulty: number;
    xpReward: number;
    description: string;
    steps: LessonStep[];
    progress: {
        stepsComplete: number;
        completed: boolean;
        xpAwarded: number;
    } | null;
}

interface StepResult {
    stepsComplete: number;
    totalSteps: number;
    lessonCompleted: boolean;
    xpAwarded: number;
    totalXp: number;
    newBadges: Array<{ id: string; title: string; icon: string }>;
}

// ── Mini board ────────────────────────────────────────────────────────────────

const MINI_SIZE = 30;

function MiniBoard({
    board,
    highlightCells = [],
    targetCell,
    onCellPress,
}: {
    board: number[];
    highlightCells: number[];
    targetCell?: number;
    onCellPress?: (idx: number) => void;
}) {
    const highlightSet = new Set(highlightCells);
    return (
        <View style={miniStyles.board}>
            {Array.from({ length: 9 }, (_, row) => (
                <View key={row} style={miniStyles.row}>
                    {Array.from({ length: 9 }, (_, col) => {
                        const idx = row * 9 + col;
                        const value = board[idx];
                        const isHL = highlightSet.has(idx);
                        const isTarget = idx === targetCell;
                        const isBoxRight = col === 2 || col === 5;
                        const isBoxBottom = row === 2 || row === 5;
                        return (
                            <TouchableOpacity
                                key={col}
                                style={[
                                    miniStyles.cell,
                                    isHL && miniStyles.cellHL,
                                    isTarget && miniStyles.cellTarget,
                                    isBoxRight && miniStyles.borderRight,
                                    isBoxBottom && miniStyles.borderBottom,
                                ]}
                                onPress={() => onCellPress?.(idx)}
                                disabled={!isTarget}
                            >
                                <Text style={[miniStyles.cellText, isTarget && miniStyles.cellTextTarget]}>
                                    {value !== 0 ? value : ''}
                                </Text>
                            </TouchableOpacity>
                        );
                    })}
                </View>
            ))}
        </View>
    );
}

const miniStyles = StyleSheet.create({
    board: {
        borderWidth: 2,
        borderColor: '#475569',
        alignSelf: 'center',
        marginVertical: 12,
    },
    row: { flexDirection: 'row' },
    cell: {
        width: MINI_SIZE,
        height: MINI_SIZE,
        borderWidth: 0.5,
        borderColor: '#334155',
        justifyContent: 'center',
        alignItems: 'center',
        backgroundColor: '#1e293b',
    },
    cellHL: { backgroundColor: 'rgba(245,158,11,0.25)' },
    cellTarget: {
        backgroundColor: 'rgba(99,102,241,0.35)',
        borderColor: '#6366f1',
        borderWidth: 1.5,
    },
    cellText: { fontSize: 11, color: '#94a3b8', fontWeight: '500' },
    cellTextTarget: { color: '#6366f1', fontWeight: '700' },
    borderRight: { borderRightWidth: 2, borderRightColor: '#475569' },
    borderBottom: { borderBottomWidth: 2, borderBottomColor: '#475569' },
});

// ── Digit picker ──────────────────────────────────────────────────────────────

function DigitPicker({
    onSelect,
    correct,
}: {
    onSelect: (d: number) => void;
    correct?: number;
}) {
    const [selected, setSelected] = useState<number | null>(null);
    const handlePress = (d: number) => {
        setSelected(d);
        onSelect(d);
    };
    return (
        <View style={pickerStyles.row}>
            {[1, 2, 3, 4, 5, 6, 7, 8, 9].map((d) => {
                const isCorrect = selected === d && d === correct;
                const isWrong = selected === d && d !== correct;
                return (
                    <TouchableOpacity
                        key={d}
                        style={[
                            pickerStyles.btn,
                            isCorrect && pickerStyles.btnCorrect,
                            isWrong && pickerStyles.btnWrong,
                        ]}
                        onPress={() => handlePress(d)}
                    >
                        <Text style={[
                            pickerStyles.btnText,
                            isCorrect && pickerStyles.btnTextCorrect,
                            isWrong && pickerStyles.btnTextWrong,
                        ]}>{d}</Text>
                    </TouchableOpacity>
                );
            })}
        </View>
    );
}

const pickerStyles = StyleSheet.create({
    row: { flexDirection: 'row', justifyContent: 'center', gap: 8, marginVertical: 12 },
    btn: {
        width: 34, height: 34, borderRadius: 8,
        backgroundColor: '#1e293b', borderWidth: 1, borderColor: '#334155',
        justifyContent: 'center', alignItems: 'center',
    },
    btnCorrect: { backgroundColor: '#16a34a22', borderColor: '#22c55e' },
    btnWrong: { backgroundColor: '#ef444422', borderColor: '#ef4444' },
    btnText: { fontSize: 14, fontWeight: '600', color: '#94a3b8' },
    btnTextCorrect: { color: '#22c55e' },
    btnTextWrong: { color: '#ef4444' },
});

// ── Main screen ───────────────────────────────────────────────────────────────

export default function LessonDetailScreen({ route, navigation }: LessonDetailScreenProps) {
    const { lessonId, title } = route.params;

    const [lessonData, setLessonData] = useState<LessonDetail | null>(null);
    const [loading, setLoading] = useState(true);
    const [currentStep, setCurrentStep] = useState(0);
    const [practiceAnswered, setPracticeAnswered] = useState(false);
    const [practiceCorrect, setPracticeCorrect] = useState(false);
    const [submitting, setSubmitting] = useState(false);
    const [xpAnim] = useState(new Animated.Value(0));

    const load = useCallback(async () => {
        try {
            const res = await fetch(`${API}/api/lessons/${lessonId}`, {
                headers: { Authorization: `Bearer ${TOKEN}` },
            });
            const data = await res.json();
            const ld: LessonDetail = {
                ...data.lesson,
                progress: data.progress,
            };
            setLessonData(ld);
            // Resume from last incomplete step
            const done = data.progress?.stepsComplete ?? 0;
            setCurrentStep(Math.min(done, ld.steps.length - 1));
        } catch (e) {
            Alert.alert('Error', 'Could not load lesson.');
        } finally {
            setLoading(false);
        }
    }, [lessonId]);

    useEffect(() => { load(); }, [load]);

    const completeStep = useCallback(
        async (stepNumber: number): Promise<StepResult | null> => {
            setSubmitting(true);
            try {
                const res = await fetch(
                    `${API}/api/lessons/${lessonId}/steps/${stepNumber}/complete`,
                    {
                        method: 'POST',
                        headers: {
                            Authorization: `Bearer ${TOKEN}`,
                            'Content-Type': 'application/json',
                        },
                        body: JSON.stringify({}),
                    },
                );
                return await res.json();
            } catch {
                return null;
            } finally {
                setSubmitting(false);
            }
        },
        [lessonId],
    );

    const handleNext = useCallback(async () => {
        if (!lessonData) return;
        const step = lessonData.steps[currentStep];

        // Require correct practice answer before proceeding
        if (step.type === 'practice' && !practiceCorrect) return;

        const result = await completeStep(step.stepNumber);

        if (result?.lessonCompleted) {
            // Animate XP badge
            Animated.sequence([
                Animated.timing(xpAnim, { toValue: 1, duration: 400, useNativeDriver: true }),
                Animated.delay(1600),
                Animated.timing(xpAnim, { toValue: 0, duration: 300, useNativeDriver: true }),
            ]).start();

            // Show badge alerts
            if (result.newBadges?.length > 0) {
                const names = result.newBadges.map((b) => `${b.icon} ${b.title}`).join('\n');
                Alert.alert('New Badge!', names);
            }

            setTimeout(() => navigation.goBack(), 2200);
        } else if (currentStep < (lessonData.steps.length - 1)) {
            setCurrentStep((s) => s + 1);
            setPracticeAnswered(false);
            setPracticeCorrect(false);
        }
    }, [lessonData, currentStep, practiceCorrect, completeStep, xpAnim, navigation]);

    const handleAnswer = useCallback(
        (digit: number) => {
            if (!lessonData) return;
            const step = lessonData.steps[currentStep];
            const correct = digit === step.targetValue;
            setPracticeAnswered(true);
            setPracticeCorrect(correct);
        },
        [lessonData, currentStep],
    );

    if (loading || !lessonData) {
        return (
            <View style={styles.center}>
                <ActivityIndicator size="large" color="#6366f1" />
            </View>
        );
    }

    const step = lessonData.steps[currentStep];
    const isLast = currentStep === lessonData.steps.length - 1;
    const canAdvance =
        step.type !== 'practice' || practiceCorrect;

    // XP banner animation
    const xpBannerStyle = {
        opacity: xpAnim,
        transform: [{ translateY: xpAnim.interpolate({ inputRange: [0, 1], outputRange: [20, 0] }) }],
    };

    return (
        <View style={styles.container}>
            {/* Step indicator */}
            <View style={styles.stepIndicator}>
                {lessonData.steps.map((_, i) => (
                    <View
                        key={i}
                        style={[
                            styles.stepDot,
                            i < currentStep && styles.stepDotDone,
                            i === currentStep && styles.stepDotActive,
                        ]}
                    />
                ))}
            </View>

            <ScrollView style={styles.scroll} contentContainerStyle={styles.scrollContent}>
                {/* Step type chip */}
                <View style={[styles.typeChip, styles[`chip_${step.type}`]]}>
                    <Text style={styles.typeChipText}>
                        {step.type === 'read' ? '📖 Read' : step.type === 'example' ? '🔍 Example' : '✏️ Practice'}
                    </Text>
                </View>

                <Text style={styles.stepTitle}>{step.title}</Text>
                <Text style={styles.stepContent}>{step.content}</Text>

                {/* Board for example + practice steps */}
                {(step.type === 'example' || step.type === 'practice') &&
                    step.puzzle && (
                        <MiniBoard
                            board={step.puzzle}
                            highlightCells={step.highlightCells ?? []}
                            targetCell={step.type === 'practice' ? step.targetCell : undefined}
                        />
                    )}

                {/* Digit picker for practice steps */}
                {step.type === 'practice' && (
                    <>
                        <Text style={styles.pickLabel}>Select the correct digit:</Text>
                        <DigitPicker onSelect={handleAnswer} correct={step.targetValue} />
                        {practiceAnswered && (
                            <Text style={[styles.feedback, practiceCorrect ? styles.feedbackOk : styles.feedbackBad]}>
                                {practiceCorrect
                                    ? `✓ Correct! ${step.targetValue} it is.`
                                    : `✗ Not quite — check the row, column, and box again.`}
                            </Text>
                        )}
                    </>
                )}

                <View style={{ height: 100 }} />
            </ScrollView>

            {/* Bottom bar */}
            <View style={styles.bottomBar}>
                <Text style={styles.progressText}>
                    Step {currentStep + 1} of {lessonData.steps.length}
                </Text>
                <TouchableOpacity
                    style={[styles.nextBtn, !canAdvance && styles.nextBtnDisabled]}
                    onPress={handleNext}
                    disabled={!canAdvance || submitting}
                >
                    <Text style={styles.nextBtnText}>
                        {submitting ? '…' : isLast ? 'Complete ✓' : 'Next →'}
                    </Text>
                </TouchableOpacity>
            </View>

            {/* XP completion banner */}
            <Animated.View style={[styles.xpBanner, xpBannerStyle]} pointerEvents="none">
                <Text style={styles.xpBannerText}>+{lessonData.xpReward} XP</Text>
                <Text style={styles.xpBannerSub}>Lesson Complete!</Text>
            </Animated.View>
        </View>
    );
}

// ── Styles ────────────────────────────────────────────────────────────────────

const styles = StyleSheet.create({
    container: { flex: 1, backgroundColor: '#0f172a' },
    center: { flex: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: '#0f172a' },
    scroll: { flex: 1 },
    scrollContent: { padding: 20 },

    stepIndicator: {
        flexDirection: 'row', gap: 6, padding: 16, paddingBottom: 0, justifyContent: 'center',
    },
    stepDot: {
        width: 8, height: 8, borderRadius: 4, backgroundColor: '#334155',
    },
    stepDotDone: { backgroundColor: '#6366f1' },
    stepDotActive: { backgroundColor: '#a78bfa', width: 20, borderRadius: 4 },

    typeChip: {
        alignSelf: 'flex-start', paddingHorizontal: 10, paddingVertical: 4,
        borderRadius: 12, marginBottom: 10,
    },
    chip_read: { backgroundColor: '#1e3a5f' },
    chip_example: { backgroundColor: '#3b2f00' },
    chip_practice: { backgroundColor: '#1a2f1a' },
    typeChipText: { fontSize: 12, fontWeight: '600', color: '#94a3b8' },

    stepTitle: { fontSize: 20, fontWeight: '700', color: '#f1f5f9', marginBottom: 10 },
    stepContent: { fontSize: 14, color: '#94a3b8', lineHeight: 22 },

    pickLabel: { fontSize: 13, color: '#94a3b8', textAlign: 'center', marginTop: 4 },
    feedback: { textAlign: 'center', fontSize: 13, fontWeight: '600', marginTop: 4 },
    feedbackOk: { color: '#22c55e' },
    feedbackBad: { color: '#ef4444' },

    bottomBar: {
        flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
        padding: 16, borderTopWidth: 1, borderTopColor: '#1e293b', backgroundColor: '#0f172a',
    },
    progressText: { fontSize: 13, color: '#475569' },
    nextBtn: {
        backgroundColor: '#6366f1', paddingHorizontal: 22, paddingVertical: 10,
        borderRadius: 10,
    },
    nextBtnDisabled: { backgroundColor: '#334155' },
    nextBtnText: { color: '#fff', fontWeight: '700', fontSize: 15 },

    xpBanner: {
        position: 'absolute', alignSelf: 'center', bottom: 100,
        backgroundColor: '#16a34a', paddingHorizontal: 28, paddingVertical: 14,
        borderRadius: 16, alignItems: 'center', shadowColor: '#000',
        shadowOffset: { width: 0, height: 4 }, shadowOpacity: 0.4, shadowRadius: 8,
        elevation: 8,
    },
    xpBannerText: { fontSize: 28, fontWeight: '900', color: '#fff' },
    xpBannerSub: { fontSize: 14, color: '#bbf7d0', marginTop: 2 },
} as any);
