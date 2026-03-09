import React from 'react';
import { TouchableOpacity, Text, View, StyleSheet, Dimensions } from 'react-native';
import { Cell, CellStatus } from '@sudoku-ultra/shared-types';
import { colors } from '../theme/colors';

const SCREEN_WIDTH = Dimensions.get('window').width;
const BOARD_PADDING = 8;
const CELL_SIZE = Math.floor((SCREEN_WIDTH - BOARD_PADDING * 2 - 12) / 9); // 12 for box borders

interface SudokuCellProps {
    cell: Cell;
    isSelected: boolean;
    isHighlighted: boolean;
    isPeerOfSelected: boolean;
    onPress: () => void;
}

export const SudokuCell = React.memo(function SudokuCell({
    cell,
    isSelected,
    isHighlighted,
    isPeerOfSelected,
    onPress,
}: SudokuCellProps) {
    const bgColor = isSelected
        ? colors.cell.selected
        : isPeerOfSelected
            ? colors.cell.highlighted
            : cell.status === CellStatus.ERROR
                ? colors.cell.error
                : cell.status === CellStatus.GIVEN
                    ? colors.cell.given
                    : colors.cell.empty;

    const textColor = isSelected
        ? colors.cell.selectedText
        : cell.status === CellStatus.ERROR
            ? colors.cell.errorText
            : cell.status === CellStatus.GIVEN
                ? colors.cell.givenText
                : isHighlighted
                    ? colors.cell.highlightedText
                    : colors.cell.emptyText;

    const hasNotes = cell.value === null && cell.notes.length > 0;

    return (
        <TouchableOpacity
            style={[styles.cell, { backgroundColor: bgColor }]}
            onPress={onPress}
            activeOpacity={0.7}
        >
            {cell.value !== null ? (
                <Text
                    style={[
                        styles.valueText,
                        { color: textColor },
                        cell.isLocked && styles.givenText,
                    ]}
                >
                    {cell.value}
                </Text>
            ) : hasNotes ? (
                <View style={styles.notesContainer}>
                    {[1, 2, 3, 4, 5, 6, 7, 8, 9].map((n) => (
                        <Text
                            key={n}
                            style={[
                                styles.noteText,
                                cell.notes.includes(n) ? styles.noteVisible : styles.noteHidden,
                            ]}
                        >
                            {n}
                        </Text>
                    ))}
                </View>
            ) : null}
        </TouchableOpacity>
    );
});

const styles = StyleSheet.create({
    cell: {
        width: CELL_SIZE,
        height: CELL_SIZE,
        alignItems: 'center',
        justifyContent: 'center',
        borderWidth: 0.5,
        borderColor: colors.grid.cellBorder,
    },
    valueText: {
        fontSize: CELL_SIZE * 0.5,
        fontWeight: '600',
        fontVariant: ['tabular-nums'],
    },
    givenText: {
        fontWeight: '800',
    },
    notesContainer: {
        flexDirection: 'row',
        flexWrap: 'wrap',
        width: CELL_SIZE - 2,
        height: CELL_SIZE - 2,
        alignItems: 'center',
        justifyContent: 'center',
    },
    noteText: {
        width: (CELL_SIZE - 2) / 3,
        height: (CELL_SIZE - 2) / 3,
        fontSize: CELL_SIZE * 0.2,
        textAlign: 'center',
        lineHeight: (CELL_SIZE - 2) / 3,
    },
    noteVisible: {
        color: colors.cell.noteText,
    },
    noteHidden: {
        color: 'transparent',
    },
});

export { CELL_SIZE };
