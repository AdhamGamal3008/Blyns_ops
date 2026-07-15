# Blyns ERP — fully custom multitenant ERP

Python FastAPI + MongoDB (database-per-tenant) backend, React + TypeScript
frontend. **All specs live in [`docs/`](docs/BUILD.md) — `docs/BUILD.md` is the
entry point.** Build phases and working rules: [`CLAUDE.md`](CLAUDE.md).

## Local quickstart (docs/ENVIRONMENTS.md §2)

```bash
# infra — either docker…
docker compose up -d mongo
# …or a locally installed mongod (any recent version)
mongod --dbpath <your-db-path> --port 27017

# backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env                 # set a real ERP_JWT_SECRET
python ../scripts/seed_control_plane.py   # lands in Phase 3
uvicorn app.main:app --reload --port 8000 # http://localhost:8000/health

# frontend (lands in Phase 5)
cd frontend
cp .env.example .env                 # VITE_API_BASE=http://localhost:8000/api/v1
npm install && npm run dev           # http://localhost:5173
```

## Tests

```bash
make test-fast    # backend unit + integration (boots an ephemeral mongod)
make test         # everything
make lint         # ruff + mypy
```

## Environments

`local` / `test` / `production` — same codebase, switched **only** by
`ERP_`-prefixed env vars (see `backend/.env.example` and
`docs/ENVIRONMENTS.md`). No secret or connection string is ever committed.
