import React from 'react';
import { View, TouchableOpacity, Text, StyleSheet } from 'react-native';
import { colors } from '../theme/colors';

interface GameControlsProps {
    notesMode: boolean;
    onToggleNotes: () => void;
    onUndo: () => void;
    onRedo: () => void;
    onHint: () => void;
    onValidate: () => void;
    onAutoNotes: () => void;
    hintsUsed: number;
}

export function GameControls({
    notesMode,
    onToggleNotes,
    onUndo,
    onRedo,
    onHint,
    onValidate,
    onAutoNotes,
    hintsUsed,
}: GameControlsProps) {
    return (
        <View style={styles.container}>
            <ControlButton icon="↩" label="Undo" onPress={onUndo} />
            <ControlButton icon="↪" label="Redo" onPress={onRedo} />
            <ControlButton
                icon="✏"
                label={notesMode ? 'Notes ON' : 'Notes'}
                onPress={onToggleNotes}
                active={notesMode}
            />
            <ControlButton
                icon="💡"
                label={`Hint (${hintsUsed})`}
                onPress={onHint}
            />
            <ControlButton icon="✓" label="Check" onPress={onValidate} />
            <ControlButton icon="📝" label="Auto" onPress={onAutoNotes} />
        </View>
    );
}

interface ControlButtonProps {
    icon: string;
    label: string;
    onPress: () => void;
    active?: boolean;
}

function ControlButton({ icon, label, onPress, active }: ControlButtonProps) {
    return (
        <TouchableOpacity
            style={[styles.button, active && styles.activeButton]}
            onPress={onPress}
            activeOpacity={0.7}
        >
            <Text style={styles.icon}>{icon}</Text>
            <Text style={[styles.label, active && styles.activeLabel]}>{label}</Text>
        </TouchableOpacity>
    );
}

const styles = StyleSheet.create({
    container: {
        flexDirection: 'row',
        justifyContent: 'space-around',
        paddingHorizontal: 8,
        paddingVertical: 8,
    },
    button: {
        alignItems: 'center',
        justifyContent: 'center',
        paddingVertical: 6,
        paddingHorizontal: 8,
        borderRadius: 8,
        minWidth: 48,
    },
    activeButton: {
        backgroundColor: colors.primary[900],
        borderWidth: 1,
        borderColor: colors.primary[500],
    },
    icon: {
        fontSize: 20,
        marginBottom: 2,
    },
    label: {
        fontSize: 10,
        color: colors.text.secondary,
        fontWeight: '600',
    },
    activeLabel: {
        color: colors.primary[400],
    },
});
