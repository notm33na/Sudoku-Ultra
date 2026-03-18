# Phase 4 API Endpoints

All game-service endpoints require a `Bearer` JWT unless marked **public**.
All responses follow `{ success, data, error, timestamp }` except where noted.

Base URL (local): `http://localhost:3001`
Via nginx gateway: `http://localhost:80/api/...`

---

## RAG Technique Tutor

### POST /ml/api/v1/tutor/ask

Ask the RAG tutor a question about a Sudoku solving technique.

**Request**
```json
{
  "question": "How does X-Wing work?",
  "top_k": 3
}
```

**Response 200**
```json
{
  "answer": "X-Wing is a fish pattern...",
  "sources": [
    { "name": "X-Wing", "score": 0.94 }
  ]
}
```

---

## XAI Technique Overlay

### POST /ml/api/v1/xai/explain

Return a per-cell SHAP importance heatmap for a given puzzle grid.

**Request**
```json
{
  "grid": [[0,5,0,...], ...],
  "difficulty": "hard"
}
```

**Response 200**
```json
{
  "cell_importance": [[0.12, 0.87, ...], ...],
  "feature_importances": {
    "candidate_density": 0.31,
    "constraint_saturation": 0.28
  },
  "difficulty_prediction": "hard"
}
```

---

## Gamified Technique Lessons

### GET /api/lessons

List all lessons with the authenticated user's progress.

**Response 200**
```json
{
  "success": true,
  "data": {
    "lessons": [
      {
        "id": "naked-singles",
        "name": "Naked Singles",
        "description": "...",
        "xpReward": 50,
        "badgeId": "naked-singles-badge",
        "stepCount": 5,
        "progress": { "stepsComplete": 3, "completed": false, "xpAwarded": 0 }
      }
    ]
  }
}
```

### GET /api/lessons/:id

Get a single lesson with full step content and current user progress.

### POST /api/lessons/:id/progress

Record progress on a step.

**Request**
```json
{ "stepIndex": 2 }
```

### POST /api/lessons/:id/complete

Mark a lesson as complete. Awards XP and badge if not already earned.

**Response 200**
```json
{
  "success": true,
  "data": {
    "xpAwarded": 50,
    "badgeAwarded": true,
    "badgeId": "naked-singles-badge",
    "totalXp": 150
  }
}
```

---

## Newbie Onboarding

### GET /api/onboarding/status

Get the authenticated user's onboarding progress.

**Response 200**
```json
{
  "success": true,
  "data": {
    "stepsComplete": 3,
    "totalSteps": 9,
    "completed": false,
    "skipped": false
  }
}
```

### POST /api/onboarding/step

Advance to the next onboarding step.

**Request**
```json
{ "stepIndex": 3 }
```

### POST /api/onboarding/complete

Mark onboarding as fully complete.

### POST /api/onboarding/skip

Skip the remaining onboarding steps.

---

## GAN Puzzle Generation

### POST /api/puzzles/generate-gan

Generate a puzzle using the WGAN-GP model.

**Request**
```json
{
  "difficulty": "hard",
  "mode": "puzzle",
  "symmetric": false
}
```

| Field | Type | Values | Default |
|---|---|---|---|
| `difficulty` | string | `easy \| medium \| hard \| super_hard \| extreme` | `medium` |
| `mode` | string | `solution \| puzzle \| constrained` | `puzzle` |
| `symmetric` | boolean | | `false` |

**Response 201**
```json
{
  "success": true,
  "data": {
    "id": "uuid",
    "grid": [[...]],
    "solution": [[...]],
    "difficulty": "hard",
    "clueCount": 28,
    "source": "gan"
  }
}
```

---

## Semantic Search / Puzzle Recommendations

### POST /api/puzzles/search

Proxy to ml-service semantic search.  Behaviour varies by `type`.

#### type: similar

Find puzzles similar to an existing puzzle.

**Request**
```json
{
  "type": "similar",
  "puzzle_id": "uuid",
  "top_k": 5,
  "difficulty_filter": "hard"
}
```

#### type: for-user

Personalised recommendations based on the user's play history.

**Request**
```json
{
  "type": "for-user",
  "top_k": 10,
  "exclude_puzzle_ids": ["uuid1", "uuid2"]
}
```

#### type: by-technique

Puzzles that require a specific technique.

**Request**
```json
{
  "type": "by-technique",
  "technique_name": "X-Wing",
  "top_k": 5,
  "difficulty_filter": "hard"
}
```

#### type: similar-features

Find puzzles matching a feature description without needing an existing puzzle.

**Request**
```json
{
  "type": "similar-features",
  "difficulty": "medium",
  "clue_count": 30,
  "techniques": ["Naked Singles", "Hidden Singles"],
  "top_k": 5
}
```

**Response 200 (all types)**
```json
{
  "success": true,
  "data": {
    "results": [
      {
        "puzzle_id": "uuid",
        "difficulty": "medium",
        "clue_count": 30,
        "techniques": ["Naked Singles"],
        "source": "engine",
        "score": 0.92
      }
    ],
    "count": 5
  }
}
```

---

## Friends System

### POST /api/friends/request

Send a friend request.

**Request**
```json
{ "addresseeId": "uuid" }
```

### POST /api/friends/:id/accept

Accept a pending friend request (`:id` = friendship ID).

### POST /api/friends/:id/decline

Decline a pending friend request.

### POST /api/friends/:id/block

Block a user (sets friendship status to `blocked`).

### GET /api/friends

List accepted friends with Elo ratings.

**Response 200**
```json
{
  "friends": [
    {
      "userId": "uuid",
      "username": "alice",
      "avatarUrl": null,
      "friendshipId": "uuid",
      "since": "2026-01-15T10:00:00.000Z",
      "eloRating": 1350
    }
  ],
  "count": 1
}
```

### GET /api/friends/pending

List incoming pending friend requests.

### GET /api/friends/feed

Cursor-paginated activity feed.

**Query params:** `limit` (default 20, max 50), `cursor` (ISO timestamp for pagination)

**Response 200**
```json
{
  "entries": [
    {
      "id": "uuid",
      "actorId": "uuid",
      "actorUsername": "alice",
      "actorAvatarUrl": null,
      "type": "puzzle_completed",
      "payload": { "difficulty": "hard", "score": 920 },
      "createdAt": "2026-03-18T12:00:00.000Z"
    }
  ],
  "nextCursor": "2026-03-18T11:59:00.000Z"
}
```

Activity types: `puzzle_completed | lesson_completed | badge_earned | friend_added`

### GET /api/friends/leaderboard

Elo-ranked leaderboard of the authenticated user and their accepted friends.

**Response 200**
```json
{
  "leaderboard": [
    {
      "rank": 1,
      "userId": "uuid",
      "username": "alice",
      "eloRating": 1400,
      "wins": 12,
      "losses": 3,
      "isMe": false
    }
  ]
}
```

---

## Pact Provider State Setup (test only)

### POST /_pact/provider-states

Registered only when `NODE_ENV=test`.  Used by the Pact Verifier to seed
the database before replaying each consumer interaction.

**Request**
```json
{ "state": "a user exists with email test@example.com" }
```

**Response 200**
```json
{ "state": "a user exists with email test@example.com", "status": "ok" }
```

Supported states:
- `game-service is running`
- `a user exists with email test@example.com`
- `an authenticated user with a streak`
- `an authenticated user with two friends`
- `an authenticated user with activity in their feed`
