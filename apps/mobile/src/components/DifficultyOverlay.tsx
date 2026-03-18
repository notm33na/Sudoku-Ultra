/**
 * DifficultyOverlay
 *
 * Renders a semi-transparent colour heat-map over the Sudoku board showing
 * which cells most influence the predicted difficulty rating.
 *
 * Colours:
 *   importance 0.0  →  transparent
 *   importance 0.5  →  amber  (#f59e0b, 40% opacity)
 *   importance 1.0  →  red    (#ef4444, 70% opacity)
 *
 * Props:
 *   cellImportances  – 81 floats (0–1) from /api/v1/xai/cell-importance
 *   topCells         – indices of the most important cells (shown with badge)
 *   visible          – toggle; when false renders nothing
 *   boardSize        – pixel width/height of the board (defaults to CELL_SIZE * 9 + 8)
 *   onToggle         – called when the XAI button is pressed
 */

import React, { useMemo } from 'react';
import {
    View,
    Text,
    TouchableOpacity,
    StyleSheet,
    Dimensions,
} from 'react-native';
import { CELL_SIZE } from './SudokuCell';

const BOARD_SIZE = CELL_SIZE * 9 + 8; // matches SudokuBoard

interface DifficultyOverlayProps {
    cellImportances: number[];   // 81 values, 0–1
    topCells?: number[];         // up to 9 indices
    visible: boolean;
    boardSize?: number;
    onToggle: () => void;
}

// ── Colour interpolation ──────────────────────────────────────────────────────

function importanceToColor(score: number): string {
    // 0.0 → transparent, 0.5 → amber, 1.0 → deep-red
    const alpha = score * 0.70;           // max 70% opacity
    if (score < 0.5) {
        // transparent → amber
        const t = score * 2;              // 0→1
        const r = Math.round(245 * t);
        const g = Math.round(158 * t);
        const b = Math.round(11 * t);
        return `rgba(${r},${g},${b},${alpha.toFixed(2)})`;
    } else {
        // amber → red
        const t = (score - 0.5) * 2;     // 0→1
        const r = Math.round(245 + (239 - 245) * t);
        const g = Math.round(158 + (68 - 158) * t);
        const b = Math.round(11 + (68 - 11) * t);
        return `rgba(${r},${g},${b},${alpha.toFixed(2)})`;
    }
}

// ── Cell overlay tile ─────────────────────────────────────────────────────────

const OverlayCell = React.memo(function OverlayCell({
    importance,
    isTop,
    size,
}: {
    importance: number;
    isTop: boolean;
    size: number;
}) {
    const bg = useMemo(() => importanceToColor(importance), [importance]);
    return (
        <View style={[styles.cell, { width: size, height: size, backgroundColor: bg }]}>
            {isTop && importance > 0.4 && (
                <View style={styles.topDot} />
            )}
        </View>
    );
});

// ── Main component ─────────────────────────────────────────────────────────────

export function DifficultyOverlay({
    cellImportances,
    topCells = [],
    visible,
    boardSize = BOARD_SIZE,
    onToggle,
}: DifficultyOverlayProps) {
    const cellSize = Math.floor((boardSize - 8) / 9); // subtract box-border gaps
    const topSet = useMemo(() => new Set(topCells), [topCells]);

    // Validate — show nothing on malformed data
    const safeImportances =
        cellImportances?.length === 81 ? cellImportances : new Array(81).fill(0);

    return (
        <>
            {/* Toggle button — always rendered so user can turn it on */}
            <TouchableOpacity
                style={[styles.toggleButton, visible && styles.toggleButtonActive]}
                onPress={onToggle}
                activeOpacity={0.8}
                accessibilityLabel="Toggle difficulty overlay"
                accessibilityRole="button"
            >
                <Text style={[styles.toggleText, visible && styles.toggleTextActive]}>
                    XAI
                </Text>
            </TouchableOpacity>

            {/* Overlay grid — absolutely positioned on top of the board */}
            {visible && (
                <View
                    style={[
                        styles.overlay,
                        { width: boardSize, height: boardSize },
                    ]}
                    pointerEvents="none"
                >
                    <View style={styles.grid}>
                        {safeImportances.map((importance, idx) => (
                            <OverlayCell
                                key={idx}
                                importance={importance}
                                isTop={topSet.has(idx)}
                                size={cellSize}
                            />
                        ))}
                    </View>

                    {/* Legend */}
                    <View style={styles.legend}>
                        <View style={[styles.legendSwatch, { backgroundColor: 'rgba(245,158,11,0.4)' }]} />
                        <Text style={styles.legendText}>influential</Text>
                        <View style={[styles.legendSwatch, { backgroundColor: 'rgba(239,68,68,0.7)', marginLeft: 8 }]} />
                        <Text style={styles.legendText}>critical</Text>
                    </View>
                </View>
            )}
        </>
    );
}

// ── Styles ────────────────────────────────────────────────────────────────────

const styles = StyleSheet.create({
    toggleButton: {
        paddingHorizontal: 10,
        paddingVertical: 4,
        borderRadius: 6,
        borderWidth: 1,
        borderColor: '#6b7280',
        backgroundColor: 'rgba(107,114,128,0.1)',
        alignSelf: 'flex-end',
        marginBottom: 4,
        marginRight: 4,
    },
    toggleButtonActive: {
        borderColor: '#f59e0b',
        backgroundColor: 'rgba(245,158,11,0.15)',
    },
    toggleText: {
        fontSize: 11,
        fontWeight: '700',
        color: '#6b7280',
        letterSpacing: 1,
    },
    toggleTextActive: {
        color: '#f59e0b',
    },
    overlay: {
        position: 'absolute',
        top: 0,
        left: 0,
    },
    grid: {
        flexDirection: 'row',
        flexWrap: 'wrap',
    },
    cell: {
        justifyContent: 'center',
        alignItems: 'center',
    },
    topDot: {
        width: 6,
        height: 6,
        borderRadius: 3,
        backgroundColor: 'rgba(239,68,68,0.9)',
    },
    legend: {
        position: 'absolute',
        bottom: -24,
        left: 0,
        flexDirection: 'row',
        alignItems: 'center',
    },
    legendSwatch: {
        width: 12,
        height: 12,
        borderRadius: 2,
    },
    legendText: {
        fontSize: 10,
        color: '#9ca3af',
        marginLeft: 4,
    },
});
