# TESTING

Tests ship with every feature. A module is not done until its tests are green.

---

## 1. Test pyramid

| Layer | Tool | Scope |
|---|---|---|
| Unit | pytest, pytest-asyncio | services, permission checks, journal balancing, stock math, lockout logic — no DB |
| Integration | pytest + httpx + ephemeral Mongo | full request→DB→response, per-tenant isolation, provisioning |
| Frontend unit | Vitest + Testing Library | components, stores, api client |
| E2E | Playwright | admin onboarding flow, client login+lockout, module CRUD |

Coverage gate: **≥ 85% backend line coverage**, 100% on `core/security`,
`auth/*`, provisioning, and finance posting logic.

---

## 2. Backend test infrastructure

- **Ephemeral MongoDB:** use `mongodb-memory-server` (via a fixture that boots a
  throwaway `mongod`) **or** a disposable local `mongod` on a random port. Never
  test against a shared/dev database.
- Each test run uses a fresh control DB and creates real tenant DBs through the
  actual provisioning engine, then drops them in teardown — this exercises the
  multitenancy path for real.

### Key fixtures (`tests/conftest.py`)
```python
@pytest.fixture async def mongo_uri(): ...        # boots ephemeral mongod, yields uri
@pytest.fixture async def db_manager(mongo_uri): ...
@pytest.fixture async def control_seeded(db_manager): ...   # seeds super admin + admin roles
@pytest.fixture async def admin_client(app): ...            # httpx client w/ admin token
@pytest.fixture async def onboarded_company(admin_client):  # onboards "acme", returns ids
    ...
@pytest.fixture async def client_client(onboarded_company): # httpx client w/ tenant token
    ...
```

---

## 3. Must-have test cases (per area)

### Multitenancy & provisioning
- Onboarding creates a new tenant DB seeded with all enabled module collections +
  indexes and one Owner user.
- Re-running a failed provisioning job is idempotent (no duplicate seeds).
- **Isolation:** a tenant-A token cannot read/write tenant-B data (assert 403 /
  wrong-tenant and that A's queries never see B's docs).
- Teardown drops only the target tenant DB.

### Auth / RBAC
- Lockout after N failed attempts; correct password still fails during lockout;
  admin unlock restores access.
- Company block and employee block reject login **and** invalidate existing
  tokens.
- Admin token rejected on client routes and vice-versa (audience separation).
- Permission matrix: for each client resource × {NONE,VIEW,READ,WRITE}, assert
  GET/POST/PATCH/DELETE allow/deny correctly (table-driven test).

### Admin portal
- Seat limit enforced on employee create (admin-side and client-side).
- Lowering seat limit below active seats is rejected without `force`.
- Password reset sets `must_reset_password` and forces change on next login.
- Dashboard aggregates render from snapshots without hitting external services.

### Modules
- **Projects:** progress recompute on task status change; overdue detection.
- **CRM:** lead conversion atomicity; deal `lost` requires reason; pipeline
  totals.
- **Inventory:** on-hand equals ledger sum; over-issue rejected; transfer
  balances; low-stock list.
- **Finance:** unbalanced journal rejected; invoice→payment status transitions;
  trial balance nets to zero; void produces reversing entry; inventory issue on
  invoice.
- **Dashboard:** quick actions and calendar/activity respect per-module READ/WRITE
  permissions.

---

## 4. Frontend testing
- Unit test the api client, auth store (token handling, forced-reset flow), and
  each module's list/detail/create components.
- E2E (Playwright) golden paths:
  1. Admin logs in → onboards company → sees it active.
  2. Owner first login → forced password reset → lands on dashboard.
  3. Lock an employee by failed logins → admin unlocks → login succeeds.
  4. Create project/task, CRM deal, inventory movement, finance invoice+payment;
     verify dashboard/calendar/activity update.

---

## 5. Test data & determinism
- Freeze time in tests (e.g. `freezegun`) for lockout/expiry/date-based cases.
- Factories/builders for each entity; no reliance on seed order.
- Every test is isolated: fresh control DB + fresh tenant DB, dropped on teardown.

---

## 6. CI gate (custom, no external SaaS required to run)
- `make test` runs: backend unit → backend integration (spins ephemeral mongo) →
  frontend unit → (optional) e2e.
- Fail the build on coverage below gate or any red test.
- Provide a `pytest -m "not e2e"` fast path for local loops.
