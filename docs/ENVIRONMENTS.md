# ENVIRONMENTS

Three environments must work from day one: `local`, `test`, `production`.
Everything is config-driven — no hard-coded URIs, secrets, or ports.

---

## 1. Config matrix

| Setting (`ERP_` prefix) | local | test | production |
|---|---|---|---|
| `ERP_ENV` | local | test | production |
| `ERP_MONGO_URI` | `mongodb://localhost:27017` | ephemeral / `mongodb://localhost:27018` | injected secret (replica set) |
| `ERP_CONTROL_DB_NAME` | `erp_control` | `erp_control_test` | `erp_control` |
| `ERP_TENANT_DB_PREFIX` | `erp_tenant_` | `test_tenant_` | `erp_tenant_` |
| `ERP_JWT_SECRET` | dev value in `.env` | random per run | injected secret (never in repo) |
| `ERP_ACCESS_TOKEN_TTL_MIN` | 60 | 5 | 15 |
| rate limit | lenient / in-memory | disabled or high | strict / Mongo-backed |
| CORS | `http://localhost:5173` | n/a | exact frontend origin(s) |
| Docs (`/docs`) | on | on | off (or auth-gated) |
| Logging | debug, pretty | warning | info, structured JSON |

Load precedence: real environment variables > `.env` file > defaults in
`config.py`. `.env` is git-ignored; ship `.env.example`.

---

## 2. Local development

### docker-compose (`docker-compose.yml`)
- `mongo` (7.x) on `27017`, named volume for persistence.
- Optional `mongo-express` for inspection (dev only; it's an open tool, not a
  product integration — remove for production).

### Run
```bash
# infra
docker compose up -d mongo

# backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env                 # fill ERP_JWT_SECRET etc.
python scripts/seed_control_plane.py # first super admin + admin roles
uvicorn app.main:app --reload --port 8000

# frontend
cd frontend
cp .env.example .env                 # VITE_API_BASE=http://localhost:8000/api/v1
npm install
npm run dev                          # http://localhost:5173
```

### Demo data
`python scripts/provision_demo_tenant.py` onboards an "acme" company end-to-end
so you can log into the client side immediately.

---

## 3. Test environment
- Spun up by the test suite, not run by hand. Uses an ephemeral `mongod` (random
  port) or a dedicated test port so it never touches local/dev data.
- Short token TTLs, deterministic clock, rate limiting disabled or set high.
- Databases are created and dropped per test run (see `TESTING.md`).

---

## 4. Production
- **Config via injected environment/secrets only.** `ERP_JWT_SECRET`,
  `ERP_MONGO_URI` never in the repo or image.
- MongoDB as a **replica set** (needed for multi-document transactions used in
  inventory movements + finance posting) with authentication enabled and TLS.
- Run backend under a process manager (e.g. `uvicorn` workers behind a reverse
  proxy you control). Rate limiting **Mongo-backed** so it holds across workers.
- `/docs` disabled or behind admin auth. CORS locked to the real frontend
  origin(s). Structured JSON logs.
- **Backups:** per-tenant `mongodump` is trivial because each company is its own
  database — enables per-company restore/export without touching others.
- **Migrations:** a versioned migration runner (custom) applies control-plane and
  per-tenant schema/index changes; on deploy, iterate tenants and run pending
  migrations idempotently (reuse each module's `seed()` for index creation).
- Health: `GET /health` (mongo ping + build info) for your own uptime checks.

---

## 5. Build/run targets (`Makefile`)
```
make dev            # docker mongo + backend reload + frontend dev
make seed           # seed control plane
make demo           # provision demo tenant
make test           # full test suite (see TESTING.md)
make test-fast      # unit + integration, no e2e
make lint           # ruff + mypy + eslint
make build-prod     # frontend build + backend image
```

---

## 6. Acceptance criteria
- The same codebase runs in all three environments switching only env vars.
- No secret or connection string is committed.
- Production uses a replica set and Mongo-backed rate limiting; `/docs` is not
  publicly open.
- A single tenant can be backed up/restored independently of others.
