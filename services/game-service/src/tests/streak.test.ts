/**
 * Streak service — unit tests.
 *
 * Mocks prisma to test business logic in isolation:
 *   - 23-25 hour window
 *   - Calendar-day fallback
 *   - Freeze consumption on missed day
 *   - Weekly freeze grant
 *   - Milestone detection (7 / 30 / 100 / 365)
 *   - Streak broken (no freeze)
 *   - Idempotent same-session double-play
 */

import { updateStreak, getStreak } from '../services/streak.service';

// ─── Mock Prisma ─────────────────────────────────────────────────────────────

const mockStreak = {
    id: 'streak-1',
    userId: 'user-1',
    currentStreak: 5,
    longestStreak: 10,
    lastPlayedDate: null as Date | null,
    freezeCount: 0,
    lastFreezeGrantedAt: null as Date | null,
    milestonesAwarded: [] as number[],
};

const mockFindUnique = jest.fn();
const mockCreate = jest.fn();
const mockUpdate = jest.fn();

jest.mock('../prisma/client', () => ({
    prisma: {
        streak: {
            findUnique: (...args: unknown[]) => mockFindUnique(...args),
            create: (...args: unknown[]) => mockCreate(...args),
            update: (...args: unknown[]) => mockUpdate(...args),
        },
        user: {
            update: jest.fn(),
        },
    },
}));

// Helper: build a streak snapshot with overrides
function streak(overrides: Partial<typeof mockStreak> = {}) {
    return { ...mockStreak, ...overrides };
}

// Helper: date N hours ago
function hoursAgo(h: number): Date {
    return new Date(Date.now() - h * 60 * 60 * 1000);
}

// Helper: date N calendar days ago (same time of day)
function daysAgo(d: number): Date {
    const dt = new Date();
    dt.setUTCDate(dt.getUTCDate() - d);
    return dt;
}

beforeEach(() => {
    jest.clearAllMocks();
    // Default: update returns what we pass as data merged with existing
    mockUpdate.mockImplementation(({ data }) =>
        Promise.resolve({ ...mockStreak, ...data }),
    );
    mockCreate.mockImplementation(({ data }) =>
        Promise.resolve({ ...mockStreak, ...data }),
    );
});

// ─── First ever completion ────────────────────────────────────────────────────

test('creates streak on first completion', async () => {
    mockFindUnique.mockResolvedValue(null);
    const result = await updateStreak('user-1');
    expect(mockCreate).toHaveBeenCalledTimes(1);
    expect(result.currentStreak).toBe(1);
    expect(result.streakBroken).toBe(false);
    expect(result.freezeConsumed).toBe(false);
});

// ─── Already played recently (idempotent) ────────────────────────────────────

test('no change when played within 23 hours', async () => {
    const last = hoursAgo(2); // 2 hours ago
    mockFindUnique.mockResolvedValue(streak({ lastPlayedDate: last, currentStreak: 5 }));
    const result = await updateStreak('user-1');
    expect(mockUpdate).not.toHaveBeenCalled();
    expect(result.currentStreak).toBe(5);
    expect(result.streakBroken).toBe(false);
});

// ─── 23-25 hour window ────────────────────────────────────────────────────────

test('extends streak when played 24 hours ago (exact window)', async () => {
    const last = hoursAgo(24);
    mockFindUnique.mockResolvedValue(streak({ lastPlayedDate: last, currentStreak: 5 }));
    const result = await updateStreak('user-1');
    expect(result.currentStreak).toBe(6);
    expect(result.streakBroken).toBe(false);
});

test('extends streak at the edge of 25-hour grace window', async () => {
    const last = hoursAgo(24.9);
    mockFindUnique.mockResolvedValue(streak({ lastPlayedDate: last, currentStreak: 5 }));
    const result = await updateStreak('user-1');
    expect(result.currentStreak).toBe(6);
    expect(result.streakBroken).toBe(false);
});

// ─── Calendar-day fallback ────────────────────────────────────────────────────

test('extends streak for next calendar day (38h apart — outside 25h window)', async () => {
    // Simulate: played 8am Monday, now 10pm Tuesday (38 hours later)
    const last = daysAgo(1);
    last.setUTCHours(8, 0, 0, 0);
    mockFindUnique.mockResolvedValue(streak({ lastPlayedDate: last, currentStreak: 3 }));
    const result = await updateStreak('user-1');
    expect(result.currentStreak).toBe(4);
    expect(result.streakBroken).toBe(false);
});

