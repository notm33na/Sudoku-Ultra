import React, { useCallback } from 'react';
import { View, StyleSheet } from 'react-native';
import { Grid } from '@sudoku-ultra/shared-types';
import { SudokuCell, CELL_SIZE } from './SudokuCell';
import { colors } from '../theme/colors';

interface SudokuBoardProps {
    grid: Grid;
    selectedRow: number | null;
    selectedCol: number | null;
    onCellPress: (row: number, col: number) => void;
}

export const SudokuBoard = React.memo(function SudokuBoard({
    grid,
    selectedRow,
    selectedCol,
    onCellPress,
}: SudokuBoardProps) {
    const selectedValue =
        selectedRow !== null && selectedCol !== null
            ? grid[selectedRow]?.[selectedCol]?.value
            : null;

    const isPeer = useCallback(
        (row: number, col: number): boolean => {
            if (selectedRow === null || selectedCol === null) return false;
            if (row === selectedRow && col === selectedCol) return false;
            // Same row, col, or box
            return (
                row === selectedRow ||
                col === selectedCol ||
                (Math.floor(row / 3) === Math.floor(selectedRow / 3) &&
                    Math.floor(col / 3) === Math.floor(selectedCol / 3))
            );
        },
        [selectedRow, selectedCol],
    );

    const isHighlighted = useCallback(
        (row: number, col: number): boolean => {
            if (selectedValue === null || selectedValue === undefined) return false;
            const cell = grid[row]?.[col];
            return cell?.value === selectedValue && !(row === selectedRow && col === selectedCol);
        },
        [grid, selectedRow, selectedCol, selectedValue],
    );

    if (grid.length === 0) return null;

    return (
        <View style={styles.board}>
            {[0, 1, 2].map((boxRow) => (
                <View key={boxRow} style={styles.boxRow}>
                    {[0, 1, 2].map((boxCol) => (
                        <View key={boxCol} style={styles.box}>
                            {[0, 1, 2].map((cellRow) => {
                                const r = boxRow * 3 + cellRow;
                                return (
                                    <View key={cellRow} style={styles.cellRow}>
                                        {[0, 1, 2].map((cellCol) => {
                                            const c = boxCol * 3 + cellCol;
                                            return (
                                                <SudokuCell
                                                    key={c}
                                                    cell={grid[r][c]}
                                                    isSelected={r === selectedRow && c === selectedCol}
                                                    isHighlighted={isHighlighted(r, c)}
                                                    isPeerOfSelected={isPeer(r, c)}
                                                    onPress={() => onCellPress(r, c)}
                                                />
                                            );
                                        })}
                                    </View>
                                );
                            })}
                        </View>
                    ))}
                </View>
            ))}
        </View>
    );
});

const BOARD_SIZE = CELL_SIZE * 9 + 8; // cells + box border gaps

const styles = StyleSheet.create({
    board: {
        width: BOARD_SIZE,
        borderWidth: 2,
        borderColor: colors.grid.boxBorder,
        borderRadius: 4,
        overflow: 'hidden',
        alignSelf: 'center',
    },
    boxRow: {
        flexDirection: 'row',
    },
    box: {
        borderWidth: 1,
        borderColor: colors.grid.boxBorder,
    },
    cellRow: {
        flexDirection: 'row',
    },
});
