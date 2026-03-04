import React from 'react';
import { StyleSheet, Text, View, StatusBar } from 'react-native';

export default function App(): React.JSX.Element {
    return (
        <View style={styles.container}>
            <StatusBar barStyle="light-content" backgroundColor="#0f172a" />
            <Text style={styles.title}>🧩 Sudoku Ultra</Text>
            <Text style={styles.subtitle}>ML-Powered Sudoku Platform</Text>
            <Text style={styles.version}>v0.0.1 — Phase 1 Scaffold</Text>
        </View>
    );
}

const styles = StyleSheet.create({
    container: {
        flex: 1,
        backgroundColor: '#0f172a',
        alignItems: 'center',
        justifyContent: 'center',
    },
    title: {
        fontSize: 36,
        fontWeight: '800',
        color: '#f8fafc',
        marginBottom: 8,
    },
    subtitle: {
        fontSize: 16,
        color: '#94a3b8',
        marginBottom: 4,
    },
    version: {
        fontSize: 12,
        color: '#64748b',
        marginTop: 16,
    },
});
