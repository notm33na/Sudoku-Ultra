# ──────────────────────────────────────────────────────────────────────────────
# Game Service — Multi-stage Docker build (monorepo-aware)
# ──────────────────────────────────────────────────────────────────────────────
# Build context must be the monorepo root:
#   docker build -f services/game-service/Dockerfile .

# Stage 1: Build
FROM node:20-alpine AS builder

WORKDIR /app

# Copy root manifests for monorepo dependency resolution
COPY package.json package-lock.json turbo.json tsconfig.base.json ./

# Copy workspace package manifests
COPY packages/shared-types/package.json packages/shared-types/
COPY packages/sudoku-engine/package.json packages/sudoku-engine/
COPY services/game-service/package.json services/game-service/

# Install all workspace dependencies
RUN npm ci --workspace=packages/shared-types \
           --workspace=packages/sudoku-engine \
           --workspace=services/game-service

# Copy source code
COPY packages/shared-types/ packages/shared-types/
COPY packages/sudoku-engine/ packages/sudoku-engine/
COPY services/game-service/ services/game-service/

# Build shared packages first, then game-service
RUN npx turbo build --filter=@sudoku-ultra/game-service

# Generate Prisma client
RUN cd services/game-service && npx prisma generate

# Stage 2: Production
FROM node:20-alpine AS runner

WORKDIR /app

ENV NODE_ENV=production

RUN addgroup --system --gid 1001 nodejs && \
    adduser --system --uid 1001 gameservice

# Copy built artifacts
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/packages/shared-types/dist ./packages/shared-types/dist
COPY --from=builder /app/packages/shared-types/package.json ./packages/shared-types/
COPY --from=builder /app/packages/sudoku-engine/dist ./packages/sudoku-engine/dist
COPY --from=builder /app/packages/sudoku-engine/package.json ./packages/sudoku-engine/
COPY --from=builder /app/services/game-service/dist ./services/game-service/dist
COPY --from=builder /app/services/game-service/prisma ./services/game-service/prisma
COPY --from=builder /app/services/game-service/package.json ./services/game-service/
COPY --from=builder /app/services/game-service/node_modules/.prisma ./services/game-service/node_modules/.prisma
COPY --from=builder /app/package.json ./

USER gameservice

WORKDIR /app/services/game-service

EXPOSE 3001

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD wget --no-verbose --tries=1 --spider http://localhost:3001/health || exit 1

CMD ["node", "dist/index.js"]
