import React, { useEffect, useRef, useCallback } from 'react';
import { View, Text, StyleSheet, SafeAreaView, Alert } from 'react-native';
import { GameScreenProps } from '../types/navigation';
import { useGameStore } from '../store/gameStore';
import { SudokuBoard } from '../components/SudokuBoard';
import { NumberPad } from '../components/NumberPad';
import { GameControls } from '../components/GameControls';
import { Timer } from '../components/Timer';
import { colors } from '../theme/colors';

export function GameScreen({ route, navigation }: GameScreenProps) {
    const { difficulty } = route.params;
    const store = useGameStore();
    const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

    // Start game
    useEffect(() => {
        store.startGame(difficulty);
        return () => {
            if (timerRef.current) clearInterval(timerRef.current);
        };
    }, [difficulty]);

    // Timer
    useEffect(() => {
        if (store.isPlaying && !store.isPaused && !store.isComplete) {
            timerRef.current = setInterval(() => {
                store.tick(1000);
            }, 1000);
        } else {
            if (timerRef.current) clearInterval(timerRef.current);
        }
        return () => {
            if (timerRef.current) clearInterval(timerRef.current);
        };
    }, [store.isPlaying, store.isPaused, store.isComplete]);

    // Navigate on completion
    useEffect(() => {
        if (store.isComplete) {
            navigation.replace('Result', {
                score: store.score,
                timeMs: store.timerMs,
                hintsUsed: store.hintsUsed,
                errorsCount: store.errorsCount,
                difficulty,
            });
        }
    }, [store.isComplete]);

    const handleCellPress = useCallback((row: number, col: number) => {
        useGameStore.getState().selectCell(row, col);
    }, []);

    const handleNumberPress = useCallback((value: number) => {
        useGameStore.getState().setValue(value);
    }, []);

    const handleClearPress = useCallback(() => {
        useGameStore.getState().clearValue();
    }, []);

    const handleValidate = useCallback(() => {
        const conflicts = useGameStore.getState().validateGrid();
        if (conflicts === 0) {
            Alert.alert('✅ Looking Good', 'No errors found!');
        } else {
            Alert.alert('❌ Errors Found', `${conflicts} conflict(s) detected.`);
        }
    }, []);

    if (store.currentGrid.length === 0) {
        return (
            <SafeAreaView style={styles.container}>
                <View style={styles.loading}>
                    <Text style={styles.loadingText}>Generating puzzle...</Text>
                </View>
            </SafeAreaView>
        );
    }

    const diffLabel = difficulty.charAt(0).toUpperCase() + difficulty.slice(1);

    return (
        <SafeAreaView style={styles.container}>
            {/* Header */}
            <View style={styles.header}>
                <Text style={styles.diffBadge}>{diffLabel}</Text>
                <Timer timeMs={store.timerMs} isPaused={store.isPaused} />
                <Text style={styles.statsText}>
                    💡 {store.hintsUsed}  ❌ {store.errorsCount}
                </Text>
            </View>

            {/* Board */}
            <SudokuBoard
                grid={store.currentGrid}
                selectedRow={store.selectedCell?.row ?? null}
                selectedCol={store.selectedCell?.col ?? null}
                onCellPress={handleCellPress}
            />

            {/* Controls */}
            <GameControls
                notesMode={store.notesMode}
                onToggleNotes={store.toggleNotesMode}
                onUndo={store.undo}
                onRedo={store.redo}
                onHint={store.useHint}
                onValidate={handleValidate}
                onAutoNotes={store.autoNotes}
                hintsUsed={store.hintsUsed}
            />

            {/* Number Pad */}
            <NumberPad
                onNumberPress={handleNumberPress}
                onClearPress={handleClearPress}
                notesMode={store.notesMode}
            />
        </SafeAreaView>
    );
}

const styles = StyleSheet.create({
    container: {
        flex: 1,
        backgroundColor: colors.surface.dark,
    },
    loading: {
        flex: 1,
        alignItems: 'center',
        justifyContent: 'center',
    },
    loadingText: {
        fontSize: 18,
        color: colors.text.secondary,
    },
    header: {
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'space-between',
        paddingHorizontal: 16,
        paddingVertical: 8,
    },
    diffBadge: {
        fontSize: 14,
        fontWeight: '700',
        color: colors.primary[400],
        backgroundColor: colors.primary[900],
        paddingHorizontal: 12,
        paddingVertical: 4,
        borderRadius: 8,
        overflow: 'hidden',
    },
    statsText: {
        fontSize: 14,
        color: colors.text.secondary,
        fontVariant: ['tabular-nums'],
    },
});
