# Production image: the built React SPA and the FastAPI backend in ONE container,
# served from one origin (docs/DEPLOYMENT_PLAN.md Phase B).
#
# Same-origin is the whole design: frontend/.env.production sets
# VITE_API_BASE=/api/v1, so the browser calls the same host it loaded the app
# from. No CORS in production, no second web server, no proxy hop between the SPA
# and the API.
#
# Config is injected at runtime as ERP_* env vars — NO secrets or connection
# strings are baked in. Runs unprivileged behind a reverse proxy you control.
#
# Build from the REPO ROOT (it needs both trees):
#   docker build -t blyns-erp:local .

# --- stage 1: build the SPA ---------------------------------------------------
FROM node:22-alpine AS frontend

WORKDIR /frontend

# Install from the lockfile first so this layer caches until dependencies change.
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
# frontend/.env.production supplies VITE_API_BASE=/api/v1. `npm run build` also
# runs `tsc --noEmit`, so a type error fails the image build rather than shipping.
RUN npm run build

# Guard the silent failure this exact setup invites: if .env.production goes
# missing, vite leaves VITE_API_BASE undefined, api.ts falls back to
# "http://localhost:8000/api/v1", and the bundle ships pointing every visitor's
# browser at its OWN machine — a build that succeeds and an app that cannot talk
# to its server. Fail the build instead.
RUN if grep -rq "localhost:8000" dist/assets/*.js; then \
      echo "FATAL: built bundle references localhost:8000 — VITE_API_BASE did not" \
           "take effect. Is frontend/.env.production present in the build context?" >&2; \
      exit 1; \
    fi


# --- stage 2: the runtime -----------------------------------------------------
FROM python:3.12-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    # Running `python scripts/migrate.py` puts scripts/ on sys.path, NOT the
    # working directory, so `from app.core...` fails without this. uvicorn is
    # unaffected (it imports app.main from cwd), which is exactly why the gap only
    # shows up when you try to migrate a deployed database.
    PYTHONPATH=/app

WORKDIR /app

# curl is for the HEALTHCHECK below; no build toolchain is kept in the image.
RUN apt-get update \
    && apt-get install --no-install-recommends -y curl \
    && rm -rf /var/lib/apt/lists/*

# Dependencies first (declared in pyproject) so the layer caches until the
# manifest changes. Only the runtime extras — no dev/test tooling.
COPY backend/pyproject.toml ./
RUN pip install --upgrade pip && pip install .

# Application code, then the SPA built in stage 1.
COPY backend/app ./app

# Operational scripts must ship WITH the image: after a deploy you need to run
# migrations and seed the control plane, and the only place the app package and
# its dependencies exist is in here. Without this there is no way to migrate a
# production database short of installing Python and the deps on the host.
#   docker compose exec app python scripts/migrate.py
COPY scripts ./scripts

COPY --from=frontend /frontend/dist ./frontend_dist

# The app resolves the SPA from the repo layout by default, which does not exist
# here — point it at what we actually copied (docs/DEPLOYMENT_PLAN.md §3 gap #1).
ENV ERP_FRONTEND_DIST=/app/frontend_dist \
    SERVE_FRONTEND=1

# Drop root.
RUN useradd --create-home --uid 10001 appuser
USER appuser

EXPOSE 8000

# /health pings Mongo and returns 503 when it is unreachable, so an app that has
# lost its database is reported unhealthy and can be restarted by the orchestrator.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/health || exit 1

# ERP_ENV=production makes create_app fail fast on unsafe config
# (validate_for_production) and switch to structured JSON logging.
# Workers hold the rate limit across the pool via the Mongo-backed store.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