test('breaks streak for 2+ calendar days missed with no freeze', async () => {
    const last = daysAgo(2);
    mockFindUnique.mockResolvedValue(streak({ lastPlayedDate: last, currentStreak: 5, freezeCount: 0 }));
    const result = await updateStreak('user-1');
    expect(result.currentStreak).toBe(1);
    expect(result.streakBroken).toBe(true);
    expect(result.freezeConsumed).toBe(false);
});

// ─── Freeze logic ─────────────────────────────────────────────────────────────

test('consumes freeze on missed day', async () => {
    const last = daysAgo(2);
    mockFindUnique.mockResolvedValue(streak({ lastPlayedDate: last, currentStreak: 5, freezeCount: 1 }));
    const result = await updateStreak('user-1');
    expect(result.currentStreak).toBe(6);
    expect(result.freezeConsumed).toBe(true);
    expect(result.streakBroken).toBe(false);
    const updateCall = mockUpdate.mock.calls[0][0];
    expect(updateCall.data.freezeCount).toBe(0);
});

test('grants weekly freeze when none available and 7 days elapsed', async () => {
    const last = hoursAgo(24); // consecutive — not a missed day
    const lastGranted = new Date(Date.now() - 8 * 24 * 60 * 60 * 1000); // 8 days ago
    mockFindUnique.mockResolvedValue(
        streak({ lastPlayedDate: last, currentStreak: 5, freezeCount: 0, lastFreezeGrantedAt: lastGranted }),
    );
    const result = await updateStreak('user-1');
    expect(result.currentStreak).toBe(6);
    // freeze granted and not consumed (it was a consecutive day, not a miss)
    expect(result.freezeConsumed).toBe(false);
    const updateCall = mockUpdate.mock.calls[0][0];
    expect(updateCall.data.freezeCount).toBe(1);
});

test('does not grant freeze if already holding one', async () => {
    const last = hoursAgo(24);
    mockFindUnique.mockResolvedValue(
        streak({ lastPlayedDate: last, currentStreak: 5, freezeCount: 1 }),
    );
    await updateStreak('user-1');
    const updateCall = mockUpdate.mock.calls[0][0];
    expect(updateCall.data.freezeCount).toBe(1); // unchanged
});

// ─── Milestones ───────────────────────────────────────────────────────────────

test('awards milestone at streak 7', async () => {
    const last = hoursAgo(24);
    mockFindUnique.mockResolvedValue(streak({ lastPlayedDate: last, currentStreak: 6, milestonesAwarded: [] }));
    const result = await updateStreak('user-1');
    expect(result.newMilestone).toBe(7);
    expect(result.milestonesAwarded).toContain(7);
});

test('awards milestone at streak 30', async () => {
    const last = hoursAgo(24);
    mockFindUnique.mockResolvedValue(streak({ lastPlayedDate: last, currentStreak: 29, milestonesAwarded: [7] }));
    const result = await updateStreak('user-1');
    expect(result.newMilestone).toBe(30);
    expect(result.milestonesAwarded).toContain(30);
});

test('does not re-award already awarded milestone', async () => {
    const last = hoursAgo(24);
    mockFindUnique.mockResolvedValue(
        streak({ lastPlayedDate: last, currentStreak: 6, milestonesAwarded: [7] }),
    );
    const result = await updateStreak('user-1');
    // Streak goes to 7 but it's already awarded
    expect(result.newMilestone).toBeNull();
});

// ─── getStreak ───────────────────────────────────────────────────────────────

test('getStreak returns zeros for new user', async () => {
    mockFindUnique.mockResolvedValue(null);
    const result = await getStreak('user-1');
    expect(result.currentStreak).toBe(0);
    expect(result.longestStreak).toBe(0);
    expect(result.milestonesAwarded).toEqual([]);
    expect(result.newMilestone).toBeNull();
});

test('getStreak returns existing data', async () => {
    const last = hoursAgo(10);
    mockFindUnique.mockResolvedValue(
        streak({ lastPlayedDate: last, currentStreak: 15, longestStreak: 42, freezeCount: 1, milestonesAwarded: [7] }),
    );
    const result = await getStreak('user-1');
    expect(result.currentStreak).toBe(15);
    expect(result.longestStreak).toBe(42);
    expect(result.freezeCount).toBe(1);
    expect(result.milestonesAwarded).toContain(7);
});
