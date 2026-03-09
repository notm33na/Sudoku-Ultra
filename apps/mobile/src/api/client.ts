const API_BASE_URL = process.env.EXPO_PUBLIC_API_URL || 'http://localhost:3001';

interface RequestOptions {
    method?: string;
    body?: unknown;
    token?: string;
}

async function request<T>(endpoint: string, options: RequestOptions = {}): Promise<T> {
    const { method = 'GET', body, token } = options;

    const headers: Record<string, string> = {
        'Content-Type': 'application/json',
    };
    if (token) {
        headers['Authorization'] = `Bearer ${token}`;
    }

    const response = await fetch(`${API_BASE_URL}${endpoint}`, {
        method,
        headers,
        body: body ? JSON.stringify(body) : undefined,
    });

    const data = await response.json();

    if (!response.ok) {
        throw new Error(data.error || `HTTP ${response.status}`);
    }

    return data.data as T;
}

// ─── Auth ─────────────────────────────────────────────────────────────────────

export const authApi = {
    register: (email: string, username: string, password: string) =>
        request('/api/auth/register', { method: 'POST', body: { email, username, password } }),
    login: (email: string, password: string) =>
        request('/api/auth/login', { method: 'POST', body: { email, password } }),
    refresh: (refreshToken: string) =>
        request('/api/auth/refresh', { method: 'POST', body: { refreshToken } }),
    me: (token: string) =>
        request('/api/auth/me', { token }),
};

// ─── Puzzles ──────────────────────────────────────────────────────────────────

export const puzzleApi = {
    generate: (difficulty: string, token: string) =>
        request('/api/puzzles/generate', { method: 'POST', body: { difficulty }, token }),
    getById: (id: string, token: string) =>
        request(`/api/puzzles/${id}`, { token }),
};

// ─── Sessions ─────────────────────────────────────────────────────────────────

export const sessionApi = {
    create: (puzzleId: string, token: string) =>
        request('/api/sessions', { method: 'POST', body: { puzzleId }, token }),
    getById: (id: string, token: string) =>
        request(`/api/sessions/${id}`, { token }),
    update: (id: string, body: unknown, token: string) =>
        request(`/api/sessions/${id}`, { method: 'PATCH', body, token }),
    getHint: (id: string, token: string) =>
        request(`/api/sessions/${id}/hint`, { method: 'POST', token }),
    validate: (id: string, token: string) =>
        request(`/api/sessions/${id}/validate`, { method: 'POST', token }),
    complete: (id: string, body: unknown, token: string) =>
        request(`/api/sessions/${id}/complete`, { method: 'POST', body, token }),
};

// ─── Scores ───────────────────────────────────────────────────────────────────

export const scoreApi = {
    leaderboard: (token: string, difficulty?: string) =>
        request(`/api/scores/leaderboard${difficulty ? `?difficulty=${difficulty}` : ''}`, { token }),
    myScores: (token: string) =>
        request('/api/scores/me', { token }),
};

// ─── Daily ────────────────────────────────────────────────────────────────────

export const dailyApi = {
    getToday: (token: string) =>
        request('/api/daily', { token }),
};

// ─── Streaks ──────────────────────────────────────────────────────────────────

export const streakApi = {
    getMyStreak: (token: string) =>
        request('/api/streaks/me', { token }),
};
