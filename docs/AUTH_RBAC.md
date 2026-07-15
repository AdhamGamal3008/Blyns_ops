# AUTH & RBAC

Covers both auth realms, failed-login lockout, block/unblock, and the admin
permission model (`NONE / VIEW / READ / WRITE`).

---

## 1. Two realms

| | Admin realm | Client realm |
|---|---|---|
| User pool | `control.admin_users` | `tenant.users` |
| Login endpoint | `POST /api/v1/admin/auth/login` | `POST /api/v1/auth/login` |
| Token audience | `erp-admin` | `erp-client` |
| Tenant claim | none | `db_name` bound into token |

A token is only accepted by handlers whose expected audience matches. Decoding
with the wrong audience → `PERMISSION_DENIED`.

---

## 2. Permission model (`NONE / VIEW / READ / WRITE`)

Your requirement — *"view or not, view + read, view + read + write"* — maps to a
4-level ordered enum applied **per resource**:

```python
class Level(IntEnum):
    NONE  = 0   # cannot view; resource hidden
    VIEW  = 1   # can see it exists (listing/labels) but not open details
    READ  = 2   # view + read full details
    WRITE = 3   # view + read + create/update/delete
```

A role is a map of `resource -> Level`. The guard is a simple `>=` check:

```python
def require(resource: str, needed: Level):
    async def _dep(user = Depends(current_user)):
        if user.role.level_for(resource) < needed:
            raise DomainError("PERMISSION_DENIED", ...)
        return user
    return _dep
```

### Admin resources
`companies`, `seats`, `admin_users`, `admin_roles`, `dashboard`,
`provisioning`, `security_policy`.

Example admin roles seeded by `scripts/seed_control_plane.py`:
- **Super Admin** — WRITE on everything.
- **Operator** — WRITE on `companies`,`seats`,`security_policy`; READ on
  `dashboard`; NONE on `admin_users`,`admin_roles`.
- **Auditor** — READ on `dashboard`,`companies`; NONE elsewhere.
- **Observer** — VIEW on `dashboard` only.

### Client resources
`dashboard`, `calendar`, `activity`, `projects`, `crm`, `inventory`,
`finance`, `settings`. Default client roles (seeded at provisioning): **Owner**
(WRITE all), **Manager** (WRITE ops modules, READ finance), **Member** (READ/WRITE
scoped modules), **Viewer** (READ dashboard/calendar).

Roles are data, not code — admins/clients edit the `resource->Level` map through
the UI. See `ADMIN_PORTAL.md` and `modules/SETTINGS.md`.

---

## 3. User documents

### `control.admin_users`
```json
{
  "_id":"…","email":"…","password_hash":"argon2…",
  "name":"…","role_id":"…","is_active":true,
  "failed_attempts":0,"locked_until":null,
  "created_at":"…","updated_at":"…"
}
```

### `tenant.users`
```json
{
  "_id":"…","email":"…","password_hash":"argon2…",
  "name":"…","role_id":"…",
  "is_blocked":false,                 // admin/client can toggle
  "failed_attempts":0,
  "locked_until":null,                // set when threshold hit
  "must_reset_password":false,        // true after admin reset
  "last_login_at":null,
  "created_at":"…","updated_at":"…"
}
```

---

## 4. Login flow (client)

Payload: `{ "company": "acme", "email": "...", "password": "..." }`
(`company` may be slug or a mapped email domain.)

1. Resolve company by slug → get `db_name`, `status`, `security` policy.
2. If company `status == "blocked"` → `TENANT_BLOCKED` (do not reveal user
   existence).
3. Load user from tenant DB by email.
4. **Block check:** `is_blocked` → `USER_BLOCKED`.
5. **Lockout check:** `locked_until` in the future → `ACCOUNT_LOCKED`
   (with `Retry-After`).
6. **Verify password:**
   - Fail → increment `failed_attempts`; if
     `failed_attempts >= company.security.failed_login_threshold`, set
     `locked_until = now + lockout_minutes` and reset counter to 0. Return
     generic `invalid credentials`.
   - Success → reset `failed_attempts=0`, `locked_until=null`, set
     `last_login_at`, issue access + refresh tokens (tenant bound). If
     `must_reset_password` → return a `password_reset_required` flag so the SPA
     forces a change before proceeding.
7. Write `activity_log` entry `auth.login`.

Admin login is identical minus the tenant resolution and block-company step;
lockout uses the global default threshold.

---

## 5. Failed-login policy (admin-configurable)

- **Global default:** `default_failed_login_threshold`,
  `default_lockout_minutes` from config.
- **Per company:** overridden in `companies.security`. Editable from the admin
  portal (`security_policy` resource, WRITE).
- **Per employee reset:** admin/client with WRITE on `security_policy` can call
  "reset attempts" to zero `failed_attempts` and clear `locked_until` for one
  employee.

Endpoints:
- `PATCH /api/v1/admin/companies/{id}/security` — set threshold/lockout.
- `POST  /api/v1/admin/companies/{id}/employees/{uid}/unlock` — clear lockout.
- `POST  /api/v1/admin/companies/{id}/employees/{uid}/reset-password` — set a
  temp password + `must_reset_password=true`.

---

## 6. Blocking (company & employee)

| Target | Endpoint | Effect |
|---|---|---|
| Company | `PATCH /admin/companies/{id}/status` `{status:"blocked"}` | All logins for the tenant rejected with `TENANT_BLOCKED`; existing tokens rejected at tenant-resolution step. |
| Employee | `PATCH /admin/companies/{id}/employees/{uid}/block` `{blocked:true}` | That user cannot log in (`USER_BLOCKED`); existing tokens rejected in `current_client_user`. |

Both are reversible. Both write admin audit entries. Blocking must invalidate
**existing sessions**, so tenant/user status is re-checked on every request in
`current_client_user` (not only at login). Keep a short-TTL cache of
company/user status to avoid a DB hit per request, invalidated on status change.

Client-side Owners may also block their own employees (client `security_policy`
WRITE) but cannot unblock a company-level block set by platform admins.

---

## 7. Tokens & refresh

- Access token TTL short (`access_token_ttl_min`). Refresh token longer,
  rotating: each refresh issues a new refresh token and invalidates the old
  (store a `refresh_jti` allowlist per user, or a denylist of revoked jtis).
- Logout / block / password reset → revoke the user's refresh jtis.

---

## 8. Acceptance criteria

- N consecutive bad passwords (N = company threshold) locks the account for the
  configured window; the (N+1)th attempt with the correct password still fails
  until the window elapses or an admin unlocks.
- A blocked company's users cannot authenticate and cannot use previously issued
  tokens.
- An admin token cannot call any client endpoint; a client token cannot call any
  admin endpoint.
- A role with `finance = READ` can open finance records but every create/update/
  delete on finance returns `PERMISSION_DENIED`.
- A role with `crm = NONE` never sees CRM in navigation and all CRM endpoints
  return `PERMISSION_DENIED`.
