# ──────────────────────────────────────────────────────────────────────────────
# Multiplayer Service — Multi-stage Go build
# ──────────────────────────────────────────────────────────────────────────────

# Stage 1: Build
FROM golang:1.22-alpine AS builder

WORKDIR /app

COPY go.mod go.sum ./
RUN go mod download

COPY . .
RUN CGO_ENABLED=0 GOOS=linux go build -ldflags="-s -w" -o /multiplayer .

# Stage 2: Production
FROM alpine:3.19 AS runner

RUN apk --no-cache add ca-certificates && \
    addgroup -S appgroup && \
    adduser -S appuser -G appgroup

COPY --from=builder /multiplayer /multiplayer

USER appuser

EXPOSE 3002

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD wget --no-verbose --tries=1 --spider http://localhost:3002/health || exit 1

CMD ["/multiplayer"]
