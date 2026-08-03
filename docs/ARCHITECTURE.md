# ARCHITECTURE

Foundational engineering spec. Everything else assumes these primitives exist.

---

## 1. Configuration (`app/core/config.py`)

Use `pydantic-settings`. **No literal connection strings anywhere else.**

```python
class Settings(BaseSettings):
    env: Literal["local", "test", "production"] = "local"

    # Mongo
    mongo_uri: str                       # e.g. mongodb://localhost:27017
    control_db_name: str = "erp_control"
    tenant_db_prefix: str = "erp_tenant_"

    # Auth
    jwt_secret: str
    jwt_algorithm: str = "HS256"
    access_token_ttl_min: int = 30
    refresh_token_ttl_days: int = 14
    admin_token_audience: str = "erp-admin"
    client_token_audience: str = "erp-client"

    # Security defaults (overridable per company)
    default_failed_login_threshold: int = 5
    default_lockout_minutes: int = 15

    # Rate limiting
    rate_limit_window_sec: int = 60
    rate_limit_max_requests: int = 120

    model_config = SettingsConfigDict(env_file=".env", env_prefix="ERP_")

settings = Settings()  # imported everywhere
```

Config is loaded once at startup. `env` drives behavior differences (see
`ENVIRONMENTS.md`).

---

## 2. Database connection manager (`app/core/db.py`)

This is the heart of multitenancy. One Motor client, many logical databases.

```python
class DBManager:
    def __init__(self, uri: str):
        self._client = AsyncIOMotorClient(uri, uuidRepresentation="standard")
        self._tenant_cache: dict[str, AsyncIOMotorDatabase] = {}

    @property
    def control(self) -> AsyncIOMotorDatabase:
        return self._client[settings.control_db_name]

    def tenant(self, db_name: str) -> AsyncIOMotorDatabase:
        # db_name comes from the company registry, already prefixed
        if db_name not in self._tenant_cache:
            self._tenant_cache[db_name] = self._client[db_name]
        return self._tenant_cache[db_name]

    async def ping(self) -> bool:
        await self._client.admin.command("ping")
        return True

    def raw_client(self) -> AsyncIOMotorClient:
        return self._client        # used by metrics for serverStatus/dbStats
```

- **One connection pool** (`AsyncIOMotorClient`) is shared. Do **not** open a new
  client per tenant — that exhausts sockets. Selecting a database is cheap.
- The tenant's `db_name` is never guessed. It is always read from the company
  registry document, which the tenant-resolution layer supplies.

---

## 3. Security primitives (`app/core/security.py`)

```python
# Passwords: argon2id (argon2-cffi). Never bcrypt-only, never plaintext.
def hash_password(raw: str) -> str: ...
def verify_password(raw: str, stored_hash: str) -> bool: ...

# JWT
def create_access_token(sub, audience, extra_claims) -> str: ...
def decode_token(token, expected_audience) -> TokenPayload: ...
```

Token payload (both realms share the shape; `aud` separates them):

```json
{
  "sub": "user_object_id",
  "aud": "erp-admin | erp-client",
  "tenant": "erp_tenant_acme  (client only, null for admin)",
  "role_id": "role_object_id",
  "type": "access | refresh",
  "iat": 0, "exp": 0
}
```

---

## 4. Error envelope & exceptions (`app/core/errors.py`)

Define a `DomainError(code, message, http_status, details)` base and register a
FastAPI exception handler that renders:

```json
{ "error": { "code": "...", "message": "...", "details": {} } }
```

Reserved codes used across specs: `TENANT_BLOCKED`, `USER_BLOCKED`,
`ACCOUNT_LOCKED`, `SEAT_LIMIT_REACHED`, `PERMISSION_DENIED`,
`TENANT_NOT_FOUND`, `RATE_LIMITED`, `PROVISIONING_FAILED`, `VALIDATION_ERROR`.

---

## 5. Audit & activity (`app/core/audit.py`)

Two writers, same signature shape:

