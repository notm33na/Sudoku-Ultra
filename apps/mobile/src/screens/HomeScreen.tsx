import React from 'react';
import {
    View,
    Text,
    TouchableOpacity,
    StyleSheet,
    StatusBar,
    SafeAreaView,
} from 'react-native';
import { HomeScreenProps } from '../types/navigation';
import { colors } from '../theme/colors';

export function HomeScreen({ navigation }: HomeScreenProps) {
    return (
        <SafeAreaView style={styles.container}>
            <StatusBar barStyle="light-content" backgroundColor={colors.surface.dark} />

            {/* Logo & Branding */}
            <View style={styles.header}>
                <Text style={styles.emoji}>🧩</Text>
                <Text style={styles.title}>Sudoku Ultra</Text>
                <Text style={styles.subtitle}>ML-Powered Sudoku Platform</Text>
            </View>

            {/* Main Actions */}
            <View style={styles.actions}>
                <TouchableOpacity
                    style={styles.primaryButton}
                    onPress={() => navigation.navigate('Difficulty')}
                    activeOpacity={0.8}
                >
                    <Text style={styles.primaryButtonText}>🎮  New Game</Text>
                </TouchableOpacity>

                <TouchableOpacity
                    style={styles.secondaryButton}
                    onPress={() => navigation.navigate('Difficulty')}
                    activeOpacity={0.8}
                >
                    <Text style={styles.secondaryButtonText}>📅  Daily Puzzle</Text>
                </TouchableOpacity>
            </View>

            {/* Footer */}
            <View style={styles.footer}>
                <Text style={styles.version}>v0.0.1 — Phase 1</Text>
            </View>
        </SafeAreaView>
    );
}

const styles = StyleSheet.create({
    container: {
        flex: 1,
        backgroundColor: colors.surface.dark,
        justifyContent: 'center',
        paddingHorizontal: 32,
    },
    header: {
        alignItems: 'center',
        marginBottom: 48,
    },
    emoji: {
        fontSize: 64,
        marginBottom: 16,
    },
    title: {
        fontSize: 36,
        fontWeight: '800',
        color: colors.text.primary,
        letterSpacing: 1,
        marginBottom: 8,
    },
    subtitle: {
        fontSize: 14,
        color: colors.text.secondary,
        letterSpacing: 0.5,
    },
    actions: {
        gap: 16,
    },
    primaryButton: {
        backgroundColor: colors.primary[600],
        paddingVertical: 18,
        borderRadius: 14,
        alignItems: 'center',
        shadowColor: colors.primary[500],
        shadowOffset: { width: 0, height: 4 },
        shadowOpacity: 0.3,
        shadowRadius: 8,
        elevation: 6,
    },
    primaryButtonText: {
        fontSize: 18,
        fontWeight: '700',
        color: '#ffffff',
        letterSpacing: 0.5,
    },
    secondaryButton: {
        backgroundColor: colors.surface.darkAlt,
        paddingVertical: 18,
        borderRadius: 14,
        alignItems: 'center',
        borderWidth: 1,
        borderColor: colors.grid.cellBorder,
    },
    secondaryButtonText: {
        fontSize: 18,
        fontWeight: '600',
        color: colors.text.primary,
        letterSpacing: 0.5,
    },
    footer: {
        position: 'absolute',
        bottom: 32,
        left: 0,
        right: 0,
        alignItems: 'center',
    },
    version: {
        fontSize: 12,
        color: colors.text.muted,
    },
});
