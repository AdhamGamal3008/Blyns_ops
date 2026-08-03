# Runbook — IP access control (break-glass & operations)

Operational guide for the platform IP allow/deny + country geo-blocking filter
(design: `docs/IP_ACCESS_CONTROL_PLAN.md`; middleware:
`backend/app/control_plane/ip_access/`). The filter guards **both** the client and
admin realms, so a bad rule can lock admins out too — this runbook is how you get
back in.

---

## 0. TL;DR — "we're locked out"

**Fastest recovery, no UI needed:** set the kill switch and restart the app.

```bash
ERP_IP_FILTER_ENABLED=false   # then restart every app process/worker
```

All IP filtering is bypassed immediately. Then fix the offending rule (§2) and turn
the filter back on. Nothing is lost — rules stay in the DB while the switch is off.

---

## 1. How the filter behaves (why lockout is recoverable)

- **Allowlist always wins.** An `allow` rule for an IP/CIDR/country beats *every*
  `deny` (including a country block). Seed your admin/office IPs and you cannot be
  geo/deny-blocked. Precedence: allow → deny ip/cidr → deny country → default-allow.
- **Default-allow.** With no matching rule, traffic is allowed. The filter only ever
  *subtracts* access via explicit deny rules.
- **Fail-open.** If the ruleset can't load or the geo lookup errors, the request is
  **allowed** (and logged loudly). The filter can never take the platform down.
- **Kill switch.** `ERP_IP_FILTER_ENABLED=false` bypasses everything, flippable from
  the environment without the UI (in case the UI itself is blocked).
- **Opaque denial.** A blocked client gets a generic `403 IP_BLOCKED` / "Access
  denied." — the matched rule is never revealed to the caller.

---

## 2. Break-glass procedures (in escalation order)

### 2a. Preferred — remove the bad rule in the UI
If *some* admin can still reach `/admin/ip-rules` (e.g. from an allowlisted IP):
disable (toggle) or delete the offending deny rule. Writes take effect on that
worker immediately (cache invalidation) and on others within
`ERP_IP_RULE_CACHE_TTL_SEC` (default 10s).

### 2b. Env kill switch (no UI)
Set `ERP_IP_FILTER_ENABLED=false` and restart all app processes. Filtering is fully
bypassed. Use this when *no* admin can get in. Re-enable after fixing the rule.

### 2c. Edit the control DB directly (last resort)
The rules live in the **control** database, collection `ip_access_rules`. Disable or
soft-delete the offending row:

```js
// mongosh, against the control DB
db.ip_access_rules.updateMany({ kind: "deny" }, { $set: { enabled: false } })  // nuclear: disable all denies
// or target one rule:
db.ip_access_rules.updateOne({ _id: ObjectId("...") }, { $set: { is_deleted: true } })
```

Changes propagate within the cache TTL (or restart to force an immediate reload).

### 2d. Prevention — bootstrap allowlist
Seed known admin/office IPs so 2a–2c are never needed. In **production**:

```bash
ERP_IP_SEED_ALLOW_IPS='["203.0.113.5","198.51.100.0/24"]'
```

Then run `python scripts/seed_control_plane.py` (idempotent). These become
`source:"seed"` allow rules; allowlist-wins guarantees those addresses are never
blocked. See §4.

---

## 3. Diagnostic tools (use BEFORE writing a rule)

- **IP tester** — `POST /api/v1/admin/ip-rules/test` `{ "ip": "203.0.113.5" }` →
  `{ allowed, reason, matched_rule, country }`. Answers "would this IP be allowed,
  and by which rule?" against the *current* rules (compiled fresh, not cached).
- **Whoami** — `GET /api/v1/admin/ip-rules/whoami` → the IP + country the server
  sees for you. The add-rule form uses it to warn "this would block your current IP"
  before you save a deny that matches you.
- Both require the `ip_rules` admin resource (READ).

---

## 4. Configuration reference (all `ERP_*`, `backend/app/core/config.py`)

| Var | Default | Notes |
|---|---|---|
| `ERP_IP_FILTER_ENABLED` | `true` | Kill switch. `false` bypasses all filtering. |
| `ERP_IP_TRUSTED_PROXIES` | `[]` | JSON list of proxy IPs/CIDRs whose `X-Forwarded-For` is trusted for the real client IP. **Behind a load balancer, set this** or every client looks like the proxy. Empty = trust none (use the socket peer). |
| `ERP_IP_RULE_CACHE_TTL_SEC` | `10` | In-process ruleset cache TTL = cross-worker rule-propagation delay. |
| `ERP_IP_GEOIP_DB_PATH` | unset | Path to a self-hosted MaxMind-format `.mmdb` (GeoLite2 Country or DB-IP Lite). Unset → country rules are inert. Never an external API. |
| `ERP_IP_SEED_DENY_COUNTRIES` | `[]` | **Production-only** seed. ISO 3166-1 alpha-2 codes. Ships empty — the list is a compliance/sanctions decision, not baked in. |
| `ERP_IP_SEED_ALLOW_IPS` | `[]` | **Production-only** seed. Bootstrap admin/office IPs/CIDRs (see §2d). |

### Geo-IP dataset (ops)
Country rules need a local `.mmdb`. Provision it, set `ERP_IP_GEOIP_DB_PATH`, and
**refresh monthly** (data goes stale): replace the file and restart (or `reload()`).
Record the dataset's license/attribution (DB-IP Lite is CC-BY). Without it, country
rules simply do nothing — IP/CIDR rules are unaffected.

### Country denylist (compliance)
The *mechanism* ships; the *list* is operator-owned. Base it on sanctions/embargo
lists (e.g. OFAC), not an arbitrary pick. Seeds only in production, ships empty.

---

## 5. Accounting & observability
Blocks are counted into the same `rate_limit_buckets` the dashboard reads
(`ip_blocked`, surfaced as `ip_blocked_last_min` on `GET /admin/dashboard`). A
fail-open event is logged at WARNING/ERROR by `app.control_plane.ip_access.middleware`
("filter error; failing open").

---

## 6. This is app-layer only
The filter rejects at HTTP, after TCP/TLS. For volumetric floods, an edge
WAF/nginx denylist is still the first line of defence; this is the dynamic,
admin-editable business layer on top.
