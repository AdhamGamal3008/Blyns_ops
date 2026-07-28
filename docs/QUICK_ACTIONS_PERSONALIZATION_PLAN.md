# Plan — Personalized Quick Actions (Phase 0 + Phase 1)

> **This is an implementation plan, not a spec, and nothing here is built yet.**
> A future session should be able to execute it cold. Decisions are already locked
> (see below); if a spec conflicts, follow the repo's real code (paths are current
> as of 2026-07-27). No third-party AI/ML — ranking is in-house, explainable
> scoring, per the project's non-negotiables.

## Locked decisions (do not re-litigate)
- **Scope now:** Phase 0 (expand the catalog) + Phase 1 (rank by **role × own recent
  behavior**, server-side, top-5 inline + overflow, **silent** — no "why" hint).
- **Deferred until we see Phase 1 live:** user pinning/hide (Phase 2) and the
  contextual "next-step" suggestion strip (Phase 3). Not in this plan.
- **Ranking is a pure, deterministic function** of (the user's recent `activity_log`
  events) + (their role permissions) + (named constants). Same inputs → same order.
- **Permissions stay the authoritative gate.** We only reorder/select among actions
  the user is *already* allowed to do; we never surface a forbidden action.
- **Cold start = today's behavior:** a user with no recent activity sees the current
  curated order.

---

## Baseline (what exists today)

| Piece | Where | Current behavior |
|---|---|---|
| Action catalog | `backend/app/modules/dashboard/permissions.py` → `QUICK_ACTIONS` | 5 static entries `{key,label,module,required_level,target_route}`, all `required_level = WRITE` |
| Selection/filter | `backend/app/modules/dashboard/service.py` → `quick_actions(principal)` (**sync**) | keeps actions whose module is enabled **and** `level_for(module) ≥ required_level`; returns them in **declaration order** |
| Endpoint | `backend/app/modules/dashboard/router.py:25` `GET /dashboard/quick-actions` | `envelope(service.quick_actions(principal))` (no `await` today) |
| Frontend | `frontend/src/client/dashboard/QuickActions.tsx` | fetches the list, renders **all** as buttons in a `Row`; **already treats index 0 as primary** ("server returns priority order") |
| Behavior data | tenant `activity_log` (written by `app/core/audit.py:write_activity`) | every write logs `{actor_id, actor_name, action, module, entity, details, occurred_at}`. Indexed on `occurred_at desc`, `module`, `actor_id` (single-field) in `dashboard/seed.py` |

**Action string shape:** `{module}.{entity}.{verb}` — e.g. `crm.lead.created`, `finance.invoice.sent`, `settings.employee.created`, `project.created`, `stage.approved`. **Some are dynamic** (`inventory.{type}` → `inventory.issue`/`inventory.adjustment`/`inventory.receipt`, `inventory.transfer`). Because exact action names don't map 1:1 to quick-action keys, the scorer uses **two signals** (below), and leans on the reliable `module` field for engagement.

---

## Phase 0 — Expand the catalog (prerequisite, small)

There's little to personalize with only 5 actions, so grow `QUICK_ACTIONS`. Add
high-value, WRITE-gated shortcuts. **Only add an action whose `target_route` already
resolves in the SPA** (an existing deep-link or a real tab route) — otherwise add the
tiny deep-link first or point it at the module tab. Candidates:

| key | label | module | target_route | route status to confirm |
|---|---|---|---|---|
| `crm.deal.new` | New Deal | crm | `/app/crm` (pipeline) or a deal deep-link | pipeline tab exists; deep-link may need adding |
| `crm.contact.new` | New Contact | crm | `/app/crm/contacts` | tab exists |
| `finance.bill.new` | New Bill | finance | `/app/finance/bills` | tab exists |
| `finance.payment.new` | Record Payment | finance | `/app/finance` (invoices) | payment is a per-invoice modal — may just land on the tab |
| `inventory.product.new` | New Product | inventory | `/app/inventory/products` | tab exists |

