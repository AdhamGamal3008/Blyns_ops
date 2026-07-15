# ERP System — Master Build File

> **Read this file first.** It is the entry point for the build. It defines the
> stack, the non-negotiable rules, the repository layout, the build order, and
> links to every other spec. Do not start coding a module before reading its own
> `.md` file.

---

## 0. Golden rules (do not violate)

1. **Fully custom code.** No third-party SaaS, no external auth providers, no
   paid APIs, no managed queues, no external monitoring. Open-source *libraries*
   (FastAPI, Motor, PyMongo, Pydantic, psutil, PyJWT, bcrypt/argon2, React,
   Vite, etc.) are allowed. Anything that calls out to a company's servers is not.
2. **Database-per-tenant.** The control plane has one database. Every onboarded
   company gets its **own** MongoDB database, provisioned and seeded at
   onboarding time. Tenant data is never co-mingled in shared collections.
3. **Two separate auth realms.** Platform admins and client employees are
   different user pools, different token audiences, different login endpoints.
   A client token can never reach the admin API and vice-versa.
4. **Every write is audited.** Admin actions → control-plane audit log. Client
   actions → that tenant's `activity_log`.
5. **Three environments must work from day one:** `local`, `test`, `production`.
   No hard-coded connection strings, secrets, or ports. Everything via config.
6. **Tests ship with features.** A module is not "done" until its unit +
   integration tests pass. See `TESTING.md`.

---

## 1. Stack

| Layer      | Choice                                   |
|------------|------------------------------------------|
| Backend    | Python 3.12, FastAPI, Uvicorn            |
| Async DB   | Motor (async PyMongo) + Pydantic v2      |
| Auth       | Custom JWT (PyJWT), argon2 password hash |
| Frontend   | React 18 + Vite + TypeScript             |
| DB         | MongoDB 7.x                              |
| Host stats | psutil (in-process)                      |
| Tests      | pytest, pytest-asyncio, httpx, Vitest, Playwright |

---

## 2. Domain map

The system has **two planes**:

```
┌──────────────────────────────────────────────────────────────┐
│  CONTROL PLANE  (Admin Portal)   — single database            │
│  • Company registry & onboarding                              │
│  • Seat management (increase/decrease user limits)            │
│  • Block/unblock company or employee                          │
│  • Password reset + failed-login policy per company/employee  │
│  • Admin users & admin RBAC (NONE/VIEW/READ/WRITE)            │
│  • Platform dashboard: capacity, rate limits, storage,        │
│    activity across all tenants                                │
│  • Tenant provisioning + seeding engine                       │
└──────────────────────────────────────────────────────────────┘
              │ provisions & seeds  ▲ reads metrics from
              ▼                     │
┌──────────────────────────────────────────────────────────────┐
│  TENANT PLANE  (one DB per company)                           │
│  • Employees, client-side roles                               │
│  • Client Dashboard (quick actions, calendar, activity panel) │
│  • Project Management module                                  │
│  • CRM module                                                 │
│  • Inventory module                                           │
│  • Accounting & Finance module                                │
│  • Settings module                                            │
└──────────────────────────────────────────────────────────────┘
```

---

## 3. Spec index (build in this order)

| # | Spec file | What it covers | Depends on |
|---|-----------|----------------|------------|
| 1 | [`ARCHITECTURE.md`](./ARCHITECTURE.md) | Repo layout, config, DB connection strategy, shared conventions | — |
| 2 | [`MULTITENANCY.md`](./MULTITENANCY.md) | Control vs tenant DBs, provisioning, seeding, tenant resolution | 1 |
| 3 | [`AUTH_RBAC.md`](./AUTH_RBAC.md) | Both auth realms, JWT, failed-login lockout, blocking, admin RBAC | 1, 2 |
| 4 | [`ADMIN_PORTAL.md`](./ADMIN_PORTAL.md) | Onboarding, seat mgmt, admin users, platform dashboard | 2, 3 |
| 5 | [`modules/CLIENT_DASHBOARD.md`](./modules/CLIENT_DASHBOARD.md) | Quick actions, calendar view, activity panel | 3 |
| 6 | [`modules/PROJECT_MANAGEMENT.md`](./modules/PROJECT_MANAGEMENT.md) | 16-stage construction/fabrication stage-gate state machine (approval + decision engines, physical gates) | 5, 7, 8, 9 |
| 7 | [`modules/CRM.md`](./modules/CRM.md) | Contacts, accounts, leads, deals, pipeline | 5 |
| 8 | [`modules/INVENTORY.md`](./modules/INVENTORY.md) | Products, warehouses, stock movements | 5 |
| 9 | [`modules/FINANCE.md`](./modules/FINANCE.md) | Chart of accounts, journals, invoices, payments | 5, 8 |
| 10 | [`modules/SETTINGS.md`](./modules/SETTINGS.md) | Company profile, client roles, calendar config, module toggles | 5 |
| 11 | [`TESTING.md`](./TESTING.md) | Test strategy, fixtures, coverage gates, CI | all |
| 12 | [`ENVIRONMENTS.md`](./ENVIRONMENTS.md) | local / test / production config & run | 1 |

