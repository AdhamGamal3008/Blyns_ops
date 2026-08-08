# Project Analytics & Overview — Plan (Projects module first)

**Status:** PLANNED, not built. Cold-executable: read this + `docs/modules/PROJECT_MANAGEMENT.md`
+ `docs/AUTH_RBAC.md` before starting.

**Goal.** Give each business module (all except Settings) an **Analytics / Overview**
surface — headline KPIs + a small set of decision-grade charts — gated by role so it
is *not* visible to every user. This plan designs it in full for **Projects** and
establishes the reusable pattern (RBAC resource, endpoint shape, frontend tab) that
CRM / Inventory / Finance will copy.

---

## 1. What to show — the research (curated, all data-backed)

The domain is stage-gate construction / fit-out. The metrics that actually drive
decisions here, ranked, and each already supported by data we store:

### Tier 1 — Headline KPIs (the "at a glance" row)
| KPI | Meaning | Source |
|---|---|---|
| **Active projects** | `status = active` | `projects` |
| **On hold / blocked** | `status = on_hold`, or a live stage in `blocked/on_hold/waiting` (`STALLED_STATES`) | `projects` + `stage_instances` |
| **Overdue** | `schedule.delivery_date < now` and not `completed/cancelled` | `projects` |
| **Open exceptions** | reports in `open` + `in_progress` | `reports` |
| **Budget variance** | portfolio `Σ actual − Σ planned` (and %) | `projects.budget` |

### Tier 2 — Overview charts (decision-grade, ~5 curated)
| # | Chart | Question it answers | Type |
|---|---|---|---|
| **A** | **Portfolio by stage** — active projects per stage (1–9) | *Where is everything piling up?* (pipeline/funnel) | Bar |
| **B** | **Time in current stage** — avg days active projects have sat in their stage, by stage | *Where are the bottlenecks?* (the highest-value operational metric) | Bar |
| **C** | **Budget: planned vs actual** — portfolio + top-N projects; plus **cost by type** (labor/material/subcontractor/machine) | *Are we on budget? Where does spend go?* | Bar (grouped) + Bar |
| **D** | **Exceptions by type & status** — open exceptions by `type` (NCR/RFI/change/snag/issue/…), split open vs in_progress | *What's our quality/risk exposure?* | Bar (stacked) |
| **E** | **Throughput** — projects started vs completed per month, last 6–12 mo | *Are we clearing work faster than it arrives?* (momentum) | Area/trend |

