/**
 * Sudoku Ultra — AI Status Indicator Component
 *
 * Small icon showing whether AI is running on-device, via API, or rule-based.
 * Displayed in the header/status bar area.
 */

import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { getAIStatus } from '../services/edgeAI';

interface AIStatusIndicatorProps {
  compact?: boolean;
}

const STATUS_CONFIG = {
  'on-device': {
    icon: '🧠',
    label: 'On-Device AI',
    color: '#10B981',
    bgColor: 'rgba(16, 185, 129, 0.15)',
  },
  api: {
    icon: '☁️',
    label: 'Cloud AI',
    color: '#3B82F6',
    bgColor: 'rgba(59, 130, 246, 0.15)',
  },
  'rule-based': {
    icon: '📐',
    label: 'Offline',
    color: '#F59E0B',
    bgColor: 'rgba(245, 158, 11, 0.15)',
  },
};

export function AIStatusIndicator({ compact = false }: AIStatusIndicatorProps) {
  const { source } = getAIStatus();
  const config = STATUS_CONFIG[source];

  if (compact) {
    return (
      <View style={[styles.compactContainer, { backgroundColor: config.bgColor }]}>
        <Text style={styles.icon}>{config.icon}</Text>
      </View>
    );
  }

  return (
    <View style={[styles.container, { backgroundColor: config.bgColor }]}>
      <Text style={styles.icon}>{config.icon}</Text>
      <Text style={[styles.label, { color: config.color }]}>{config.label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 12,
    gap: 4,
  },
  compactContainer: {
    alignItems: 'center',
    justifyContent: 'center',
    width: 28,
    height: 28,
    borderRadius: 14,
  },
  icon: {
    fontSize: 14,
  },
  label: {
    fontSize: 11,
    fontWeight: '600',
    letterSpacing: 0.3,
  },
});
