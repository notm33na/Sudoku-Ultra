import { NativeStackScreenProps } from '@react-navigation/native-stack';
import { Difficulty } from '@sudoku-ultra/shared-types';

export type RootStackParamList = {
    Home: undefined;
    Difficulty: undefined;
    Game: { difficulty: Difficulty };
    Result: {
        score: number;
        timeMs: number;
        hintsUsed: number;
        errorsCount: number;
        difficulty: Difficulty;
    };
};

export type HomeScreenProps = NativeStackScreenProps<RootStackParamList, 'Home'>;
export type DifficultyScreenProps = NativeStackScreenProps<RootStackParamList, 'Difficulty'>;
export type GameScreenProps = NativeStackScreenProps<RootStackParamList, 'Game'>;
export type ResultScreenProps = NativeStackScreenProps<RootStackParamList, 'Result'>;
