# CLAUDE.md — Read me every session

You are building a **fully custom multitenant ERP**. Python FastAPI backend,
React + TypeScript frontend, MongoDB. The full specification lives in `docs/`.
**`docs/BUILD.md` is the entry point — read it first.**

## Non-negotiable rules
1. **Fully custom code.** No third-party SaaS, auth providers, paid APIs, managed
   queues, or external monitoring. Open-source libraries are fine.
2. **Database-per-tenant.** One control-plane DB; each company gets its own DB,
   provisioned + seeded at onboarding.
3. **Two auth realms.** Admins and client employees are separate pools, separate
   token audiences. Never let one realm's token reach the other's API.
4. **Every write is audited** (admin → control audit log; client → tenant
   activity_log).
5. **Three environments** — `local`, `test`, `production` — all config-driven. No
   hard-coded URIs, secrets, or ports.
6. **Tests ship with features.** A phase is not done until its tests pass.

## How to work
- **Before coding anything in a module, open and follow that module's spec in
  `docs/` (and `docs/modules/`).** Implement to its data models, endpoints, and
  **Acceptance criteria** sections — those are the definition of done.
- **Work one phase at a time** (see order below). At the start of each phase:
  read the relevant spec, output a short plan + file list, then implement.
- After each phase, **run the tests and the phase's "Prove:" check** before
  moving on. Commit at each phase boundary.
- Match the repo layout and conventions in `docs/ARCHITECTURE.md` exactly
  (naming, response envelope, error codes, module package shape).
- **Do not regenerate existing seed assets.** The Project Management seed already
  exists at `backend/app/modules/projects/stage_definitions.json` and
  `backend/app/modules/projects/seed.py` — wire them in, don't recreate them.
- If a spec is ambiguous, ask before inventing behavior.

## Build order (phases)
0. Orientation — read all specs, propose scaffold + plan.
1. Foundation — `ENVIRONMENTS.md` + `ARCHITECTURE.md`.
2. Multitenancy core — `MULTITENANCY.md` (wire the projects seed here).
3. Auth & RBAC — `AUTH_RBAC.md`.
4. Admin portal — `ADMIN_PORTAL.md`.
5. Client shell + Dashboard — `modules/CLIENT_DASHBOARD.md`.
6. Settings — `modules/SETTINGS.md` (client roles + `client_contact` role + approver map).
7. CRM — `modules/CRM.md`.
8. Inventory — `modules/INVENTORY.md`.
9. Finance — `modules/FINANCE.md`.
10. Project Management — `modules/PROJECT_MANAGEMENT.md` (integrates CRM/Inventory/Finance).
11. Hardening — rate limits, full test suite green, production config.

> Modules are ordered so that Project Management is built **last**, after the
> CRM, Inventory, and Finance modules it integrates with.

## Where things are
- `docs/` — all specs. `docs/modules/` — per-module specs.
- `backend/app/` — FastAPI app (see `docs/ARCHITECTURE.md` §4 for layout).
- `frontend/src/` — React app (`admin/`, `client/`, `shared/`).
- `scripts/` — control-plane seed + demo tenant provisioning.
