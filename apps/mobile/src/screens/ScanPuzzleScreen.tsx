/**
 * ScanPuzzleScreen — CV-powered Sudoku scanner
 *
 * Flow:
 *   1. Camera viewfinder with capture button
 *   2. POST image to ml-service /api/v1/scan (multipart)
 *   3. Show 9×9 result grid:
 *      - Given cells: white
 *      - Empty cells: dark
 *      - Low-confidence cells (<0.70): amber highlight
 *   4. Tap any cell to cycle 0-9 (manual correction)
 *   5. "Start Puzzle" → create game session with scanned grid
 */

import React, { useCallback, useRef, useState } from 'react';
import {
    ActivityIndicator,
    Alert,
    Modal,
    Pressable,
    ScrollView,
    StyleSheet,
    Text,
    View,
} from 'react-native';
import { CameraView, useCameraPermissions } from 'expo-camera';
import { useNavigation } from '@react-navigation/native';

// ─── Config ───────────────────────────────────────────────────────────────────

const ML_SERVICE_URL = process.env.EXPO_PUBLIC_ML_SERVICE_URL ?? 'http://localhost:3003';
const CONFIDENCE_THRESHOLD = 0.70;

// ─── Types ────────────────────────────────────────────────────────────────────

type Phase = 'camera' | 'scanning' | 'review';

