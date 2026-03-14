/**
 * profanityFilter.ts
 *
 * Client-side, best-effort profanity filter.
 * Replaces matched words with asterisks before the message is displayed locally.
 * The authoritative moderation runs server-side (DistilBERT via ml-service).
 *
 * Usage:
 *   import { filterText, containsProfanity } from '@/utils/profanityFilter';
 *   const clean = filterText('Some bad word here');  // 'Some *** **** here'
 *   const bad   = containsProfanity('bad word');     // true
 */

// ── Word list ──────────────────────────────────────────────────────────────────
// Deliberately minimal — the server-side classifier handles nuanced cases.
// Extend conservatively: false positives harm UX more than false negatives here.
const BLOCKED_WORDS: ReadonlyArray<string> = [
  'idiot',
  'moron',
  'stupid',
  'retard',
  'loser',
  'noob',
  'suck',
  'sucks',
  'dumb',
  'crap',
  'damn',
  'hell',
  'ass',
  'bitch',
  'bastard',
  'cunt',
  'fuck',
  'fucking',
  'shit',
  'shitty',
  'piss',
  'cock',
  'dick',
  'pussy',
];

// Build a single regex from the word list at module load time (not per-call).
// \b word boundaries prevent matching substrings (e.g. "classic" for "ass").
const PATTERN = new RegExp(
  `\\b(${BLOCKED_WORDS.map((w) => escapeRegex(w)).join('|')})\\b`,
  'gi',
);

function escapeRegex(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

/** Replace each profane word with an equal-length asterisk string. */
export function filterText(text: string): string {
  return text.replace(PATTERN, (match) => '*'.repeat(match.length));
}

/** Return true if the text contains at least one blocked word. */
export function containsProfanity(text: string): boolean {
  PATTERN.lastIndex = 0; // reset stateful `g` flag
  return PATTERN.test(text);
}
