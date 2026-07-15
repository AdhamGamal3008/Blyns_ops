# ADMIN PORTAL (Control Plane)

The platform operator's surface. Depends on `MULTITENANCY.md` and `AUTH_RBAC.md`.
All routes under `/api/v1/admin/...`, audience `erp-admin`, every route RBAC-guarded.

---

## 1. Company onboarding

`POST /api/v1/admin/companies` — RBAC: `companies` WRITE.

Request:
```json
{
  "name": "Acme Corp",
  "slug": "acme",
  "seat_limit": 25,
  "enabled_modules": ["dashboard","projects","crm","inventory","finance","settings"],
  "owner": { "name": "Jane Doe", "email": "jane@acme.com" },
  "security": { "failed_login_threshold": 5, "lockout_minutes": 15 }
}
```

Behavior:
1. Validate slug uniqueness and shape (`^[a-z0-9-]{3,40}$`).
2. Create company doc `status="provisioning"`.
3. Kick the provisioning engine (`MULTITENANCY.md` §3) which creates + seeds the
   tenant DB and the Owner user with a generated temp password
   (`must_reset_password=true`).
4. Return company + provisioning job id. Poll
   `GET /admin/companies/{id}/provisioning` for progress.

Other company endpoints:
- `GET /admin/companies` — list + filter by status/search; paginated.
- `GET /admin/companies/{id}` — detail incl. seats, storage snapshot, status.
- `PATCH /admin/companies/{id}` — edit name, enabled_modules (enabling a module
  runs its seed).
- `PATCH /admin/companies/{id}/status` — active/blocked/suspended.
- `DELETE /admin/companies/{id}` — teardown (WRITE + confirmation token).

---

## 2. Seat management

Seats = number of employees a company may create. Enforced on employee creation.

- `PATCH /admin/companies/{id}/seats` `{ "seat_limit": 40 }` — RBAC `seats` WRITE.
  - Increasing: always allowed.
  - Decreasing **below `seats_used`**: reject with `SEAT_LIMIT_REACHED` unless
    `force=true`, in which case require the admin to first block/remove the
    excess users. Never silently orphan users.
- Employee creation (client or admin side) checks
  `seats_used < seat_limit` → else `SEAT_LIMIT_REACHED`.
- `seats_used` is incremented on create, decremented on hard-delete; blocked
  users still count against seats (they occupy a seat) unless configured
  otherwise — document the choice in Settings.

Admin can also directly manage a company's employees:
- `GET /admin/companies/{id}/employees` — list.
- `POST /admin/companies/{id}/employees` — seed an employee from admin side
  (respects seat limit).
- `POST .../employees/{uid}/reset-password`, `.../unlock`, `.../block` — see
  `AUTH_RBAC.md` §5–6.

---

## 3. Admin users & admin roles

- `admin_users` CRUD — RBAC `admin_users` WRITE.
  - `GET/POST/PATCH/DELETE /admin/admin-users`.
  - Cannot delete the last Super Admin (guard).
  - Deactivate (`is_active=false`) instead of delete where possible.
- `admin_roles` CRUD — RBAC `admin_roles` WRITE. A role is a
  `{ name, permissions: { resource: Level } }` document. Editing a role
  re-evaluates access for all admins holding it on their next request (no cached
  stale permissions — see status/permission cache invalidation).

Role editor contract: the UI shows every admin resource with a 4-way selector
(None / View / Read / Write) mapping to `Level`. Server validates unknown
resources are rejected.

---

## 4. Platform dashboard — data sources

`GET /api/v1/admin/dashboard` — RBAC `dashboard` READ (VIEW returns headline
counts only, no drill-down). Aggregates four panels. All values computed
in-app (no external monitoring).

### 4.1 Server capacity (host)
From `psutil` in-process:
- CPU % (1s sample), load average.
- Memory: total / used / available %.
- Disk: total / used / free % on the data volume.
- Process: worker count, uptime.

### 4.2 Rate limits / activity throughput
From `rate_limit_buckets` + request counters (`ARCHITECTURE.md` §6):
- Requests per minute (platform-wide and top tenants).
- Count of `429 RATE_LIMITED` responses in the window.
- Per-tenant request share.

### 4.3 Storage
From MongoDB `dbStats` per database (`MULTITENANCY.md` §6), snapshotted into
`platform_metrics`:
- Control DB size.
- Per-tenant `dataSize / storageSize / indexSize / objects`.
- Total storage + top-N tenants by size + growth trend from snapshots.

### 4.4 Company activity (business)
Aggregated across tenants (read-only fan-out or pre-aggregated snapshots):
- Active companies, active users (logins in last 24h/7d).
- New companies onboarded (trend).
- Per-company: last activity, seats used/limit, status, module usage counts
  from each tenant's `activity_log`.

**Performance note:** do not fan out live queries to every tenant DB on each
dashboard load. A scheduled collector (APScheduler-style in-process loop, or a
`/admin/metrics/collect` task) writes rolling snapshots into
`platform_metrics`; the dashboard reads snapshots and only fetches host stats
(`psutil`) live.

### `platform_metrics` document
```json
{
  "_id":"…","captured_at":"ISO-8601","scope":"host|control|tenant",
  "tenant_id":"… or null",
  "metrics": {
    "cpu_pct":0,"mem_pct":0,"disk_pct":0,
    "data_size":0,"storage_size":0,"index_size":0,"objects":0,
    "requests_min":0,"rate_limited":0,
    "active_users_24h":0,"logins_24h":0
  }
}
```

---

## 5. Admin API surface (summary)

```
POST   /admin/auth/login
POST   /admin/auth/refresh
POST   /admin/auth/logout

GET    /admin/companies
POST   /admin/companies
GET    /admin/companies/{id}
PATCH  /admin/companies/{id}
DELETE /admin/companies/{id}
PATCH  /admin/companies/{id}/status
PATCH  /admin/companies/{id}/seats
PATCH  /admin/companies/{id}/security
GET    /admin/companies/{id}/provisioning

GET    /admin/companies/{id}/employees
POST   /admin/companies/{id}/employees
POST   /admin/companies/{id}/employees/{uid}/reset-password
POST   /admin/companies/{id}/employees/{uid}/unlock
PATCH  /admin/companies/{id}/employees/{uid}/block

GET    /admin/admin-users        (+ POST/PATCH/DELETE)
GET    /admin/admin-roles        (+ POST/PATCH/DELETE)

GET    /admin/dashboard
POST   /admin/metrics/collect     (manual snapshot trigger)
GET    /admin/audit-log
```

---

## 6. Acceptance criteria

- Onboarding produces an active company with a seeded tenant DB and a working
  Owner login using the temp password (forced reset on first login).
- Seat limit is enforced on both admin-side and client-side employee creation.
- Lowering seat limit below active seats is blocked unless excess users are
  handled first.
- Dashboard renders host/storage/rate/activity panels from snapshots + live host
  stats with no external service.
- Every admin write appears in `admin_audit_log` with actor, action, target.
