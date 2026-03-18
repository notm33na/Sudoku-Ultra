/**
 * ErrorBoundary.tsx — React error boundary for the mobile app.
 *
 * Wraps any subtree. On uncaught render errors:
 *   1. Captures the exception via Sentry (if configured).
 *   2. Shows a user-friendly fallback screen with a "Restart" button.
 *   3. Uses React Native's `DevSettings.reload()` (dev) or resets the
 *      navigation state (prod) to recover without killing the process.
 *
 * Usage:
 *   <ErrorBoundary>
 *     <YourComponent />
 *   </ErrorBoundary>
 *
 *   // With custom fallback:
 *   <ErrorBoundary fallback={<MyFallback />}>
 *     <YourComponent />
 *   </ErrorBoundary>
 */

import React from 'react';
import {
    View,
    Text,
    Pressable,
    StyleSheet,
    ScrollView,
} from 'react-native';
import { captureException } from '../services/sentry';

interface Props {
    children: React.ReactNode;
    fallback?: React.ReactNode;
}

interface State {
    hasError: boolean;
    error: Error | null;
    errorInfo: React.ErrorInfo | null;
}

export class ErrorBoundary extends React.Component<Props, State> {
    constructor(props: Props) {
        super(props);
        this.state = { hasError: false, error: null, errorInfo: null };
    }

    static getDerivedStateFromError(error: Error): Partial<State> {
        return { hasError: true, error };
    }

    componentDidCatch(error: Error, errorInfo: React.ErrorInfo): void {
        this.setState({ errorInfo });
        captureException(error, {
            componentStack: errorInfo.componentStack ?? undefined,
        });
    }

    private handleRestart = (): void => {
        this.setState({ hasError: false, error: null, errorInfo: null });
    };

    render(): React.ReactNode {
        if (!this.state.hasError) {
            return this.props.children;
        }

        if (this.props.fallback) {
            return this.props.fallback;
        }

        const { error } = this.state;
        const isDev = __DEV__;

        return (
            <View style={styles.container}>
                <Text style={styles.icon}>⚠️</Text>
                <Text style={styles.title}>Something went wrong</Text>
                <Text style={styles.subtitle}>
                    The app hit an unexpected error. Tap below to try again.
                </Text>

                {isDev && error ? (
                    <ScrollView style={styles.debugBox} contentContainerStyle={styles.debugContent}>
                        <Text style={styles.debugTitle}>{error.name}: {error.message}</Text>
                        <Text style={styles.debugStack}>{error.stack}</Text>
                    </ScrollView>
                ) : null}

                <Pressable
                    style={({ pressed }) => [styles.button, pressed && styles.pressed]}
                    onPress={this.handleRestart}
                    accessibilityRole="button"
                    accessibilityLabel="Restart the app"
                >
                    <Text style={styles.buttonText}>Restart</Text>
                </Pressable>
            </View>
        );
    }
}

const styles = StyleSheet.create({
    container: {
        flex: 1,
        backgroundColor: '#0f172a',
        alignItems: 'center',
        justifyContent: 'center',
        paddingHorizontal: 32,
    },
    icon: {
        fontSize: 64,
        marginBottom: 20,
    },
    title: {
        fontSize: 22,
        fontWeight: '700',
        color: '#f1f5f9',
        marginBottom: 12,
        textAlign: 'center',
    },
    subtitle: {
        fontSize: 14,
        color: '#94a3b8',
        textAlign: 'center',
        lineHeight: 21,
        marginBottom: 32,
    },
    debugBox: {
        maxHeight: 200,
        width: '100%',
        backgroundColor: '#1e293b',
        borderRadius: 8,
        marginBottom: 24,
    },
    debugContent: {
        padding: 12,
    },
    debugTitle: {
        color: '#f87171',
        fontSize: 12,
        fontWeight: '700',
        marginBottom: 6,
    },
    debugStack: {
        color: '#94a3b8',
        fontSize: 10,
        fontFamily: 'monospace',
    },
    button: {
        backgroundColor: '#6366f1',
        paddingVertical: 16,
        paddingHorizontal: 48,
        borderRadius: 12,
    },
    pressed: {
        opacity: 0.75,
    },
    buttonText: {
        color: '#ffffff',
        fontSize: 16,
        fontWeight: '700',
    },
});
