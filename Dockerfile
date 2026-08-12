# ── Stage 1: builder ──────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /build

# Install build deps in a separate layer for cache efficiency
COPY requirements.txt .
RUN pip install --upgrade pip \
    && pip install --no-cache-dir --prefix=/install -r requirements.txt


# ── Stage 2: runtime ──────────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

# Non-root user for security
RUN addgroup --system app && adduser --system --ingroup app app

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy application source
COPY --chown=app:app app/ ./app/
COPY --chown=app:app alembic/ ./alembic/
COPY --chown=app:app alembic.ini .

USER app

EXPOSE 8000

# No curl/wget in the slim image — urllib is stdlib, so this needs nothing extra.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health/ready', timeout=3)" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
