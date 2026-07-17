# Production backend image (docs/ENVIRONMENTS.md §4).
# Config is injected at runtime as ERP_* env vars — NO secrets or connection
# strings are baked in. Runs unprivileged behind a reverse proxy you control.
FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install dependencies first (declared in pyproject) so the layer caches until
# the manifest changes. Only the runtime extras — no dev/test tooling.
COPY pyproject.toml ./
RUN pip install --upgrade pip && pip install .

# Application code.
COPY app ./app

# Drop root.
RUN useradd --create-home --uid 10001 appuser
USER appuser

EXPOSE 8000

# ERP_ENV=production makes create_app fail fast on unsafe config
# (validate_for_production) and switch to structured JSON logging.
# Workers hold the rate limit across the pool via the Mongo-backed store.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
