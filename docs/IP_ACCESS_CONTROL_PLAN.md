# Plan — IP Access Control (allowlist / denylist + country geo-blocking)

> **This is an implementation plan, not a spec, and nothing here is built yet.**
> A future session must be able to execute it cold. It adds a platform-wide IP
> **allowlist / denylist** with **country-level geo-blocking**, managed from the
> **admin portal**, enforced in ASGI middleware — mirroring the existing rate
> limiter.
>
> - **Non-negotiables (`CLAUDE.md`):** fully custom, no third-party SaaS / paid
>   APIs / external services (open-source libs + self-hosted datasets are fine);
>   three config-driven environments (`local`/`test`/`production`); every admin
>   write is audited to the control audit log; tests ship with the feature.
> - Paths/line numbers are current as of 2026-08-01. If a reference has moved,
>   follow the real code.

---

## 0. What we are building, in one paragraph

A control-plane–stored set of **IP access rules** (`allow`/`deny`, matching a
single **IP**, a **CIDR** range, or a **country** code) that a new
`IPAccessMiddleware` consults on every request and returns **403** for a blocked
client, *before* the request reaches auth or the rate limiter. Rules are managed
by admins in the admin portal (audited), seeded with an operator-owned country
denylist in production, and country matching is resolved against a **self-hosted
geo-IP dataset** (no external API). The design is availability-first: it
**fails open**, ships an env **kill switch**, and an **allowlist always wins** so
an operator cannot geo-block themselves out.

---

## 1. Baseline — what exists to build on (read first)

This feature is deliberately shaped like the existing **rate limiter**; copy its
patterns.

| Thing | Where | Reuse |
|---|---|---|
| ASGI enforcement middleware | `backend/app/core/rate_limit.py` (`RateLimitMiddleware`) | Same structure: `__call__`, per-request client IP, env-chosen behaviour, 4xx short-circuit. |
| Middleware registration | `backend/app/main.py:~92-100` — `add_middleware(...)` **outermost-last** (comment: "Rate limiting fronts everything") | Add `IPAccessMiddleware` **after** `RateLimitMiddleware` so it is *outermost* and runs first. |
| Index bootstrap on startup | `backend/app/main.py` lifespan (`ensure_bucket_indexes` / `ensure_enforcement_indexes`, idempotent, failure-swallowed) | Add `ensure_ip_rule_indexes(db.control)` the same way. |
| Config knobs | `backend/app/core/config.py` (`rate_limit_enabled/_window_sec/_max_requests`, env `ERP_*`) | Add `ip_filter_*` knobs the same way. |
| Error envelope | `backend/app/core/errors.py` (`RATE_LIMITED`, `error_body`, status→code map) | Add an `IP_BLOCKED` code (403). |
| Control-plane DB handle | `app.core.db.get_db_manager().control` | New collection `ip_access_rules` lives here (platform-wide, admin realm), **not** tenant DBs. |
| Admin realm + RBAC | routers under `/api/v1/admin`, dep `require_admin(<resource>, Level)`, principal `AdminPrincipal` (see `app/control_plane/companies/router.py`, `.../admin_users/router.py`) | New admin router; new admin RBAC resource (e.g. `security` or `ip_rules`). |
| Admin audit | `app/core/audit.py:write_admin_audit(actor_id, action, target, details)` | Audit every rule create/update/delete/toggle. |
| Client-IP today | `request.client.host` only (rate_limit.py) — ignores `X-Forwarded-For` | **Harden this** (trusted-proxy XFF) — allow/deny decisions depend on the true client IP. Shared win for the rate limiter. |

**Load-bearing facts to preserve**
1. Middleware wraps **outermost-first**; the *last* `add_middleware` call is the
   *outermost* wrapper and executes first per request.
2. Startup index creation is idempotent and failure-swallowed — every uvicorn
   worker runs it; never let it stop the app from serving.
3. Accounting/enforcement must **never break a request** (rate_limit.py swallows
   accounting errors). Same rule here: a geo-IP/ruleset failure must not 500.
4. Enforcement collections live in the **control** DB, shared across workers.

---

