# Branch Protection Rules

This document defines the required GitHub branch protection settings for
`main` and `develop`. Apply these via **Settings → Branches → Add rule** or
the GitHub CLI (`gh api`) after the repository is created.

---

## `main` branch

### Protection rule settings

| Setting | Value |
|---|---|
| Require a pull request before merging | ✅ enabled |
| Required approving reviews | **2** |
| Dismiss stale reviews on new commits | ✅ enabled |
| Require review from Code Owners | ✅ enabled (`.github/CODEOWNERS` must exist) |
| Require status checks to pass before merging | ✅ enabled |
| Require branches to be up to date before merging | ✅ enabled |
| Require conversation resolution before merging | ✅ enabled |
| Require signed commits | ✅ enabled |
| Require linear history (no merge commits) | ✅ enabled |
| Include administrators | ✅ enabled |
| Allow force pushes | ❌ disabled |
| Allow deletions | ❌ disabled |

### Required status checks (must all pass before merge)

These map to job names in `.github/workflows/ci.yml`:

```
Lint
Type-Check (shared-types)
Type-Check (sudoku-engine)
Type-Check (game-service)
Type-Check (mobile)
Unit Test — engine (Node 20)
Integration Test — game-service (Node 20)
Test — multiplayer (Go)
pytest — ml-service (Python 3.11)
Helm Lint
Terraform Validate
Pact Consumer Contracts
Pact Provider Verification — game-service
```

And from `.github/workflows/security.yml` (runs on push to main):

```
TruffleHog Secret Scan
```

### Applying via GitHub CLI

```bash
gh api repos/{owner}/{repo}/branches/main/protection \
  -X PUT \
  -H "Accept: application/vnd.github+json" \
  -f required_status_checks='{"strict":true,"contexts":["Lint","Type-Check (shared-types)","Type-Check (sudoku-engine)","Type-Check (game-service)","Type-Check (mobile)","Unit Test — engine (Node 20)","Integration Test — game-service (Node 20)","Test — multiplayer (Go)","pytest — ml-service (Python 3.11)","Helm Lint","Terraform Validate","Pact Consumer Contracts","Pact Provider Verification — game-service","TruffleHog Secret Scan"]}' \
  -f enforce_admins=true \
  -f required_pull_request_reviews='{"dismissal_restrictions":{},"dismiss_stale_reviews":true,"require_code_owner_reviews":true,"required_approving_review_count":2}' \
  -f restrictions=null \
  -f required_linear_history=true \
  -f allow_force_pushes=false \
  -f allow_deletions=false \
  -f required_conversation_resolution=true
```

---

## `develop` branch

### Protection rule settings

| Setting | Value |
|---|---|
| Require a pull request before merging | ✅ enabled |
| Required approving reviews | **1** |
| Dismiss stale reviews on new commits | ✅ enabled |
| Require status checks to pass before merging | ✅ enabled |
| Require branches to be up to date before merging | ✅ enabled |
| Allow force pushes | ❌ disabled |
| Allow deletions | ❌ disabled |

### Required status checks (develop)

```
Lint
Type-Check (shared-types)
Type-Check (sudoku-engine)
Type-Check (game-service)
Type-Check (mobile)
Unit Test — engine (Node 20)
Integration Test — game-service (Node 20)
Test — multiplayer (Go)
pytest — ml-service (Python 3.11)
Pact Consumer Contracts
```

---

## Branch naming convention

| Branch type | Pattern | Example |
|---|---|---|
| Feature | `feat/<ticket>-<slug>` | `feat/SU-142-friends-leaderboard` |
| Fix | `fix/<ticket>-<slug>` | `fix/SU-201-streak-reset` |
| Chore | `chore/<slug>` | `chore/upgrade-prisma` |
| Release | `release/<semver>` | `release/1.3.0` |
| Hotfix | `hotfix/<slug>` | `hotfix/auth-token-leak` |

---

## Commit message convention

All commits must follow [Conventional Commits](https://www.conventionalcommits.org/)
so that `git-cliff` can generate the CHANGELOG automatically:

```
<type>(<scope>): <description>

Types: feat | fix | perf | refactor | test | docs | chore | ci | build
Scope: optional, e.g. game-service | mobile | ml | multiplayer | infra

Breaking changes: append ! after type/scope, e.g. feat(auth)!: rotate JWT keys
```

The `release.yml` workflow auto-detects the version bump (`patch/minor/major`)
from commit types since the last tag:
- `feat:` → minor bump
- `fix:` / `chore:` / others → patch bump
- Any `!` breaking change → major bump

---

## CODEOWNERS

Create `.github/CODEOWNERS` to enforce ownership-based review requirements:

```
# Default: any change requires review from a core team member
*                   @your-org/core-team

# Infrastructure changes require infra team approval
/infra/             @your-org/infra-team
/.github/           @your-org/infra-team

# ML changes require ML team approval
/services/ml-service/  @your-org/ml-team
/ml/                   @your-org/ml-team

# Mobile changes require mobile team approval
/apps/mobile/       @your-org/mobile-team
```