Keep each entry's shape identical to today's. **Whatever the final set, keep it ≤ ~10** so the overflow stays short. Update the frontend/backend tests that assert the action count.

---

## Phase 1 — Role × behavior ranking (the core)

### 1. Data model — no new collection
Reads `activity_log` only. **Add one compound index** so the per-user query is cheap:
`activity_log [(actor_id, 1), (occurred_at, -1)]` in `dashboard/seed.py` (idempotent;
the existing single-field indexes can stay or be dropped later).

### 2. The scoring function (explainable)
For each **candidate** quick action `qa` (candidates = the current permission+enabled
gate, unchanged), compute:

```
score(qa) =
      role_weight(level_for(qa.module))                     # role affinity
    + W_EXACT  * Σ over events e where e.action ∈ exact(qa):  decay(age(e))
    + W_MODULE * Σ over events e where e.module == qa.module: decay(age(e))
    + TIE_EPSILON * (len(catalog) - declaration_index(qa))   # stable curated tiebreak

decay(age_days) = 0.5 ** (age_days / HALF_LIFE_DAYS)          # recency half-life
events         = this user's activity_log in the last WINDOW_DAYS (capped fetch)
```

Sort candidates by `score` **descending**; return the **full ordered list** (the
frontend decides how many to show inline). The `module`-engagement term is the robust
signal (it catches `stage.*` boosting "New Project", `inventory.{type}` boosting
"Adjust Stock", etc.); the exact-action term sharpens it toward the specific shortcut.

**Proposed constants** (env-overridable; see §5):
```
WINDOW_DAYS    = 30      HALF_LIFE_DAYS = 7
W_EXACT        = 3.0     W_MODULE       = 1.0
ROLE_W_WRITE   = 2.0     ROLE_W_READ    = 0.5   # READ is future-proofing; all actions are WRITE today
TIE_EPSILON    = 0.001   EVENT_FETCH_CAP = 500  # newest N events, bounds cost
INLINE_LIMIT   = 5       # shown inline; the rest go to the overflow menu (frontend)
```

**Cold start:** no events in window → both behavior sums are 0 → order = `role_weight +
TIE_EPSILON·bias` = **today's curated order**, filtered by permission. Guarantees the
"new user sees current behavior" decision.

### 3. `exact(qa)` — the action map (keep it beside the catalog)
A dict from quick-action key → the activity `action` strings (or prefixes) that count
as "did exactly this". Maintain it whenever the catalog changes.

| quick action | exact actions |
|---|---|
| `project.new` | `project.created` |
| `crm.lead.new` | `crm.lead.created` |
| `crm.deal.new` | `crm.deal.created` |
| `crm.contact.new` | `crm.contact.created` |
| `inventory.adjust` | `inventory.receipt`, `inventory.issue`, `inventory.adjustment`, `inventory.transfer` |
| `inventory.product.new` | `inventory.product.created` |
| `finance.invoice.new` | `finance.invoice.created`, `finance.invoice.sent` |
| `finance.bill.new` | `finance.bill.created`, `finance.bill.sent` |
| `finance.payment.new` | `finance.payment.recorded` |
| `employee.invite` | `settings.employee.created` |

> Confirm each string by grepping `write_activity(`/`_log(` in the owning module's
> `service.py` before relying on it (some are dynamic f-strings). The **module** term
> does not depend on this map — it reads the stored `module` field — so a missing exact
> mapping degrades gracefully to module-engagement ranking.

### 4. Server changes
- **`dashboard/service.py`**: make `quick_actions` **async**; keep the existing
  candidate filter; fetch the user's recent events once
  (`activity_log.find({actor_id, occurred_at ≥ now-WINDOW_DAYS}, {action:1, module:1, occurred_at:1}).sort(occurred_at,-1).limit(EVENT_FETCH_CAP)`);
  score in memory; return sorted. Pure helper `_score(...)` for unit-testing.
- **`dashboard/router.py:25`**: `await service.quick_actions(principal)`.
- **`dashboard/permissions.py`**: the expanded `QUICK_ACTIONS`, the `EXACT_ACTIONS`
  map, and the scoring constants (or put constants in config — §5).
