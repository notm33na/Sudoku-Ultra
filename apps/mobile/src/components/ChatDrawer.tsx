/**
 * ChatDrawer.tsx
 *
 * Slide-up drawer for in-game multiplayer chat.
 *
 * Features:
 * - Animated slide-up from bottom (Animated.Value on translateY)
 * - Message bubbles: own messages right-aligned, opponent left-aligned
 * - Unread badge on the chat toggle button while drawer is closed
 * - Client-side profanity filter applied to incoming messages before display
 * - Mute notification: shows inline banner when server sends chat_muted
 * - Auto-scroll to bottom on new messages
 *
 * Usage:
 *   <ChatDrawer
 *     messages={messages}
 *     isMuted={isMuted}
 *     myUserID="u1"
 *     onSend={(text) => ws.send({ type: 'chat_send', payload: { text } })}
 *   />
 */

import React, {
  useCallback,
  useEffect,
  useRef,
  useState,
} from 'react';
import {
  Animated,
  FlatList,
  KeyboardAvoidingView,
  Platform,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from 'react-native';
import { filterText } from '../utils/profanityFilter';
import { colors } from '../theme/colors';

// ── Types ──────────────────────────────────────────────────────────────────────

export interface ChatMessage {
  id: string;        // unique key (e.g. `${senderID}-${timestamp}`)
  senderID: string;
  displayName: string;
  text: string;
  timestamp: string; // RFC3339
}

interface ChatDrawerProps {
  messages: ChatMessage[];
  isMuted: boolean;
  myUserID: string;
  onSend: (text: string) => void;
}

// ── Constants ──────────────────────────────────────────────────────────────────

const DRAWER_HEIGHT = 340;
const MAX_INPUT_CHARS = 500;

// ── ChatDrawer ─────────────────────────────────────────────────────────────────

export function ChatDrawer({
  messages,
  isMuted,
  myUserID,
  onSend,
}: ChatDrawerProps) {
  const [open, setOpen] = useState(false);
  const [inputText, setInputText] = useState('');
  const [unread, setUnread] = useState(0);

  const translateY = useRef(new Animated.Value(DRAWER_HEIGHT)).current;
  const listRef = useRef<FlatList<ChatMessage>>(null);
  const prevMessageCount = useRef(messages.length);

  // Track unread count when drawer is closed.
  useEffect(() => {
    if (!open && messages.length > prevMessageCount.current) {
      setUnread((u) => u + (messages.length - prevMessageCount.current));
    }
    prevMessageCount.current = messages.length;
  }, [messages.length, open]);

  // Animate drawer open/close.
  useEffect(() => {
    Animated.spring(translateY, {
      toValue: open ? 0 : DRAWER_HEIGHT,
      useNativeDriver: true,
      bounciness: 4,
    }).start();
    if (open) {
      setUnread(0);
    }
  }, [open, translateY]);

  // Scroll to bottom when new messages arrive while open.
  useEffect(() => {
    if (open && messages.length > 0) {
      listRef.current?.scrollToEnd({ animated: true });
    }
  }, [messages.length, open]);

  const handleSend = useCallback(() => {
    const trimmed = inputText.trim();
    if (!trimmed || isMuted) return;
    onSend(trimmed);
    setInputText('');
  }, [inputText, isMuted, onSend]);

  const renderMessage = useCallback(
    ({ item }: { item: ChatMessage }) => {
      const isOwn = item.senderID === myUserID;
      const displayText = filterText(item.text);
      return (
        <View
          style={[
            styles.bubble,
            isOwn ? styles.bubbleOwn : styles.bubbleOpponent,
          ]}
        >
          {!isOwn && (
            <Text style={styles.bubbleSender}>{item.displayName}</Text>
          )}
          <Text
            style={[
              styles.bubbleText,
              isOwn ? styles.bubbleTextOwn : styles.bubbleTextOpponent,
            ]}
          >
            {displayText}
          </Text>
          <Text style={styles.bubbleTime}>
            {formatTime(item.timestamp)}
          </Text>
        </View>
      );
    },
    [myUserID],
  );

  return (
    <>
      {/* Toggle button */}
      <TouchableOpacity
        style={styles.toggleButton}
        onPress={() => setOpen((o) => !o)}
        activeOpacity={0.8}
        accessibilityLabel={open ? 'Close chat' : 'Open chat'}
        accessibilityRole="button"
      >
        <Text style={styles.toggleIcon}>💬</Text>
        {unread > 0 && !open && (
          <View style={styles.badge}>
            <Text style={styles.badgeText}>
              {unread > 9 ? '9+' : String(unread)}
            </Text>
          </View>
        )}
      </TouchableOpacity>

      {/* Drawer */}
      <Animated.View
        style={[styles.drawer, { transform: [{ translateY }] }]}
        pointerEvents={open ? 'auto' : 'none'}
      >
        {/* Header */}
        <View style={styles.drawerHeader}>
          <Text style={styles.drawerTitle}>Chat</Text>
          <TouchableOpacity onPress={() => setOpen(false)} hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}>
            <Text style={styles.closeIcon}>✕</Text>
          </TouchableOpacity>
        </View>

        {/* Mute banner */}
        {isMuted && (
          <View style={styles.muteBanner}>
            <Text style={styles.muteBannerText}>
              You are muted for this session.
            </Text>
          </View>
        )}

        {/* Message list */}
        <FlatList
          ref={listRef}
          data={messages}
          keyExtractor={(item) => item.id}
          renderItem={renderMessage}
          style={styles.messageList}
          contentContainerStyle={styles.messageListContent}
          showsVerticalScrollIndicator={false}
          onContentSizeChange={() =>
            listRef.current?.scrollToEnd({ animated: false })
          }
        />

        {/* Input */}
        <KeyboardAvoidingView
          behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        >
          <View style={styles.inputRow}>
            <TextInput
              style={[styles.input, isMuted && styles.inputMuted]}
              value={inputText}
              onChangeText={setInputText}
              placeholder={isMuted ? 'You are muted' : 'Message…'}
              placeholderTextColor={colors.text.muted}
              maxLength={MAX_INPUT_CHARS}
              returnKeyType="send"
              onSubmitEditing={handleSend}
              editable={!isMuted}
              accessibilityLabel="Chat input"
            />
            <TouchableOpacity
              style={[styles.sendButton, isMuted && styles.sendButtonMuted]}
              onPress={handleSend}
              disabled={isMuted || inputText.trim().length === 0}
              activeOpacity={0.7}
              accessibilityLabel="Send message"
              accessibilityRole="button"
            >
              <Text style={styles.sendIcon}>➤</Text>
            </TouchableOpacity>
          </View>
        </KeyboardAvoidingView>
      </Animated.View>
    </>
  );
}