```python
async def write_admin_audit(actor_id, action, target, details): ...   # -> control.admin_audit_log
async def write_activity(tenant_db, actor_id, action, entity, details): ...  # -> tenant.activity_log
```

Call sites: every state-changing admin endpoint calls `write_admin_audit`; every
state-changing client endpoint calls `write_activity`. The client Dashboard's
activity panel and calendar read from `activity_log`.

Activity document:
```json
{
  "actor_id": "…", "actor_name": "…",
  "action": "project.created",
  "entity": { "type": "project", "id": "…", "label": "Website Revamp" },
  "module": "projects",
  "occurred_at": "ISO-8601",
  "details": {}
}
```

---

## 6. Security middleware

Custom, no external service. Two ASGI middlewares front every request. Middleware
wraps outermost-first — the **last** `add_middleware` call runs first — so the order
is: **IP access filter → rate limiter →** CORS → access log → app.

### 6.1 Rate limiting (`app/core/rate_limit.py`)

Two tiers:

- **Global per-IP** middleware: fixed window (`rate_limit_window_sec`,
  `rate_limit_max_requests`). Backed by an in-process dict for `local`, and a
  MongoDB `rate_limit_buckets` collection (TTL-indexed) for `production` so it
  survives multiple workers.
- **Per-tenant** counters: increment a bucket keyed by `(tenant, minute)`; these
  feed the admin dashboard "rate limits / activity" panel.

Return `429` with `RATE_LIMITED` when exceeded. Emit `Retry-After`.

### 6.2 IP access filter (`app/control_plane/ip_access/`)

Platform-wide allow/deny + country geo-blocking, mounted **ahead of** the rate
limiter so a blocked IP is rejected before it consumes a rate-limit slot. Per
request: resolve the true client IP (trusted-proxy `X-Forwarded-For`,
`app/core/client_ip.py`) → consult the in-process ruleset cache over the
control-plane `ip_access_rules` collection → resolve the country from a self-hosted
`.mmdb` (no external API) → `decide()`. Precedence: **allowlist always wins** → deny
ip/cidr → deny country → default-allow. On deny: a generic `403 IP_BLOCKED` that
never names the matched rule.

Guards **both realms** (client + admin), so break-glass is mandatory: honours the
`ERP_IP_FILTER_ENABLED` kill switch, **fails open** on any internal error, and a
bootstrap admin allowlist can be seeded. Blocks are accounted into
`rate_limit_buckets` (`ip_blocked`). Admin CRUD + the IP tester / `whoami` live
under `/admin/ip-rules` (RBAC `ip_rules`). Design + operations:
`docs/IP_ACCESS_CONTROL_PLAN.md`, `docs/IP_ACCESS_RUNBOOK.md`.

---

## 7. FastAPI dependencies (`app/tenant/deps.py`)

Reusable DI functions every route uses:

- `get_control_db()` → control database.
- `current_admin()` → decodes admin token, loads admin user + role, enforces
  admin is active.
- `current_client_user()` → decodes client token, resolves tenant, loads
  employee, enforces: company not blocked, user not blocked, not locked out.
- `get_tenant_db(user = Depends(current_client_user))` → tenant database handle.
- `require(permission_level, resource)` → RBAC guard (see `AUTH_RBAC.md`).

Ordering matters: tenant/block checks happen **before** any business logic runs.

---

## 8. Module package shape (every client module identical)

```
modules/<name>/
├── __init__.py
├── router.py       # FastAPI APIRouter, mounted at /api/v1/<name>
├── models.py       # Pydantic request/response + DB doc schemas
├── service.py      # business logic, talks to tenant db only
├── repository.py   # Mongo access, no business rules
├── permissions.py  # resource → required level mapping
└── seed.py         # collections + indexes this module needs at tenant creation
```

`seed.py` is critical: the provisioning engine imports each module's `seed()` to
build indexes and default documents when a tenant DB is created (see
`MULTITENANCY.md`).