## 2. Target design

### 2-A. Data model — `ip_access_rules` (control DB)
```json
{
  "_id": "…",
  "kind": "allow" | "deny",
  "match_type": "ip" | "cidr" | "country",
  "value": "203.0.113.5" | "203.0.113.0/24" | "KP",   // country = ISO 3166-1 alpha-2, UPPER
  "range_start": 3405803781, "range_end": 3405803781,  // precomputed int bounds for ip/cidr; null for country
  "family": 4 | 6 | null,                              // ip/cidr address family
  "reason": "…",
  "enabled": true,
  "source": "seed" | "manual",
  "created_by": "admin…", "created_at": "…", "updated_at": "…", "is_deleted": false
}
```
- **IP/CIDR** → precompute integer `range_start`/`range_end` (IPv4 → uint32; IPv6
  → 128-bit, store as two uint64 or a fixed-width comparable form) so matching is
  a range check and is indexable.
- **Country** → store just the code; resolve the request IP → country at match
  time via the geo-IP dataset (2-D).
- Indexes: `(kind, match_type, enabled)`, `(match_type, range_start, range_end)`
  for range scans, `value`. All in `ensure_ip_rule_indexes(control_db)`.

### 2-B. Precedence & default posture (the rules engine)
A single pure function `decide(ip: str) -> Decision` (allow / deny + which rule),
evaluated in this fixed order:
1. **Allowlist match wins** (IP → CIDR → country). A matched allow short-circuits
   to ALLOW — the operator's escape hatch; a country block can never override it.
2. **Denylist IP / CIDR match** → DENY.
3. **Denylist country** (geo-IP lookup of the IP → country in a deny rule) → DENY.
4. **Default**: ALLOW (default-allow posture). A later optional **strict mode**
   flips the default to DENY when the allowlist is non-empty — powerful and a
   lockout risk; ship it behind a flag, not in v1.

Keep the ruleset in an **in-process cache** refreshed on a short TTL (or
invalidated on write) so matching is not a Mongo hit per request; geo-IP lookups
are already in-memory.