interface ScanResult {
    grid: number[];        // 81 values, 0 = empty
    confidence: number[];  // 81 confidence scores [0, 1]
    warnings: string[];
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function cellColor(value: number, confidence: number, editedCells: Set<number>, idx: number) {
    if (editedCells.has(idx)) return styles.cellEdited;
    if (value === 0) return styles.cellEmpty;
    if (confidence < CONFIDENCE_THRESHOLD) return styles.cellLowConf;
    return styles.cellGiven;
}

// ─── Main Component ───────────────────────────────────────────────────────────

export default function ScanPuzzleScreen() {
    const navigation = useNavigation<any>();
    const cameraRef = useRef<CameraView>(null);
    const [permission, requestPermission] = useCameraPermissions();

    const [phase, setPhase] = useState<Phase>('camera');
    const [scan, setScan] = useState<ScanResult | null>(null);
    const [grid, setGrid] = useState<number[]>(new Array(81).fill(0));
    const [editedCells, setEditedCells] = useState<Set<number>>(new Set());
    const [selectedCell, setSelectedCell] = useState<number | null>(null);
    const [errorMsg, setErrorMsg] = useState<string | null>(null);

    // ── Camera permission guard ───────────────────────────────────────────────
    if (!permission) return <View style={styles.container} />;

    if (!permission.granted) {
        return (
            <View style={styles.center}>
                <Text style={styles.permText}>Camera permission required to scan puzzles.</Text>
                <Pressable style={styles.btn} onPress={requestPermission}>
                    <Text style={styles.btnText}>Grant Permission</Text>
                </Pressable>
            </View>
        );
    }

    // ── Capture & scan ────────────────────────────────────────────────────────
    const handleCapture = useCallback(async () => {
        if (!cameraRef.current) return;
        setPhase('scanning');
        setErrorMsg(null);

        try {
            const photo = await cameraRef.current.takePictureAsync({
                quality: 0.85,
                base64: false,
                exif: false,
            });

            if (!photo?.uri) throw new Error('No photo captured');

            const formData = new FormData();
            formData.append('image', {
                uri: photo.uri,
                type: 'image/jpeg',
                name: 'scan.jpg',
            } as unknown as Blob);

            const response = await fetch(`${ML_SERVICE_URL}/api/v1/scan`, {
                method: 'POST',
                body: formData,
            });

            if (!response.ok) {
                throw new Error(`ml-service returned ${response.status}`);
            }

            const result: ScanResult = await response.json();
            setScan(result);
            setGrid([...result.grid]);
            setEditedCells(new Set());
            setPhase('review');

            if (result.warnings.length > 0) {
                Alert.alert('Scan warnings', result.warnings.join('\n'));
            }
        } catch (err) {
            setErrorMsg(String(err));
            setPhase('camera');
        }
    }, []);

    // ── Cell editing ──────────────────────────────────────────────────────────
    const handleCellPress = useCallback((idx: number) => {
        setSelectedCell(idx);
    }, []);

    const handleNumberPress = useCallback(
        (num: number) => {
            if (selectedCell === null) return;
            setGrid((prev) => {
                const next = [...prev];
                next[selectedCell] = num;
                return next;
            });
            setEditedCells((prev) => new Set(prev).add(selectedCell));
            setSelectedCell(null);
        },
        [selectedCell],
    );

    // ── Start puzzle ──────────────────────────────────────────────────────────
    const handleStartPuzzle = useCallback(() => {
        // Pass the scanned grid to GameScreen as route param
        navigation.navigate('Game', {
            scannedGrid: grid,
            difficulty: 'medium', // will be reclassified by edgeAI in GameScreen
        });
    }, [grid, navigation]);

    // ── Render: camera phase ──────────────────────────────────────────────────
    if (phase === 'camera') {
        return (
            <View style={styles.container}>
                <CameraView ref={cameraRef} style={styles.camera} facing="back">
                    {/* Alignment overlay */}
                    <View style={styles.overlay}>
                        <View style={styles.scanFrame} />
                        <Text style={styles.scanHint}>
                            Align the Sudoku grid inside the frame
                        </Text>
                    </View>
                </CameraView>

                {errorMsg && (
                    <View style={styles.errorBanner}>
                        <Text style={styles.errorText}>{errorMsg}</Text>
                    </View>
                )}

                <View style={styles.cameraControls}>
                    <Pressable style={styles.captureBtn} onPress={handleCapture}>
                        <View style={styles.captureInner} />
                    </Pressable>
                </View>
            </View>
        );
    }

    // ── Render: scanning phase ────────────────────────────────────────────────
    if (phase === 'scanning') {
        return (
            <View style={styles.center}>
                <ActivityIndicator size="large" color="#a78bfa" />
                <Text style={styles.scanningText}>Scanning puzzle…</Text>
            </View>
        );
    }

    // ── Render: review phase ──────────────────────────────────────────────────
    const lowConfCount = scan
        ? scan.confidence.filter((c, i) => grid[i] !== 0 && c < CONFIDENCE_THRESHOLD).length
        : 0;

    return (
        <ScrollView style={styles.container} contentContainerStyle={styles.reviewContent}>
            {/* Header */}
            <Text style={styles.heading}>Review Scanned Puzzle</Text>
            {lowConfCount > 0 && (
                <Text style={styles.warning}>
                    ⚠ {lowConfCount} cell{lowConfCount > 1 ? 's' : ''} flagged — tap to correct
                </Text>
            )}

            {/* 9×9 Grid */}
            <View style={styles.grid}>
                {Array.from({ length: 9 }, (_, row) => (
                    <View key={row} style={styles.gridRow}>
                        {Array.from({ length: 9 }, (_, col) => {
                            const idx = row * 9 + col;
                            const val = grid[idx];
                            const conf = scan?.confidence[idx] ?? 1;
                            const isSelected = selectedCell === idx;

                            const borderRight = (col + 1) % 3 === 0 && col < 8;
                            const borderBottom = (row + 1) % 3 === 0 && row < 8;

                            return (
                                <Pressable
                                    key={col}
                                    onPress={() => handleCellPress(idx)}
                                    style={[
                                        styles.cell,
                                        cellColor(val, conf, editedCells, idx),
                                        isSelected && styles.cellSelected,
                                        borderRight && styles.borderRight,
                                        borderBottom && styles.borderBottom,
                                    ]}
                                >
                                    <Text style={[
                                        styles.cellText,
                                        val === 0 && styles.cellTextEmpty,
                                        editedCells.has(idx) && styles.cellTextEdited,
                                    ]}>
                                        {val !== 0 ? String(val) : ''}
                                    </Text>
                                    {val !== 0 && conf < CONFIDENCE_THRESHOLD && !editedCells.has(idx) && (
                                        <Text style={styles.confDot}>●</Text>
                                    )}
                                </Pressable>
                            );
                        })}
                    </View>
                ))}
            </View>

            {/* Legend */}
            <View style={styles.legend}>
                <View style={[styles.legendSwatch, { backgroundColor: '#1e2130' }]} />
                <Text style={styles.legendLabel}>Given</Text>
                <View style={[styles.legendSwatch, { backgroundColor: '#78350f' }]} />
                <Text style={styles.legendLabel}>Low confidence — tap to fix</Text>
                <View style={[styles.legendSwatch, { backgroundColor: '#1e3a5f' }]} />
                <Text style={styles.legendLabel}>Manually corrected</Text>
            </View>

            {/* Actions */}
            <View style={styles.actions}>
                <Pressable style={styles.btnSecondary} onPress={() => setPhase('camera')}>
                    <Text style={styles.btnSecondaryText}>Rescan</Text>
                </Pressable>
                <Pressable style={styles.btn} onPress={handleStartPuzzle}>
                    <Text style={styles.btnText}>Start Puzzle →</Text>
                </Pressable>
            </View>

            {/* Number picker modal */}
            <Modal
                visible={selectedCell !== null}
                transparent
                animationType="fade"
                onRequestClose={() => setSelectedCell(null)}
            >
                <Pressable style={styles.modalBackdrop} onPress={() => setSelectedCell(null)}>
                    <View style={styles.numberPicker}>
                        <Text style={styles.pickerTitle}>Select value</Text>
                        <View style={styles.pickerGrid}>
                            {[1, 2, 3, 4, 5, 6, 7, 8, 9].map((n) => (
                                <Pressable
                                    key={n}
                                    style={styles.pickerCell}
                                    onPress={() => handleNumberPress(n)}
                                >
                                    <Text style={styles.pickerNum}>{n}</Text>
                                </Pressable>
                            ))}
                        </View>
                        <Pressable
                            style={styles.pickerClear}
                            onPress={() => handleNumberPress(0)}
                        >
                            <Text style={styles.pickerClearText}>Clear cell</Text>
                        </Pressable>
                    </View>
                </Pressable>
            </Modal>
        </ScrollView>
    );
}

// ─── Styles ───────────────────────────────────────────────────────────────────

const CELL_SIZE = 36;
const GRID_COLOR = '#3d4266';

const styles = StyleSheet.create({
    container: { flex: 1, backgroundColor: '#0f1117' },
    center: { flex: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: '#0f1117', gap: 16 },
    reviewContent: { paddingVertical: 32, paddingHorizontal: 16, alignItems: 'center' },

    // Camera
    camera: { flex: 1 },
    overlay: { flex: 1, justifyContent: 'center', alignItems: 'center', gap: 16 },
    scanFrame: {
        width: 280, height: 280,
        borderWidth: 2, borderColor: '#a78bfa',
        borderRadius: 4,
    },
    scanHint: { color: '#e2e8f0', fontSize: 13, textAlign: 'center', paddingHorizontal: 32 },
    cameraControls: { paddingBottom: 40, alignItems: 'center', backgroundColor: '#0f1117' },
    captureBtn: {
        width: 72, height: 72, borderRadius: 36,
        backgroundColor: '#a78bfa',
        justifyContent: 'center', alignItems: 'center',
        marginTop: 16,
    },
    captureInner: { width: 58, height: 58, borderRadius: 29, backgroundColor: '#fff' },

    // Scanning
    scanningText: { color: '#94a3b8', fontSize: 14, marginTop: 12 },

    // Review
    heading: { color: '#e2e8f0', fontSize: 20, fontWeight: '700', marginBottom: 8 },
    warning: { color: '#f59e0b', fontSize: 13, marginBottom: 16, textAlign: 'center' },
    errorBanner: { backgroundColor: '#7f1d1d', padding: 12 },
    errorText: { color: '#fca5a5', fontSize: 12, textAlign: 'center' },

    // Grid
    grid: { borderWidth: 2, borderColor: GRID_COLOR },
    gridRow: { flexDirection: 'row' },
    cell: {
        width: CELL_SIZE, height: CELL_SIZE,
        justifyContent: 'center', alignItems: 'center',
        borderWidth: 0.5, borderColor: GRID_COLOR,
    },
    cellGiven: { backgroundColor: '#1e2130' },
    cellEmpty: { backgroundColor: '#0f1117' },
    cellLowConf: { backgroundColor: '#78350f' },
    cellEdited: { backgroundColor: '#1e3a5f' },
    cellSelected: { backgroundColor: '#4c1d95' },
    borderRight: { borderRightWidth: 2, borderRightColor: GRID_COLOR },
    borderBottom: { borderBottomWidth: 2, borderBottomColor: GRID_COLOR },
    cellText: { color: '#e2e8f0', fontSize: 16, fontWeight: '600' },
    cellTextEmpty: { color: '#475569' },
    cellTextEdited: { color: '#93c5fd' },
    confDot: { position: 'absolute', top: 1, right: 2, fontSize: 6, color: '#f59e0b' },

    // Legend
    legend: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 16, justifyContent: 'center' },
    legendSwatch: { width: 12, height: 12, borderRadius: 2 },
    legendLabel: { color: '#64748b', fontSize: 11, marginRight: 8 },

    // Actions
    actions: { flexDirection: 'row', gap: 12, marginTop: 24 },
    btn: {
        backgroundColor: '#7c3aed', paddingHorizontal: 24, paddingVertical: 12,
        borderRadius: 10, flex: 1, alignItems: 'center',
    },
    btnText: { color: '#fff', fontWeight: '600', fontSize: 14 },
    btnSecondary: {
        backgroundColor: '#1e2130', paddingHorizontal: 24, paddingVertical: 12,
        borderRadius: 10, flex: 1, alignItems: 'center',
        borderWidth: 1, borderColor: '#3d4266',
    },
    btnSecondaryText: { color: '#94a3b8', fontWeight: '600', fontSize: 14 },

    // Permissions
    permText: { color: '#94a3b8', fontSize: 14, textAlign: 'center', paddingHorizontal: 32 },

    // Number picker
    modalBackdrop: {
        flex: 1, backgroundColor: 'rgba(0,0,0,0.7)',
        justifyContent: 'center', alignItems: 'center',
    },
    numberPicker: {
        backgroundColor: '#1a1d27', borderRadius: 16,
        padding: 20, width: 240,
        borderWidth: 1, borderColor: '#3d4266',
    },
    pickerTitle: { color: '#94a3b8', fontSize: 13, textAlign: 'center', marginBottom: 12 },
    pickerGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, justifyContent: 'center' },
    pickerCell: {
        width: 52, height: 52, backgroundColor: '#0f1117',
        justifyContent: 'center', alignItems: 'center',
        borderRadius: 8, borderWidth: 1, borderColor: '#3d4266',
    },
    pickerNum: { color: '#e2e8f0', fontSize: 20, fontWeight: '700' },
    pickerClear: {
        marginTop: 12, paddingVertical: 10, borderRadius: 8,
        backgroundColor: '#7f1d1d', alignItems: 'center',
    },
    pickerClearText: { color: '#fca5a5', fontWeight: '600', fontSize: 13 },
});
