import { NativeStackScreenProps } from '@react-navigation/native-stack';
import { Difficulty } from '@sudoku-ultra/shared-types';

export type RootStackParamList = {
    Home: undefined;
    Difficulty: undefined;
    Game: {
        difficulty: Difficulty;
        /** Optional 81-element grid from the CV scanner. */
        scannedGrid?: number[];
    };
    Result: {
        score: number;
        timeMs: number;
        hintsUsed: number;
        errorsCount: number;
        difficulty: Difficulty;
    };
    ScanPuzzle: undefined;
    MultiplayerLobby: undefined;
    MultiplayerGame: {
        roomId: string;
        myUserId: string;
        myDisplayName: string;
        difficulty: string;
    };
    MatchResult: {
        won: boolean;
        endReason: string;
        eloBefore: number;
        eloAfter: number;
        eloDelta: number;
        opponentName: string;
        difficulty: string;
        durationMs: number;
    };
    Lessons: undefined;
    LessonDetail: {
        lessonId: string;
        title: string;
    };
    Onboarding: undefined;
    Friends: undefined;
    ActivityFeed: undefined;
};

export type HomeScreenProps = NativeStackScreenProps<RootStackParamList, 'Home'>;
export type DifficultyScreenProps = NativeStackScreenProps<RootStackParamList, 'Difficulty'>;
export type GameScreenProps = NativeStackScreenProps<RootStackParamList, 'Game'>;
export type ResultScreenProps = NativeStackScreenProps<RootStackParamList, 'Result'>;
export type ScanPuzzleScreenProps = NativeStackScreenProps<RootStackParamList, 'ScanPuzzle'>;
export type MultiplayerLobbyScreenProps = NativeStackScreenProps<RootStackParamList, 'MultiplayerLobby'>;
export type MultiplayerGameScreenProps = NativeStackScreenProps<RootStackParamList, 'MultiplayerGame'>;
export type MatchResultScreenProps = NativeStackScreenProps<RootStackParamList, 'MatchResult'>;
export type LessonsScreenProps = NativeStackScreenProps<RootStackParamList, 'Lessons'>;
export type LessonDetailScreenProps = NativeStackScreenProps<RootStackParamList, 'LessonDetail'>;
export type OnboardingScreenProps = NativeStackScreenProps<RootStackParamList, 'Onboarding'>;
export type FriendsScreenProps = NativeStackScreenProps<RootStackParamList, 'Friends'>;
export type ActivityFeedScreenProps = NativeStackScreenProps<RootStackParamList, 'ActivityFeed'>;
