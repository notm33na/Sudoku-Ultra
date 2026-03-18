import React, { useEffect, useState } from 'react';
import { NavigationContainer } from '@react-navigation/native';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { StatusBar, View, ActivityIndicator } from 'react-native';
import { RootNavigator } from './src/navigation/RootNavigator';
import { RootStackParamList } from './src/types/navigation';

const GAME_API = process.env.EXPO_PUBLIC_API_URL ?? 'http://localhost:3001';
const TOKEN = process.env.EXPO_PUBLIC_API_TOKEN ?? '';

export default function App(): React.JSX.Element {
    const [initialRoute, setInitialRoute] = useState<keyof RootStackParamList | null>(null);

    useEffect(() => {
        async function checkOnboarding() {
            try {
                const res = await fetch(`${GAME_API}/api/onboarding/status`, {
                    headers: { Authorization: `Bearer ${TOKEN}` },
                });
                if (!res.ok) throw new Error('not ok');
                const data = await res.json();
                const needsOnboarding = !data.completed && !data.skipped;
                setInitialRoute(needsOnboarding ? 'Onboarding' : 'Home');
            } catch {
                // On error (unauthenticated, offline) go straight to Home
                setInitialRoute('Home');
            }
        }
        checkOnboarding();
    }, []);

    if (initialRoute === null) {
        return (
            <View style={{ flex: 1, backgroundColor: '#0f172a', justifyContent: 'center', alignItems: 'center' }}>
                <ActivityIndicator size="large" color="#6366f1" />
            </View>
        );
    }

    return (
        <SafeAreaProvider>
            <StatusBar barStyle="light-content" backgroundColor="#0f172a" />
            <NavigationContainer>
                <RootNavigator initialRoute={initialRoute} />
            </NavigationContainer>
        </SafeAreaProvider>
    );
}