// ── Helpers ────────────────────────────────────────────────────────────────────

function formatTime(rfc3339: string): string {
  try {
    const d = new Date(rfc3339);
    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  } catch {
    return '';
  }
}

// ── Styles ─────────────────────────────────────────────────────────────────────

const styles = StyleSheet.create({
  // Toggle button (floating, bottom-right of game screen)
  toggleButton: {
    position: 'absolute',
    bottom: 88,
    right: 16,
    width: 48,
    height: 48,
    borderRadius: 24,
    backgroundColor: colors.primary[700],
    alignItems: 'center',
    justifyContent: 'center',
    elevation: 4,
    shadowColor: '#000',
    shadowOpacity: 0.3,
    shadowRadius: 4,
    shadowOffset: { width: 0, height: 2 },
  },
  toggleIcon: {
    fontSize: 22,
  },

  // Unread badge
  badge: {
    position: 'absolute',
    top: -4,
    right: -4,
    minWidth: 18,
    height: 18,
    borderRadius: 9,
    backgroundColor: colors.error,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 4,
  },
  badgeText: {
    fontSize: 10,
    color: '#fff',
    fontWeight: '700',
  },

  // Drawer container
  drawer: {
    position: 'absolute',
    bottom: 0,
    left: 0,
    right: 0,
    height: DRAWER_HEIGHT,
    backgroundColor: colors.surface.card,
    borderTopLeftRadius: 16,
    borderTopRightRadius: 16,
    elevation: 8,
    shadowColor: '#000',
    shadowOpacity: 0.4,
    shadowRadius: 8,
    shadowOffset: { width: 0, height: -2 },
    overflow: 'hidden',
  },

  // Drawer header
  drawerHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 16,
    paddingVertical: 10,
    borderBottomWidth: 1,
    borderBottomColor: colors.grid.border,
  },
  drawerTitle: {
    fontSize: 15,
    fontWeight: '700',
    color: colors.text.primary,
  },
  closeIcon: {
    fontSize: 16,
    color: colors.text.secondary,
  },

  // Mute banner
  muteBanner: {
    backgroundColor: colors.error + '33', // 20% opacity
    paddingVertical: 6,
    paddingHorizontal: 16,
    borderBottomWidth: 1,
    borderBottomColor: colors.error + '55',
  },
  muteBannerText: {
    color: colors.error,
    fontSize: 12,
    fontWeight: '600',
    textAlign: 'center',
  },

  // Message list
  messageList: {
    flex: 1,
  },
  messageListContent: {
    paddingHorizontal: 12,
    paddingVertical: 8,
    gap: 6,
  },

  // Bubbles
  bubble: {
    maxWidth: '78%',
    paddingHorizontal: 12,
    paddingVertical: 7,
    borderRadius: 12,
    marginBottom: 2,
  },
  bubbleOwn: {
    alignSelf: 'flex-end',
    backgroundColor: colors.primary[700],
    borderBottomRightRadius: 3,
  },
  bubbleOpponent: {
    alignSelf: 'flex-start',
    backgroundColor: colors.surface.darkAlt,
    borderBottomLeftRadius: 3,
  },
  bubbleSender: {
    fontSize: 11,
    fontWeight: '700',
    color: colors.text.accent,
    marginBottom: 2,
  },
  bubbleText: {
    fontSize: 14,
    lineHeight: 18,
  },
  bubbleTextOwn: {
    color: '#fff',
  },
  bubbleTextOpponent: {
    color: colors.text.primary,
  },
  bubbleTime: {
    fontSize: 10,
    color: colors.text.muted,
    marginTop: 3,
    textAlign: 'right',
  },

  // Input row
  inputRow: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 12,
    paddingVertical: 8,
    borderTopWidth: 1,
    borderTopColor: colors.grid.border,
    gap: 8,
  },
  input: {
    flex: 1,
    height: 38,
    borderRadius: 19,
    backgroundColor: colors.surface.dark,
    paddingHorizontal: 14,
    fontSize: 14,
    color: colors.text.primary,
    borderWidth: 1,
    borderColor: colors.grid.border,
  },
  inputMuted: {
    opacity: 0.5,
  },
  sendButton: {
    width: 38,
    height: 38,
    borderRadius: 19,
    backgroundColor: colors.primary[600],
    alignItems: 'center',
    justifyContent: 'center',
  },
  sendButtonMuted: {
    backgroundColor: colors.grid.border,
  },
  sendIcon: {
    fontSize: 16,
    color: '#fff',
  },
});
