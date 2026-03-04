# ──────────────────────────────────────────────────────────────────────────────
# ML Service — Python 3.11 Docker build
# ──────────────────────────────────────────────────────────────────────────────

FROM python:3.11-slim AS runner

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN addgroup --system --gid 1001 mlgroup && \
    adduser --system --uid 1001 --ingroup mlgroup mluser

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

USER mluser

EXPOSE 3003

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD python -c "import httpx; r = httpx.get('http://localhost:3003/health'); assert r.status_code == 200" || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "3003"]
