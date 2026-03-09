# ──────────────────────────────────────────────────────────────────────────────
# ML Service — Multi-stage Docker build
# ──────────────────────────────────────────────────────────────────────────────

FROM python:3.11-slim AS builder

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY requirements.txt .

# Install build deps for numpy/scipy/opencv, then pip install
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc g++ libglib2.0-0 libsm6 libxrender1 libxext6 && \
    pip install --no-cache-dir --user -r requirements.txt && \
    apt-get purge -y gcc g++ && \
    apt-get autoremove -y && \
    rm -rf /var/lib/apt/lists/*

# ── Production stage ──────────────────────────────────────────────────────────
FROM python:3.11-slim AS runner

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PATH="/root/.local/bin:$PATH"

RUN addgroup --system --gid 1001 mlgroup && \
    adduser --system --uid 1001 --ingroup mlgroup mluser

# Copy installed packages from builder
COPY --from=builder /root/.local /home/mluser/.local
ENV PATH="/home/mluser/.local/bin:$PATH"

# Copy application code
COPY . .

# Create model directory
RUN mkdir -p ml/models && chown -R mluser:mlgroup ml/

USER mluser

EXPOSE 3003

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:3003/health')" || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "3003"]