---

## 4. Repository layout

```
erp-system/
├── backend/
│   ├── app/
│   │   ├── main.py                 # FastAPI app factory, router mounting
│   │   ├── core/
│   │   │   ├── config.py           # env-driven settings (pydantic-settings)
│   │   │   ├── security.py         # hashing, JWT encode/decode
│   │   │   ├── db.py               # connection manager (control + tenant pools)
│   │   │   ├── rate_limit.py       # custom Mongo/in-memory limiter
│   │   │   ├── audit.py            # audit + activity writers
│   │   │   └── errors.py           # exception handlers, error envelope
│   │   ├── control_plane/          # ADMIN PORTAL (see ADMIN_PORTAL.md)
│   │   │   ├── companies/
│   │   │   ├── admin_users/
│   │   │   ├── metrics/
│   │   │   └── provisioning/
│   │   ├── tenant/
│   │   │   ├── context.py          # resolve tenant from token/slug
│   │   │   └── deps.py             # FastAPI deps: tenant db, current user
│   │   ├── auth/
│   │   │   ├── admin_auth.py
│   │   │   └── client_auth.py
│   │   ├── modules/                # CLIENT MODULES (one package each)
│   │   │   ├── dashboard/
│   │   │   ├── projects/
│   │   │   ├── crm/
│   │   │   ├── inventory/
│   │   │   ├── finance/
│   │   │   └── settings/
│   │   └── shared/                 # pydantic bases, pagination, enums
│   ├── tests/
│   │   ├── unit/
│   │   ├── integration/
│   │   └── conftest.py
│   ├── pyproject.toml
│   └── .env.example
├── frontend/
│   ├── src/
│   │   ├── admin/                  # admin portal SPA area
│   │   ├── client/                 # tenant SPA area (modules)
│   │   ├── shared/                 # api client, auth store, ui kit
│   │   └── main.tsx
│   ├── package.json
│   └── .env.example
├── docs/                           # THIS folder
├── scripts/
│   ├── seed_control_plane.py       # first admin + default roles
│   └── provision_demo_tenant.py
├── docker-compose.yml              # local mongo + services
└── README.md
```

---

## 5. Cross-cutting conventions

- **IDs:** Mongo `ObjectId` internally; expose as string `id` in all API bodies.
- **Timestamps:** UTC, stored as BSON date, serialized ISO-8601. Every document
  has `created_at`, `updated_at`, `created_by`, `updated_by`.
- **Soft delete:** documents carry `is_deleted: bool` + `deleted_at`. Hard
  delete only via admin provisioning teardown.
- **Response envelope:**
  ```json
  { "data": { }, "meta": { "page": 1, "page_size": 25, "total": 0 } }
  ```
  Errors:
  ```json
  { "error": { "code": "SEAT_LIMIT_REACHED", "message": "…", "details": {} } }
  ```
- **Pagination:** `?page=&page_size=` (max page_size 100), cursor optional later.
- **Naming:** API routes `kebab-case`, JSON fields `snake_case`, TS types
  `PascalCase`, React components `PascalCase`.
- **Every module router** is versioned under `/api/v1/...` and, for tenant
  routes, always resolves tenant context before touching data.

---

## 6. Build phases (suggested milestones)

1. **Foundation:** config, DB connection manager, error envelope, health check,
   `ENVIRONMENTS.md` working locally with docker-compose.
2. **Multitenancy core:** control-plane models, provisioning + seeding engine,
   tenant resolution. Prove: onboard a company → new DB appears + seeded.
3. **Auth & RBAC:** both realms, JWT, lockout, blocking, admin roles.
4. **Admin portal:** companies CRUD, seat mgmt, admin users, platform dashboard.
5. **Client shell + Dashboard:** login, tenant routing, calendar, activity panel.
6. **Client modules** in index order (6→10). Each behind a settings toggle.
7. **Hardening:** rate limits, full test suite green, production config.

Each phase ends with its module tests green before the next begins.