- **`dashboard/seed.py`**: the compound index.

### 5. Config (three environments, config-driven)
Put the constants in `core/config.py` as settings with the proposed defaults, overridable
by env (`ERP_QA_WINDOW_DAYS`, `ERP_QA_HALF_LIFE_DAYS`, …). Nothing hard-coded per the
ENVIRONMENTS.md rule. Defaults above are fine for local/test/prod.

### 6. Frontend changes (`QuickActions.tsx`)
Ordering is already respected. Add only: render the **first `INLINE_LIMIT` (5)** inline
(first = primary, as now), and put any remainder behind a **"More ▾" overflow**
(`DropdownMenu` from the UI kit) so every permitted action stays reachable. **Silent** —
no "recent/suggested" labelling in this phase.

---

## Tests (ship with the feature)

**Backend** (`tests/integration/test_dashboard.py` or new `test_quick_actions.py`):
- *Behavior ranks*: a user who repeatedly creates invoices (drive via the real API so
  `finance.invoice.*` events accrue) gets `finance.invoice.new` ranked first.
- *Exact beats module-only*: exact-action activity outranks mere module presence.
- *Recency*: events older than `WINDOW_DAYS` don't outrank a recent one (freeze time or
  insert dated events).
- *Permission gate intact*: a role without finance WRITE never sees a finance action,
  whatever the activity.
- *Enabled-modules gate intact*.
- *Cold start*: a brand-new user gets the curated default order, all permitted.
- *Determinism*: identical inputs → identical order.
- Unit-test the pure `_score(...)` directly for the formula.

**Frontend** (`QuickActions.test.tsx`):
- Renders in server order; index 0 is primary.
- More than 5 → first 5 inline, rest under the overflow menu; clicking any navigates to
  its `target_route`.

---

## Acceptance criteria (definition of done)
- `quick_actions` is async, does **one** capped, indexed `activity_log` query, and keeps
  the permission + enabled-module filter as the hard gate.
- Ranking is deterministic and explainable (pure function of events + role + constants),
  no external service.
- Cold start returns today's curated order.
- Constants are config-driven (env-overridable), valid across local/test/prod.
- Frontend shows 5 inline + overflow, silent, honoring server order.
- Full backend suite + frontend suite green; ruff + mypy + tsc clean.

---

## Edge cases & risks
- **Map drift:** adding a quick action without updating `EXACT_ACTIONS` → it still ranks
  via module-engagement (graceful), just less sharply. Keep the map next to the catalog.
- **Dynamic action names** (`inventory.{type}`): covered by the module term; the exact
  set lists the known type strings.
- **Nothing hidden:** the primary highlight is only the top action; the overflow keeps
  every permitted action reachable, so a heavy user of one action never strands others.
- **Cost:** one compound-indexed query, projected + capped at `EVENT_FETCH_CAP`; scored
  in memory. Negligible.
- **Privacy:** ranks on the user's *own*, tenant-scoped activity only. No cross-user data.
- **Module tagging:** confirm project `stage.*` events carry `module:"projects"` (they
  should — the activity panel filters projects by module) so they boost "New Project".

---

## Suggested order of work
1. Phase 0: expand `QUICK_ACTIONS` (routes confirmed) + fix count assertions in tests.
2. Config constants in `core/config.py`.
3. `dashboard/seed.py` compound index.
4. `dashboard/service.py`: async `quick_actions` + pure `_score`; `router.py` `await`.
5. Backend tests → green + ruff/mypy.
6. Frontend overflow in `QuickActions.tsx` + tests → green + tsc.
7. Live-verify (drive some activity as a user, confirm the order shifts; confirm a
   fresh user sees the default order).
8. Commit; **confirm before pushing** (repo rule).

## Micro-decisions still open (safe defaults chosen; change if you prefer)
- Final Phase-0 action set + their routes (some need a deep-link vs land-on-tab).
- The five constants (defaults proposed above).
- Whether the overflow is a "More ▾" menu vs a horizontally scrolling row.
