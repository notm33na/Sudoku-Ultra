import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { colors } from '../theme/colors';

interface TimerProps {
    timeMs: number;
    isPaused: boolean;
}

export function Timer({ timeMs, isPaused }: TimerProps) {
    const totalSeconds = Math.floor(timeMs / 1000);
    const minutes = Math.floor(totalSeconds / 60);
    const seconds = totalSeconds % 60;

    const formatted = `${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;

    return (
        <View style={styles.container}>
            <Text style={[styles.time, isPaused && styles.paused]}>
                {isPaused ? '⏸ ' : '⏱ '}
                {formatted}
            </Text>
        </View>
    );
}

const styles = StyleSheet.create({
    container: {
        alignItems: 'center',
        paddingVertical: 4,
    },
    time: {
        fontSize: 18,
        fontWeight: '700',
        color: colors.text.primary,
        fontVariant: ['tabular-nums'],
        letterSpacing: 2,
    },
    paused: {
        color: colors.text.muted,
    },
});
