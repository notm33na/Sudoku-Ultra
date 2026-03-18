/**
 * deepLink.ts — Deep link configuration for React Navigation.
 *
 * Supports:
 *   Custom scheme:  sudokuultra://join/:roomId
 *                   sudokuultra://puzzle/:puzzleId
 *   Universal link: https://sudokuultra.example.com/join/:roomId
 *                   https://sudokuultra.example.com/puzzle/:puzzleId
 *
 * Usage (RootNavigator):
 *   import { linking } from '../utils/deepLink';
 *   <NavigationContainer linking={linking}>
 *
 * Testing on device:
 *   # Android
 *   adb shell am start -W -a android.intent.action.VIEW \
 *     -d "sudokuultra://join/my-room-id" com.sudokuultra.app
 *
 *   # iOS simulator
 *   xcrun simctl openurl booted "sudokuultra://join/my-room-id"
 */

import { LinkingOptions } from '@react-navigation/native';
import { Linking } from 'react-native';
import { RootStackParamList } from '../types/navigation';

export const linking: LinkingOptions<RootStackParamList> = {
    // URL schemes to handle
    prefixes: [
        'sudokuultra://',
        'https://sudokuultra.example.com',
        'https://www.sudokuultra.example.com',
    ],

    // Custom getInitialURL — handles cold-start deep links
    async getInitialURL(): Promise<string | null> {
        const url = await Linking.getInitialURL();
        return url;
    },

    // Subscribe to incoming URLs while app is open
    subscribe(listener: (url: string) => void) {
        const subscription = Linking.addEventListener('url', ({ url }) => listener(url));
        return () => subscription.remove();
    },

    config: {
        screens: {
            Home:             '',
            Difficulty:       'play',
            Game:             'game',
            Result:           'result',
            ScanPuzzle:       'scan',
            MultiplayerLobby: 'multiplayer',
            MultiplayerGame: {
                path: 'join/:roomId',
                parse: {
                    roomId: (roomId: string) => roomId,
                },
            },
            MatchResult:     'match-result',
            Lessons:         'learn',
            LessonDetail: {
                path: 'learn/:lessonId',
                parse: {
                    lessonId: (id: string) => id,
                    title:    (t: string) => decodeURIComponent(t),
                },
            },
            Onboarding:      'onboarding',
            Friends:         'friends',
            ActivityFeed:    'activity',
        },
    },
};
