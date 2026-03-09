import React from 'react';
import { View, TouchableOpacity, Text, StyleSheet } from 'react-native';
import { colors } from '../theme/colors';

interface NumberPadProps {
    onNumberPress: (value: number) => void;
    onClearPress: () => void;
    notesMode: boolean;
}

export function NumberPad({ onNumberPress, onClearPress, notesMode }: NumberPadProps) {
    return (
        <View style={styles.container}>
            <View style={styles.row}>
                {[1, 2, 3, 4, 5].map((n) => (
                    <TouchableOpacity
                        key={n}
                        style={[styles.button, notesMode && styles.notesButton]}
                        onPress={() => onNumberPress(n)}
                        activeOpacity={0.7}
                    >
                        <Text style={[styles.buttonText, notesMode && styles.notesButtonText]}>{n}</Text>
                    </TouchableOpacity>
                ))}
            </View>
            <View style={styles.row}>
                {[6, 7, 8, 9].map((n) => (
                    <TouchableOpacity
                        key={n}
                        style={[styles.button, notesMode && styles.notesButton]}
                        onPress={() => onNumberPress(n)}
                        activeOpacity={0.7}
                    >
                        <Text style={[styles.buttonText, notesMode && styles.notesButtonText]}>{n}</Text>
                    </TouchableOpacity>
                ))}
                <TouchableOpacity
                    style={[styles.button, styles.clearButton]}
                    onPress={onClearPress}
                    activeOpacity={0.7}
                >
                    <Text style={styles.clearText}>✕</Text>
                </TouchableOpacity>
            </View>
        </View>
    );
}

const styles = StyleSheet.create({
    container: {
        paddingHorizontal: 16,
        paddingVertical: 8,
        gap: 8,
    },
    row: {
        flexDirection: 'row',
        justifyContent: 'center',
        gap: 8,
    },
    button: {
        width: 56,
        height: 56,
        borderRadius: 12,
        backgroundColor: colors.surface.darkAlt,
        alignItems: 'center',
        justifyContent: 'center',
        borderWidth: 1,
        borderColor: colors.grid.cellBorder,
    },
    notesButton: {
        borderColor: colors.primary[500],
        borderWidth: 1.5,
    },
    buttonText: {
        fontSize: 24,
        fontWeight: '700',
        color: colors.text.primary,
        fontVariant: ['tabular-nums'],
    },
    notesButtonText: {
        fontSize: 18,
        color: colors.primary[400],
    },
    clearButton: {
        backgroundColor: colors.surface.darkAlt,
        borderColor: colors.error,
    },
    clearText: {
        fontSize: 22,
        fontWeight: '700',
        color: colors.error,
    },
});
