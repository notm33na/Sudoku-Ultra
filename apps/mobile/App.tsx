import React from 'react';
import { NavigationContainer } from '@react-navigation/native';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { StatusBar } from 'react-native';
import { RootNavigator } from './src/navigation/RootNavigator';

export default function App(): React.JSX.Element {
    return (
        <SafeAreaProvider>
            <StatusBar barStyle="light-content" backgroundColor="#0f172a" />
            <NavigationContainer>
                <RootNavigator />
            </NavigationContainer>
        </SafeAreaProvider>
    );
}
