import React from 'react';
import {
    View,
    Text,
    TouchableOpacity,
    StyleSheet,
    ScrollView,
    SafeAreaView,
} from 'react-native';
import { Difficulty } from '@sudoku-ultra/shared-types';
import { DifficultyScreenProps } from '../types/navigation';
import { colors } from '../theme/colors';

const DIFFICULTIES: Array<{
    level: Difficulty;
    label: string;
    description: string;
    clues: string;
    color: string;
}> = [
        {
            level: Difficulty.BEGINNER,
            label: 'Beginner',
            description: 'Perfect for learning the basics',
            clues: '45–50 clues',
            color: colors.difficulty.beginner,
        },
        {
            level: Difficulty.EASY,
            label: 'Easy',
            description: 'Straightforward logic chains',
            clues: '36–44 clues',
            color: colors.difficulty.easy,
        },
        {
            level: Difficulty.MEDIUM,
            label: 'Medium',
            description: 'Requires some deduction',
            clues: '30–35 clues',
            color: colors.difficulty.medium,
        },
        {
            level: Difficulty.HARD,
            label: 'Hard',
            description: 'Advanced techniques needed',
            clues: '26–29 clues',
            color: colors.difficulty.hard,
        },
        {
            level: Difficulty.EXPERT,
            label: 'Expert',
            description: 'Multiple advanced strategies',
            clues: '22–25 clues',
            color: colors.difficulty.expert,
        },
        {
            level: Difficulty.EVIL,
            label: 'Evil',
            description: 'Only for the brave',
            clues: '17–21 clues',
            color: colors.difficulty.evil,
        },
    ];

export function DifficultyScreen({ navigation }: DifficultyScreenProps) {
    return (
        <SafeAreaView style={styles.container}>
            <Text style={styles.title}>Choose Difficulty</Text>
            <ScrollView
                style={styles.scroll}
                contentContainerStyle={styles.scrollContent}
                showsVerticalScrollIndicator={false}
            >
                {DIFFICULTIES.map((d) => (
                    <TouchableOpacity
                        key={d.level}
                        style={styles.card}
                        onPress={() => navigation.navigate('Game', { difficulty: d.level })}
                        activeOpacity={0.8}
                    >
                        <View style={[styles.badge, { backgroundColor: d.color }]}>
                            <Text style={styles.badgeText}>{d.label[0]}</Text>
                        </View>
                        <View style={styles.cardContent}>
                            <Text style={styles.cardTitle}>{d.label}</Text>
                            <Text style={styles.cardDesc}>{d.description}</Text>
                            <Text style={styles.cardClues}>{d.clues}</Text>
                        </View>
                        <Text style={styles.arrow}>→</Text>
                    </TouchableOpacity>
                ))}
            </ScrollView>
        </SafeAreaView>
    );
}

const styles = StyleSheet.create({
    container: {
        flex: 1,
        backgroundColor: colors.surface.dark,
    },
    title: {
        fontSize: 24,
        fontWeight: '800',
        color: colors.text.primary,
        textAlign: 'center',
        paddingTop: 16,
        paddingBottom: 12,
    },
    scroll: {
        flex: 1,
    },
    scrollContent: {
        paddingHorizontal: 16,
        paddingBottom: 32,
        gap: 12,
    },
    card: {
        flexDirection: 'row',
        alignItems: 'center',
        backgroundColor: colors.surface.card,
        borderRadius: 14,
        padding: 16,
        borderWidth: 1,
        borderColor: colors.grid.cellBorder,
    },
    badge: {
        width: 44,
        height: 44,
        borderRadius: 12,
        alignItems: 'center',
        justifyContent: 'center',
        marginRight: 14,
    },
    badgeText: {
        fontSize: 20,
        fontWeight: '800',
        color: '#ffffff',
    },
    cardContent: {
        flex: 1,
    },
    cardTitle: {
        fontSize: 17,
        fontWeight: '700',
        color: colors.text.primary,
        marginBottom: 2,
    },
    cardDesc: {
        fontSize: 13,
        color: colors.text.secondary,
        marginBottom: 2,
    },
    cardClues: {
        fontSize: 11,
        color: colors.text.muted,
    },
    arrow: {
        fontSize: 20,
        color: colors.text.muted,
        marginLeft: 8,
    },
});