### 2-C. Enforcement middleware — `IPAccessMiddleware`
- Registered as the **last** `add_middleware` call (outermost / first to run).
- Per request: extract the true client IP (2-E), `decide(ip)`; on DENY return
  **403** with a generic body (`code:"IP_BLOCKED"`, "Access denied.") — **never
  reveal which rule matched** (don't tell an attacker "blocked: country X").
- Honour an env flag `ip_filter_enabled`; when false, pass through (kill switch).
- **Fail open**: if the ruleset or geo-IP DB can't load, ALLOW + log loudly.
- Emit an accounting signal (reuse/extend the rate-limit buckets) so the admin
  dashboard can chart blocks.

### 2-D. Geo-IP (self-hosted — the crux)
- Resolve IP → country from a **local dataset loaded at startup into memory**;
  **never** a per-request external call (keeps it "no paid API").
- Dataset options (pick in P0): **DB-IP Lite Country** (CC-BY, no account, direct
  download) *or* **MaxMind GeoLite2 Country** (free but needs a free license key +
  redistribution terms). Readers (`maxminddb`/`geoip2`) are open-source.
- Treat as a first-class asset: **bundle + version it**, document a **monthly
  refresh** (data goes stale), record the license/attribution. Provide a small
  **fixture DB** (or a mock reader) for tests so the suite never depends on the
  real file. Must cover **IPv4 and IPv6**.

### 2-E. Client-IP extraction (do this properly)
Add trusted-proxy-aware extraction: trust `X-Forwarded-For` **only** from a
configured set of proxy IPs/CIDRs (`ip_trusted_proxies`), else use the socket IP
(`request.client.host`). Put it in a shared helper and adopt it in the rate
limiter too. Getting this wrong means matching the proxy's IP for every user.

### 2-F. Admin portal (API + UI)
- Admin API (control realm, `require_admin("security"|"ip_rules", …)`, audited):
  - `GET /api/v1/admin/ip-rules` — list/filter/paginate.
  - `POST /api/v1/admin/ip-rules` — create (validate IP/CIDR/country code).
  - `PATCH /api/v1/admin/ip-rules/{id}` — enable/disable, edit reason.
  - `DELETE /api/v1/admin/ip-rules/{id}` — soft delete.
  - `POST /api/v1/admin/ip-rules/test` (`{ip}`) — "would this IP be allowed, and
    by which rule?" **Build early — the primary lockout-preventer.**
- UI: two lists (allow / deny), add-entry form (type selector + value + reason +
  enable toggle), the IP checker, and a **warning if a new rule would block the
  admin's current IP**.

### 2-G. Seeding (config-driven, environment-aware)
- Seed the country denylist from a **config value / seed file**, `source:"seed"`,
  enabled — **production only by default** (do NOT geo-block local/test).
- ⚠️ **Which countries is a compliance/legal decision the operator owns**, not a
  technical one; base it on sanctions/embargo lists (e.g. OFAC), not an arbitrary
  pick. Ship the *mechanism* + an operator-provided list; do not bake opinionated
  country choices into code.

### 2-H. Anti-lockout / break-glass (do not skip)
- **Allowlist-wins** precedence (2-B) + a bootstrap allowlist of known admin/office
  IPs seeded for the admin's environment.
- **Env kill switch** `ERP_IP_FILTER_ENABLED=false` an operator can flip **without
  the UI** (in case the UI itself is blocked).
- Fail-open on load errors; "this would block you" warning on writes.
- **D3 = client + admin (locked):** the filter guards the admin portal too, so the
  break-glass items above are **mandatory** for v1 — the env kill switch and a
  bootstrap admin/office allowlist must land with the middleware (P4/P6), not
  after. A single bad rule could otherwise lock every admin out.

---

## 3. Open decisions (P0) — fill these before P1

**All locked 2026-08-01.**

| # | Decision | Chosen |
|---|---|---|
| D1 | Default posture | **default-allow + denylist** (strict allowlist-only mode deferred, behind a flag) |
| D2 | Precedence | **allowlist ALWAYS wins**, then deny IP/CIDR, then deny country, else allow |
| D3 | Realms enforced | **client + admin** — the filter guards the admin portal too ⇒ break-glass (kill switch + bootstrap admin allowlist) is **mandatory**, not optional |
| D4 | Geo-IP dataset | **DB-IP Lite Country** (CC-BY, no account, direct download; monthly refresh; attribution required) |
| D5 | Fail behaviour on load error | **fail-open** + loud log (strict mode, if ever added, may fail-closed) |
| D6 | Country list | **defer to compliance** — build the mechanism + a config-driven, **production-only** seed that ships **empty** until compliance supplies ISO codes (sanctions-based). No countries baked into code |
| D7 | Client-IP behind proxy | **trusted-proxy-aware** XFF helper (trust `X-Forwarded-For` only from configured proxy IPs), shared with the rate limiter |

---

## 4. Phased work (commit at each boundary; tests ship with each phase)

- **P0 — Decisions.** Lock D1–D7 (this doc §3 + §7). No code.
- **P1 — Model + storage + client-IP.** `ip_access_rules` model + control-plane
  repo + `ensure_ip_rule_indexes`; `config.py` `ip_filter_*` + `ip_trusted_proxies`
  knobs; the trusted-proxy client-IP helper (adopt in rate limiter).
  *Prove:* indexes build on startup; helper unit tests pass (v4/v6, proxy/no-proxy).
- **P2 — Matching engine.** Pure `decide(ip, ruleset, geo)` with precedence
  (D1/D2); in-memory ruleset cache with invalidation. *Prove:* unit tests for
  ip/cidr/country matching + precedence + disabled-rule inert (geo mocked).
- **P3 — Geo-IP.** Bundle the chosen dataset (D4) + loader + monthly-refresh note
  + fixture DB for tests. *Prove:* known IP → expected country from the fixture.
- **P4 — Middleware.** `IPAccessMiddleware` outermost; 403 `IP_BLOCKED`; kill
  switch; fail-open; blocks accounted. *Prove:* denied IP → 403, allowlisted IP
  passes, allow>deny, disabled filter passes through.
- **P5 — Admin API.** CRUD + `test` endpoint, `require_admin`, audited. *Prove:*
  CRUD round-trip + audit rows + test endpoint verdicts + admin RBAC gate.
- **P6 — Seed.** Config-driven prod country denylist (D6) + bootstrap admin
  allowlist; `source:"seed"`. *Prove:* fresh prod-config seed yields the rules;
  local/test seed adds none.
- **P7 — Admin UI.** Two lists, add form, IP checker, "would block you" warning.
  *Prove:* component tests for rendering + the checker + the warning.
- **P8 — Harden & document.** Full suites green (`ruff`/`mypy`/`tsc`); a
  **break-glass runbook** in `docs/`; update `docs/ARCHITECTURE.md` §6 (security
  middleware) and `docs/ADMIN_PORTAL.md` (the new panel).

---

## 5. Testing (non-negotiable rule 6)
- **Unit:** IP/CIDR parse + integer range match (v4 **and** v6); precedence
  (allow>deny>country>default); disabled rule inert; country resolution (mock
  reader); trusted-proxy client-IP extraction.
- **Integration:** middleware 403 on denied IP; allowlist beats denylist; kill
  switch passes through; admin CRUD + audit; `test` endpoint verdicts; admin RBAC
  denies non-privileged admins; fail-open when the geo DB is absent.
- **Frontend:** the two lists, add form, and IP checker; the lockout warning.
- Geo-IP tests use a **fixture dataset**, never the shipped file.

---

## 6. Risks & edge cases
- **Geo-IP dataset** — licensing (attribution/redistribution), **staleness**
  (schedule refreshes), and IPv6 coverage. Biggest external dependency.
- **Client IP behind a proxy** — decisions are only as correct as the extracted
  IP; get the trusted-proxy handling right (P1) before enforcing (P4).
- **Self-lockout** — the IP tester, kill switch, allowlist-wins, and fail-open
  exist for this; land them early, not late.
- **App-layer only** — this rejects at HTTP (after TCP/TLS). For real floods, an
  edge WAF/nginx denylist is still the first line; this is the dynamic,
  admin-editable business layer. Optional future: export rules to the edge.
- **Over-blocking a CIDR** — validate/normalise CIDRs; warn on very large ranges.

---

# 7. SESSION HANDOVER — start here

## 7.1 Repo state
- Branch: **create `ip-access-control`** off `main` (main is at the merged PM v2
  work). Nothing for this feature is built yet.
- The rate limiter (`backend/app/core/rate_limit.py`) is the reference
  implementation — read it before P1.

## 7.2 Decisions locked (P0) — **DONE 2026-08-01**

| # | Decision | Chosen | Status |
|---|---|---|---|
| D1 | Default posture | default-allow + denylist (strict mode deferred) | ✅ |
| D2 | Precedence | allowlist always wins → deny IP/CIDR → deny country → allow | ✅ |
| D3 | Realms enforced | **client + admin** (⇒ kill switch + bootstrap admin allowlist mandatory) | ✅ |
| D4 | Geo-IP dataset | **DB-IP Lite Country** (CC-BY, no account) | ✅ |
| D5 | Fail behaviour | fail-open + loud log | ✅ |
| D6 | Country list | defer to compliance; config-driven prod-only seed, ships empty | ✅ |
| D7 | Client-IP behind proxy | trusted-proxy XFF helper (shared with rate limiter) | ✅ |

## 7.3 Done
- **P0 — decisions locked** (§7.2).
- **P1 — model + storage + client-IP (DONE 2026-08-01, on branch `ip-access-control`, uncommitted).**
  - Config knobs `ip_filter_enabled` (kill switch) + `ip_trusted_proxies` in
    `backend/app/core/config.py`; `.env.example` documents `ERP_IP_FILTER_ENABLED`
    / `ERP_IP_TRUSTED_PROXIES`.
  - Trusted-proxy client-IP helper `backend/app/core/client_ip.py`
    (`resolve_client_ip` pure + `client_ip(request, ...)`); adopted in
    `rate_limit.py` (rate limiter now keys on the real client IP behind trusted
    proxies).
  - `ip_access_rules` control-plane package: `app/control_plane/ip_access/models.py`
    (`IpRuleCreate`/`IpRulePatch` + `normalize_value`, validates+canonicalizes
    ip/cidr/country, computes `family`) and `.../repository.py` (`COLLECTION`,
    `ensure_ip_rule_indexes`, `insert`/`list_rules`/`enabled_rules`/`get`/
    `find_duplicate`/`update`/`soft_delete`). **Design note:** rules are matched
    **in-process** from a small set, so we store canonical `value` + `family`
    (no 128-bit IPv6 Mongo bounds) and build `ipaddress` networks at match time.
  - Index bootstrapped in the `main.py` lifespan next to the rate-limit indexes.
  - Tests green: `tests/unit/test_client_ip.py`, `tests/unit/test_ip_access_models.py`,
    `tests/integration/test_ip_access_repo.py` (+ rate-limit units still pass).
    ruff + mypy clean.

- **P2 — matching engine (DONE 2026-08-01, on branch `ip-access-control`, uncommitted).**
  - `app/control_plane/ip_access/matcher.py`: pure `decide(ip, ruleset, country=None)`
    + `compile_rules(rules) -> RuleSet` with the D2 precedence (allowlist wins →
    deny ip/cidr → deny country → default allow). `Decision` carries the matched
    rule (id/kind/match_type/value) for the P5 test-IP endpoint. Geo is NOT done
    here — the caller passes the resolved `country` (or None), so the engine is
    dataset-free and pure. Defensively skips deleted/disabled/bad-value rows;
    v4/v6-safe; unparseable IP → default allow (`reason="unresolved"`).
  - `app/control_plane/ip_access/cache.py`: `RuleCache(loader, ttl_sec=10)` —
    compiles once, serves from memory, `invalidate()` on writes (P5); TTL is the
    cross-worker propagation backstop.
  - Tests: `tests/unit/test_ip_access_matcher.py` (precedence, v6, disabled/
    deleted inert, bad values, cache TTL + invalidate). ruff + mypy clean.

- **P3 — geo-IP (DONE 2026-08-01, on branch `ip-access-control`, uncommitted).**
  - `app/control_plane/ip_access/geoip.py`: `GeoIpResolver.country(ip) -> str|None`
    over an injected `.mmdb` reader; `open_mmdb_reader(path)` lazily imports the
    optional `maxminddb` lib; `build_geoip_resolver(db_path)` returns a working
    resolver when the dataset is present, else a **fail-open no-op** (returns
    None → country rules inert). Handles `country` + `registered_country`
    iso_code, upper-cases, swallows lookup errors.
  - Config `ip_geoip_db_path` (`ERP_IP_GEOIP_DB_PATH`, unset by default);
    `maxminddb` added as an **optional** dep (`pyproject` extra `geoip`), so the
    base app runs without it. **No external API call, ever — fully self-hosted.**
  - Ops: provision a GeoLite2-Country / DB-IP-Lite `.mmdb`, set the path, refresh
    monthly (replace file + `reload()`/restart); record the dataset license.
  - Tests: `tests/unit/test_ip_geoip.py` (iso extraction + fallback, fail-open on
    missing lib/file/errors, and the geo→matcher bridge). ruff + mypy clean.

## 7.4 Remaining
- **P4 (next) — enforcement middleware.** `IPAccessMiddleware` mounted OUTSIDE the
  rate limiter (blocked IPs rejected before consuming a rate-limit slot): resolve
  client IP (P1 helper) → `RuleCache.get()` (P2) → resolve country (P3) →
  `decide(...)`; on deny return **403** generic `IP_BLOCKED` (never reveal which
  rule). Honour the `ip_filter_enabled` kill switch; fail-open on any internal
  error; feed the same accounting signal as the rate limiter. Decide realm scope
  (client vs admin — D-realm). *Prove:* integration tests — denied IP → 403,
  allowlist beats deny, kill switch bypasses, disabled/absent rules allow.
- Then P5 → P8 per §4, in order.
