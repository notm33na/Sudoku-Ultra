import React from 'react';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { RootStackParamList } from '../types/navigation';
import { HomeScreen } from '../screens/HomeScreen';
import { DifficultyScreen } from '../screens/DifficultyScreen';
import { GameScreen } from '../screens/GameScreen';
import { ResultScreen } from '../screens/ResultScreen';
import { colors } from '../theme/colors';

const Stack = createNativeStackNavigator<RootStackParamList>();

export function RootNavigator() {
    return (
        <Stack.Navigator
            initialRouteName="Home"
            screenOptions={{
                headerStyle: {
                    backgroundColor: colors.surface.dark,
                },
                headerTintColor: colors.text.primary,
                headerTitleStyle: {
                    fontWeight: '700',
                    fontSize: 18,
                },
                headerShadowVisible: false,
                contentStyle: {
                    backgroundColor: colors.surface.dark,
                },
                animation: 'slide_from_right',
            }}
        >
            <Stack.Screen
                name="Home"
                component={HomeScreen}
                options={{ headerShown: false }}
            />
            <Stack.Screen
                name="Difficulty"
                component={DifficultyScreen}
                options={{ title: 'Select Difficulty' }}
            />
            <Stack.Screen
                name="Game"
                component={GameScreen}
                options={{
                    title: 'Sudoku Ultra',
                    headerBackVisible: false,
                    gestureEnabled: false,
                }}
            />
            <Stack.Screen
                name="Result"
                component={ResultScreen}
                options={{
                    headerShown: false,
                    gestureEnabled: false,
                }}
            />
        </Stack.Navigator>
    );
}