### Stretch (data exists; ship after the core five)
- **F. Status mix** — active/on_hold/completed/cancelled/archived composition (donut or stat row).
- **G. Gate & approval health** — gate pass/fail/**waive** counts (waivers = governance red flag), rejection rate per stage.
- **H. Workload by PM** — active projects & open exceptions per `pm_id` / owner.

> Deliberately **excluded from v1** (needs schema work): true historical per-stage
> cycle time (entered→exited deltas across *completed* stages) and exception MTTR
> (`resolved_at` isn't stored). Metric **B** uses `now − entered_at` on the *current*
> stage instead — same bottleneck signal, one field, no migration. Add a
> `resolved_at`/stage-exit stamp later to unlock the historical versions.

---

## 2. Data mapping (collection → aggregation)

All tenant-DB collections; every pipeline filters soft-deletes (`repo._LIVE`).
Confirmed fields (from `backend/app/modules/projects/`):

- **`projects`**: `status`, `current_stage_order/_key`, `pm_id`, `created_at`,
  `completed_at`, `budget:{planned,committed,actual,currency}`, `schedule.delivery_date`.
- **`stage_instances`**: `project_id`, `order`, `stage_key`, `status` (state machine),
  `entered_at`, `completed_at`.
- **`reports`**: `type`, `status`, `owner_id`, `created_at`, `stage`.
- **`job_costs`**: `cost_type`, `hours`, `quantity`, `unit_cost`, `stage_key` (an
  aggregation, `job_cost_totals`, already exists to copy).
- **`gate_results`**: `passed`, `waived` (see `waived_gate_results`).

| Metric | Pipeline sketch |
|---|---|
| KPIs | `count_documents` per status; overdue = date filter; variance = `$group Σ budget.*`; open exceptions = status `$in [open,in_progress]`. |
| A by-stage | `$match status=active` → `$group by current_stage_order` → join stage_definitions for labels. |
| B time-in-stage | `$match` current stage instances of active projects → `$group by stage_key, avg(now − entered_at)`. |
| C budget | portfolio `$group Σ planned/actual`; top-N by `budget.actual`; cost-by-type = `$group job_costs by cost_type Σ(unit_cost·qty + …)`. |
| D exceptions | `$match status∈[open,in_progress]` → `$group by {type,status}`. |
| E throughput | two `$group by month`: `created_at` (started) and `completed_at` (completed), last N months. |

Feasibility: **A–E and all Tier-1 KPIs need zero schema changes.**

---

## 3. RBAC — how access is gated (the core requirement)

Ladder (`app/shared/enums.py`): `NONE=0 · VIEW=1 · READ=2 · WRITE=3`.
`level_for(resource)` defaults **missing keys to NONE**, so a new resource is
**safe-by-default** — nobody sees analytics until explicitly granted.

**Design: a dedicated resource `projects_analytics`** (not a reuse of `projects`),
so analytics can be granted to management without also granting it to everyone who
can read the project list. It joins the existing cross-cutting client resources
(`calendar`, `activity` are the precedent) in
`CLIENT_RESOURCES` (`app/modules/settings/seed.py`).

**Two meaningful tiers** (this is the "view and read access" the request asks for):
- **VIEW (1)** → the **Analytics tab + Tier-1 KPI row only** (the summary numbers).
- **READ (2)** → **everything** (KPIs + all charts + breakdowns).
- **NONE (0)** → no Analytics tab at all.

Server enforces it exactly like the dashboard KPIs ("a block the role can't reach is
simply absent"): router requires `VIEW`; the service adds the chart blocks only when
`level_for("projects_analytics") >= READ`.

**Default role seed** (`default_roles()` in settings/seed.py) — proposed:
| Role | projects_analytics | Rationale |
|---|---|---|
| Owner | READ | sees everything |
| Manager | READ | full oversight |
| Member | VIEW | headline numbers only |
| Viewer | NONE | no analytics |

⚠️ **Backfill trap (mirror commit `494abb0`).** `seed_default_roles` uses
`$setOnInsert`, so it will **not** add the new key to already-provisioned tenant
roles. A one-off **backfill** must `$set` `projects_analytics` onto existing roles'
permission maps (default `NONE`, plus the system-role defaults above), same as the
admin-resource backfill did. Without it, existing tenants get the key = NONE
(harmless, but the Settings RBAC editor won't show it until backfilled).

The Settings RBAC editor renders `CLIENT_RESOURCES` and validates against it
(`settings/service.py`), so adding the resource makes it appear and be editable
automatically — needs a human label ("Projects Analytics").

---

## 4. Backend design

- **Endpoint:** `GET /api/v1/projects/analytics`, guarded by
  `require("projects_analytics", Level.VIEW)`.
- **Service** (`projects/service.py` or a new `projects/analytics.py`): builds
  `{ kpis, by_stage, time_in_stage, budget, exceptions, throughput }`; the chart
  blocks are included **only** at `>= READ`. Reads are not audited (rule 4 = writes only).
- **Repository:** new `analytics_*` async fns, one per pipeline in §2, each `_LIVE`-filtered.
- **Response envelope:** standard `{data: …}`; blocks omitted (not null) when hidden,
  so the frontend's "render if present" stays clean.

---

## 5. Frontend design

- **Placement:** turn the Projects page into a `Tabs` surface — **Portfolio** (the
  existing `DataTable`) + **Analytics** (new). The Analytics tab is rendered only when
  `me.role.permissions["projects_analytics"] >= 1` (VIEW).
- **New component** `client/projects/ProjectsAnalytics.tsx`: fetches `/projects/analytics`,
  renders `KpiCards`-style tiles (`KpiCard` + `Grid`) then each chart in a `Card`.
  Each block renders **only if present** in the response (absent = the role's tier or
  an unreadable source hid it) — same pattern as `KpiCards`/`SuggestionsStrip`.
- **Reuse:** `KpiCard`, `Grid`, `Card`, `DataState`, and `TrendChart` / `BarChart`
  from `shared/ui/Chart`. Follow the **dataviz skill** for palette/labels at build time.

**Design-system gaps (small extensions, plan for them):**
- `BarChart` supports grouped series but **not stacked** → add an optional `stacked`
  prop (recharts `stackId`) for chart **D**.
- No donut → stretch metric **F** uses a horizontal stacked bar or stat row, or add a
  `DonutChart` later. Core five need only Bar + Area (already exist).

---

## 6. Phasing (each phase: ship tests, run the "Prove" check, commit)

- **Phase A — RBAC.** Add `projects_analytics` to `CLIENT_RESOURCES` + role defaults;
  write the backfill; label in Settings editor.
  *Prove:* new tenant seeds with the key; backfill adds it to an old tenant; Settings
  editor shows "Projects Analytics"; tests: NONE hidden, VIEW/READ granted.
- **Phase B — Backend.** Repo aggregations + service tiering + endpoint + tests.
  *Prove:* seeded fixture returns correct KPIs/series; `VIEW` → KPIs only, `READ` → all,
  `NONE` → 403.
- **Phase C — Frontend.** Projects tabs + `ProjectsAnalytics` + charts + tests.
  *Prove:* Analytics tab hidden at NONE, KPIs-only at VIEW, full at READ; charts render;
  responsive + a11y sweep clean.
- **Phase D — Rollout (separate).** Repeat for CRM / Inventory / Finance with
  `crm_analytics` / `inventory_analytics` / `finance_analytics` and each module's
  metrics. Same endpoint/tab/RBAC shape; only the pipelines differ.

---

## 7. Decisions — CONFIRMED (owner, 2026-08-06)
1. **Resource granularity: per-module.** `projects_analytics` now, and
   `crm_analytics` / `inventory_analytics` / `finance_analytics` in the Phase-D rollout.
   ✅ locked.
2. **Access tiers: two-tier VIEW/READ.** VIEW = Tier-1 KPI row only; READ = KPIs + all
   charts; NONE = no tab. ✅ locked (this is what §3–§5 build).
3. **Default role levels** (§3 table) stand as the default; the one remaining tunable
   knob is **Member = VIEW** (headline numbers) — flip to NONE in Phase A if analytics
   should be management-only.
