import React, { useRef } from 'react';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { NavigationState } from '@react-navigation/native';
import { RootStackParamList } from '../types/navigation';
import { analyticsService } from '../services/analytics.service';
import { HomeScreen } from '../screens/HomeScreen';
import { DifficultyScreen } from '../screens/DifficultyScreen';
import { GameScreen } from '../screens/GameScreen';
import { ResultScreen } from '../screens/ResultScreen';
import ScanPuzzleScreen from '../screens/ScanPuzzleScreen';
import { MultiplayerLobbyScreen } from '../screens/MultiplayerLobbyScreen';
import { MultiplayerGameScreen } from '../screens/MultiplayerGameScreen';
import { MatchResultScreen } from '../screens/MatchResultScreen';
import LessonsScreen from '../screens/LessonsScreen';
import LessonDetailScreen from '../screens/LessonDetailScreen';
import OnboardingScreen from '../screens/OnboardingScreen';
import FriendsScreen from '../screens/FriendsScreen';
import ActivityFeedScreen from '../screens/ActivityFeedScreen';
import { colors } from '../theme/colors';

const Stack = createNativeStackNavigator<RootStackParamList>();

function getActiveRouteName(state: NavigationState | undefined): string {
    if (!state) return 'Unknown';
    const route = state.routes[state.index];
    if (route.state) return getActiveRouteName(route.state as NavigationState);
    return route.name;
}

/**
 * Pass initialRoute="Onboarding" for first-time users.
 * The app entry point checks /api/onboarding/status and decides.
 */
export function RootNavigator({ initialRoute = 'Home' }: { initialRoute?: keyof RootStackParamList }) {
    const routeNameRef = useRef<string>('');

    return (
        <Stack.Navigator
            screenListeners={{
                state: (e) => {
                    const state = e.data?.state as NavigationState | undefined;
                    const current = getActiveRouteName(state);
                    if (current !== routeNameRef.current) {
                        routeNameRef.current = current;
                        analyticsService.screen(current);
                    }
                },
            }}
            initialRouteName={initialRoute as 'Home'}
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
            <Stack.Screen
                name="ScanPuzzle"
                component={ScanPuzzleScreen}
                options={{ title: 'Scan Puzzle' }}
            />
            <Stack.Screen
                name="MultiplayerLobby"
                component={MultiplayerLobbyScreen}
                options={{ title: 'Multiplayer' }}
            />
            <Stack.Screen
                name="MultiplayerGame"
                component={MultiplayerGameScreen}
                options={{
                    title: 'Match',
                    headerBackVisible: false,
                    gestureEnabled: false,
                }}
            />
            <Stack.Screen
                name="MatchResult"
                component={MatchResultScreen}
                options={{
                    headerShown: false,
                    gestureEnabled: false,
                }}
            />
            <Stack.Screen
                name="Lessons"
                component={LessonsScreen}
                options={{ title: 'Learn' }}
            />
            <Stack.Screen
                name="LessonDetail"
                component={LessonDetailScreen}
                options={({ route }) => ({ title: route.params.title })}
            />
            <Stack.Screen
                name="Onboarding"
                component={OnboardingScreen}
                options={{ headerShown: false, gestureEnabled: false }}
            />
            <Stack.Screen
                name="Friends"
                component={FriendsScreen}
                options={{ title: 'Friends' }}
            />
            <Stack.Screen
                name="ActivityFeed"
                component={ActivityFeedScreen}
                options={{ title: 'Activity Feed' }}
            />
        </Stack.Navigator>
    );
}
