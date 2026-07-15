# MULTITENANCY

Defines how tenants are isolated, provisioned, and seeded. **Database-per-tenant.**

---

## 1. Isolation model

- **Control plane:** exactly one database (`erp_control`). Holds the company
  registry, admin users/roles, provisioning jobs, and platform metrics.
- **Tenant plane:** each company owns a database named
  `{tenant_db_prefix}{slug}` (e.g. `erp_tenant_acme`). A tenant's data never
  leaves its own database. There are **no** shared business collections and
  **no** `tenant_id` discriminator columns — isolation is at the database level.

Why DB-per-tenant here: hard data isolation for enterprise/government clients,
trivial per-tenant backup/restore/export, per-tenant storage accounting for the
dashboard, and clean teardown on offboarding.

---

## 2. Company registry (control plane collection: `companies`)

```json
{
  "_id": "ObjectId",
  "name": "Acme Corp",
  "slug": "acme",                     // unique, url-safe, drives db_name
  "db_name": "erp_tenant_acme",
  "status": "active | blocked | suspended | provisioning | failed",
  "seat_limit": 25,                   // max employees allowed
  "seats_used": 4,                    // maintained on user create/delete
  "security": {
    "failed_login_threshold": 5,      // overrides global default
    "lockout_minutes": 15
  },
  "enabled_modules": ["dashboard","projects","crm","inventory","finance","settings"],
  "onboarded_by": "admin_user_id",
  "provisioned_at": "ISO-8601 | null",
  "created_at": "…", "updated_at": "…"
}
```

Indexes: unique on `slug`, unique on `db_name`, index on `status`.

---

## 3. Provisioning engine (`control_plane/provisioning/`)

Triggered by the admin "onboard company" action. Runs as an **idempotent,
resumable job** tracked in `provisioning_jobs`.

### Job document (`provisioning_jobs`)
```json
{
  "_id": "ObjectId",
  "company_id": "…",
  "type": "provision | teardown",
  "state": "pending | running | seeded | done | failed",
  "steps": [
    {"name": "create_db", "status": "done"},
    {"name": "build_indexes", "status": "done"},
    {"name": "seed_rbac", "status": "done"},
    {"name": "seed_modules", "status": "running"},
    {"name": "create_owner_user", "status": "pending"}
  ],
  "error": null,
  "created_at": "…", "finished_at": null
}
```

### Provision sequence
1. **Reserve** — write company doc with `status="provisioning"`, compute
   `slug`/`db_name`, guard against duplicate slug.
2. **create_db** — touch the tenant DB (Mongo creates lazily on first write).
3. **build_indexes + seed_modules** — import every enabled module's `seed()`
   from `modules/<name>/seed.py`; each creates its collections, indexes, and
   default documents. See §5.
4. **seed_rbac** — create default client roles (Owner, Manager, Member,
   Viewer). Owner = full WRITE on all modules.
5. **create_owner_user** — create the first employee (the client-side admin)
   from the onboarding payload, hash the temp password, assign Owner role,
   increment `seats_used`.
6. **seed_calendar/settings** — company profile + calendar defaults.
7. **finalize** — set company `status="active"`, `provisioned_at=now`, job
   `state="done"`. Write admin audit `company.onboarded`.

**Failure handling:** any step failure → job `state="failed"`, company
`status="failed"`, error captured. Re-running the job resumes from the first
non-`done` step (idempotent seeds: use `create index` (no-op if exists) and
`upsert` for default docs).

### Teardown (offboarding)
`type="teardown"` → export/backup hook (optional) → `dropDatabase` on the tenant
DB → company `status="suspended"` or hard-remove per admin choice. Hard delete is
the **only** place a full DB is dropped, and it requires WRITE admin permission.

---

## 4. Tenant resolution (`tenant/context.py`)

Order of resolution at request time:
1. Client access token carries `tenant` (the `db_name`) and `sub` (user id).
2. Load the company doc by `db_name`; if missing → `TENANT_NOT_FOUND`.
3. If `status != "active"` → `TENANT_BLOCKED`.
4. Hand the tenant DB handle (`db.tenant(db_name)`) to downstream deps.

The tenant is **never** taken from a header/query the client controls directly
for data access — it is bound to the signed token. (Login is the one place a
slug/email is accepted to *find* the tenant before a token exists; see
`AUTH_RBAC.md`.)

---

## 5. Module seeding contract

Each client module exposes:

```python
# modules/<name>/seed.py
async def seed(tenant_db) -> None:
    """Idempotent. Create collections, indexes, and default docs for THIS module.
    Must be safe to run multiple times."""
```

Provisioning calls, in order: `dashboard`, `settings`, `projects`, `crm`,
`inventory`, `finance` — but only those in `enabled_modules`. Enabling a module
later (from admin or client settings) runs that module's `seed()` on demand.

Example (projects):
```python
async def seed(tenant_db):
    await tenant_db.projects.create_index("status")
    await tenant_db.tasks.create_index([("project_id", 1), ("status", 1)])
    await tenant_db.tasks.create_index("due_date")
    # no default docs needed
```

---

## 6. Storage accounting (feeds admin dashboard)

Per tenant, on demand and on a schedule, run `db.command("dbStats")` against the
tenant DB to capture `dataSize`, `storageSize`, `indexSize`, `objects`. Persist
snapshots into control-plane `platform_metrics` so the dashboard can show
per-company storage and growth without recomputing every request. See
`ADMIN_PORTAL.md` §5.

---

## 7. Acceptance criteria

- Onboarding a company creates a new database named `erp_tenant_<slug>` that did
  not exist before, seeded with all enabled modules' collections + indexes and
  one Owner user.
- Re-running a failed provisioning job completes without duplicating data.
- A client token for tenant A cannot read or write tenant B's database under any
  request shape.
- Dropping a tenant DB removes only that company's data and leaves the control
  plane and other tenants intact.
