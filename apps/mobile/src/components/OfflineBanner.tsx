/**
 * OfflineBanner.tsx — Network connectivity indicator
 *
 * Shows a dismissible banner at the top of the screen when the device
 * is offline. Displays pending queue count when items are queued.
 * Fades out automatically when connectivity is restored.
 */

import React, { useEffect, useRef, useState } from 'react';
import {
    Animated,
    StyleSheet,
    Text,
    TouchableOpacity,
    View,
} from 'react-native';
import NetInfo, { NetInfoState } from '@react-native-community/netinfo';
import { offlineQueue, QueueStats } from '../services/offlineQueue.service';

// ── Types ────────────────────────────────────────────────────────────────────

interface OfflineBannerProps {
    /** Override for testing — skip NetInfo and treat as offline */
    forceOffline?: boolean;
}

// ── Component ────────────────────────────────────────────────────────────────

export function OfflineBanner({ forceOffline }: OfflineBannerProps) {
    const [isOffline, setIsOffline] = useState(false);
    const [dismissed, setDismissed] = useState(false);
    const [queueStats, setQueueStats] = useState<QueueStats | null>(null);
    const opacity = useRef(new Animated.Value(0)).current;

    // Subscribe to network state
    useEffect(() => {
        const unsubscribe = NetInfo.addEventListener((state: NetInfoState) => {
            const offline = !state.isConnected;
            setIsOffline(offline);
            if (!offline) {
                // Coming back online — refresh stats after sync completes
                setTimeout(refreshStats, 1500);
                setDismissed(false);
            }
        });

        // Initial state check
        NetInfo.fetch().then((state) => {
            setIsOffline(!state.isConnected);
        });

        return unsubscribe;
    }, []);

    // Refresh queue stats periodically while offline
    useEffect(() => {
        if (!isOffline && !forceOffline) return;
        refreshStats();
        const interval = setInterval(refreshStats, 5000);
        return () => clearInterval(interval);
    }, [isOffline, forceOffline]);

    // Animate in/out
    const visible = (isOffline || forceOffline) && !dismissed;
    useEffect(() => {
        Animated.timing(opacity, {
            toValue: visible ? 1 : 0,
            duration: 300,
            useNativeDriver: true,
        }).start();
    }, [visible]);

    async function refreshStats() {
        const stats = await offlineQueue.stats();
        setQueueStats(stats);
    }

    if (!visible && !forceOffline) return null;

    const pendingCount = queueStats?.pending ?? 0;

    return (
        <Animated.View style={[styles.banner, { opacity }]} accessibilityLiveRegion="polite">
            <View style={styles.content}>
                <View style={styles.icon} accessibilityLabel="Offline indicator">
                    <Text style={styles.iconText}>⚡</Text>
                </View>
                <View style={styles.textContainer}>
                    <Text style={styles.title}>You're offline</Text>
                    <Text style={styles.subtitle}>
                        {pendingCount > 0
                            ? `${pendingCount} game result${pendingCount !== 1 ? 's' : ''} will sync when reconnected`
                            : 'Game progress is saved locally'}
                    </Text>
                </View>
                <TouchableOpacity
                    style={styles.dismiss}
                    onPress={() => setDismissed(true)}
                    accessibilityLabel="Dismiss offline banner"
                    accessibilityRole="button"
                    hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
                >
                    <Text style={styles.dismissText}>✕</Text>
                </TouchableOpacity>
            </View>
            {pendingCount > 0 && (
                <View style={styles.progressBar}>
                    <View
                        style={[
                            styles.progressFill,
                            {
                                width: `${Math.min(
                                    ((queueStats?.synced ?? 0) /
                                        Math.max(queueStats?.total ?? 1, 1)) *
                                        100,
                                    100,
                                )}%`,
                            },
                        ]}
                    />
                </View>
            )}
        </Animated.View>
    );
}

// ── Styles ───────────────────────────────────────────────────────────────────

const styles = StyleSheet.create({
    banner: {
        backgroundColor: '#1a1a2e',
        borderBottomWidth: 1,
        borderBottomColor: '#e94560',
        overflow: 'hidden',
    },
    content: {
        flexDirection: 'row',
        alignItems: 'center',
        paddingHorizontal: 16,
        paddingVertical: 10,
    },
    icon: {
        width: 28,
        height: 28,
        borderRadius: 14,
        backgroundColor: '#e94560',
        alignItems: 'center',
        justifyContent: 'center',
        marginRight: 12,
    },
    iconText: {
        fontSize: 14,
        color: '#ffffff',
    },
    textContainer: {
        flex: 1,
    },
    title: {
        fontSize: 13,
        fontWeight: '600',
        color: '#ffffff',
        letterSpacing: 0.2,
    },
    subtitle: {
        fontSize: 11,
        color: '#aaaacc',
        marginTop: 1,
    },
    dismiss: {
        padding: 4,
        marginLeft: 8,
    },
    dismissText: {
        fontSize: 14,
        color: '#aaaacc',
    },
    progressBar: {
        height: 2,
        backgroundColor: '#2d2d4e',
    },
    progressFill: {
        height: '100%',
        backgroundColor: '#4caf50',
    },
});

export default OfflineBanner;
