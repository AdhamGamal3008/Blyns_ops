# Production Module — Adaptation & Build Plan

> **Cold-executable plan.** A future session with no prior context can run this.
> Source spec: *"Production Module — Build Specification"* (Bovali Studio).
> Generated 2026-08-10. Decisions in §1 are **locked** by the product owner.
>
> **Read [`modules/PROJECT_WORKFLOW_V2_SOP.md`](./modules/PROJECT_WORKFLOW_V2_SOP.md)
> and [`PROJECT_MANAGEMENT_LIFECYCLE.md`](./PROJECT_MANAGEMENT_LIFECYCLE.md) first** —
> Production sits underneath the pipeline and this plan assumes the v2.0 9-stage
> machine that is live on `main`.

---

## 0. The reframing (read this before anything else)

The source spec is written in the **v1.0 16-stage** numbering. Our pipeline is the
**v2.0 9-stage** workflow (`backend/app/modules/projects/stage_definitions.json`,
`machine_version: 2`). Translate every stage reference and the module collapses
onto a **single live stage**:

| Spec says (v1 #) | Actually is now (v2) |
|---|---|
| "Stages 9–12 · Factory Production, QC, Packing, Delivery Planning" | **Stage 6 · Factory Release** (`factory_release`). Its seeded `release_checklist` **is** these four: `production`, `quality_control`, `packing_protection`, `delivery_planning`. |
| "Stage 6 drawings + BOM" (source deliverables) | shop drawings from **Stage 3 · Design Package** (`design_package`); the BOM is finalised at **Stage 5** |
| "Stage 8 stock reservation" | **Stage 5 · Material Procurement** (`material_procurement`; gate **G2** `bom_present` → `reserve_stock`) |
| "Stage 13 site-readiness date" (due-date back-calc target) | **Stage 7 · Site Readiness Inspection** (`site_readiness`) |

**Conclusion: the Production module is the execution surface that lives underneath
v2 Stage 6 · Factory Release.** v2 already consolidated the four v1 factory stages
into one `factory_release` stage with a four-section checklist and a single
`production_manager` approval — the spec explicitly assumes this ("Per SOP v2 the
four factory approvals consolidate to one release approval by production_manager").

Two facts verified in code:
- **No work-order code exists yet** anywhere in `backend/app` or `frontend/src` —
  clean slate.
- **Stage 6 already has the checklist machinery**: `release_checklist_complete`
  validation check in `engines.run_auto_validation`, marked via
  `POST /projects/{id}/stages/{order}/checklist/{section}` →
  `service.mark_checklist_section` (recorded as `checklist_done` on the stage
  instance). Production **drives** these sections; it does not reinvent them.

---

## 1. Locked decisions

| # | Decision | Choice | Consequence for the build |
|---|---|---|---|
| D1 | Rework accounting | **New Inventory reservation per rework** | A rework draws a fresh reservation/issue against Inventory (true material burn). No write-off path. Bake into the WO rework transition (Phase 2). |
| D2 | Subcontracted production | **Leave schema room, build later** | WO `station_route` is nullable and the WO carries an optional `subcontract { vendor }`. **No** external-vendor workflow in the MVP. Do not add receive-on-return logic yet. |
| D3 | Cost visibility on the floor | **Hidden** | Production views show qty/progress only. Cost stays on the project Finance tab. Job costs still flow to Finance (Phase 2). No cost field in any Production response body. |
| D4 | WO generation from BOM | **Auto-propose, `production_manager` confirms** | Phase 1 ships a *propose* endpoint returning draft WOs + a *confirm* endpoint that commits them. Never auto-commit. |

**Adopted defaults (not asked, conventional):** module is behind a Settings
toggle like every other module; floor sub-roles are soft "functions" (see §4);
`production_analytics` follows the cross-module analytics pattern and is deferred
to an optional Phase 5.

---

## 2. Core concept — the Work Order + the gate-mirroring contract

### 2.1 Work Order (WO)
One manufactured item or batch, below the project. One project → one or more WOs.

- **Version-pinned.** A WO pins to a specific **deliverable version**
  (`{deliverable_id, version}`), never "latest." Our deliverables are already
  versioned + immutable (`DELIVERABLE_KINDS` incl. `shop_drawing`, `bom`;
  `versions[]`), so this is native. If the pinned deliverable gains a newer
  version, the WO raises a visible **`revision_conflict`** — it never updates in
  place. Resolution is an explicit manager re-pin (may regenerate BOM lines).
- **The four WO phases map 1:1 to the Stage-6 checklist sections:**

  | WO phase (spec nav) | Stage-6 checklist section key |
  |---|---|
  | Production | `production` |
  | QC | `quality_control` |
  | Packing | `packing_protection` |
  | Dispatch | `delivery_planning` |

### 2.2 WO status model
```
Queued → Released → In progress → QC pending → QC hold ⇄ Rework
                                          ↓
                                       Passed → Packed → Staged → Dispatched
```
- **QC hold blocks the affected WO only** — never the project or the pipeline
  stage. (This is the whole reason the WO exists.)
- **Rework** (D1) draws a **new Inventory reservation** for the extra material,
  then returns the WO to `In progress`.

### 2.3 Gate-mirroring contract (the pipeline stays authoritative)

| Element | Owned by | Rendered in Production as |
|---|---|---|
| WO execution + phases | **Production** | live, editable |
| Stage-6 release approval | **Pipeline** | read-only checkpoint chip + an **"Approve in pipeline"** link |
| Stage-3 drawings + Stage-5 BOM | **Pipeline (Deliverables)** | read-only, version-pinned reference |
| Stage-5 reservation balance | **Inventory** | read-only balance |

**Sync rules (all enforced in Production's service, verified against the seed):**
1. **A WO cannot be released before Stage 5 is approved** (materials reserved).
   This is also the pipeline's precondition to *enter* Stage 6 (`materials_reserved`
   dependency), so in practice the project is already at Stage 6.
2. **A Stage-6 checklist section flips to done only when every non-cancelled WO on
   the project has cleared the corresponding phase.** Partial progress shows as a
   **percentage on the pipeline node**; the gate does not open early. Production
   writes the existing `checklist_done` flags (so `release_checklist_complete`
   keeps working unchanged) + a display-only `production_rollup` (per-section %).
3. **Production never hosts the approve button.** Release = the existing
   `POST /projects/{id}/stages/6/approve` (needs `projects` WRITE + the
   `production_manager` position via `engines.may_approve`).
4. **Fallback:** a project with **zero WOs** keeps manual checklist marking, so no
   existing project or test breaks. Production only takes over section-marking once
   ≥1 WO exists for the project.
5. Stage 6 (Dispatch/Delivery Planning) completes on a **confirmed schedule**, not
   on arrival — consistent with v2 (actual site work is Stage 7+).

---

## 3. Data model (tenant DB, new collections)

Conventions per `BUILD.md` §5: Mongo `ObjectId` internally → string `id` in bodies;
UTC BSON dates; `created_at/updated_at/created_by/updated_by`; soft delete
`is_deleted`+`deleted_at`; response envelope `{data, meta}`.

### `work_orders` (the aggregate)
```
_id, code (WO-{project_code}-{seq:02d}), project_id, crm_account_id (inherited),
client_name (inherited),
source_drawing { deliverable_id, version },      # pinned; §2.1
bom_lines [ { product_id, sku, description, qty, uom } ],   # snapshot at generation
qty { ordered, done },
station_route [ station_id | null ],             # null allowed for D2 subcontract
current_station_id,
assigned_function ("station_operator"|"qc_inspector"|"warehouse"|"logistics"|null),
assigned_user_id,
due_date,                                         # back-calc from Stage 7 target
status,                                           # §2.2
blocked_by { type ("material_shortfall"|"qc_hold"|"upstream_gate"), note },
revision_conflict bool,
subcontract { vendor } | null,                    # D2, schema room only
qc { checklist[], dimensional[], finish[], batch[], defects[], disposition, inspector_id },
packing { type, protection_spec, labels[], moisture_barrier_ref, handling[] },
dispatch { load, vehicle, delivery_window, delivery_note_ref, manifest_ref, site_notified_at },
history [ { at, by, from_status, to_status, note } ],   # immutable audit trail
created_at, updated_at, created_by, updated_by, is_deleted, deleted_at
```
> **No cost fields** (D3). Cost lives in Finance/job-costs.

### `production_stations` (work centres — seeded, tenant-editable)
```
_id, code, name, material_types[], capacity_units_per_day, is_active,
created_at, updated_at, ...
```
Seed a small default set (e.g. CNC, Edgebander, Assembly, Finishing, QC Bench,
Packing) — examples only, editable in Settings.

### `production_rollup` (display cache, keyed by project_id)
```
_id (=project_id), sections { production: pct, quality_control: pct,
  packing_protection: pct, delivery_planning: pct }, updated_at
```
Recomputed on any WO status change; read by the projects board/timeline for the
node %.

**Indexes:** `work_orders` on `{project_id}`, `{status}`, `{current_station_id}`,
`{assigned_user_id}`, `{due_date}`; unique on `{code}`. Add to the module `seed.py`
`_build_indexes`.

**Activity/audit (rule 4):** every write emits to the tenant `activity_log` —
`production.wo_created`, `wo_released`, `wo_progress`, `material_issued`,
`shortfall_flagged`, `qc_passed`, `qc_held`, `rework_started`, `wo_packed`,
`wo_staged`, `wo_dispatched`, `revision_conflict_raised`, `section_completed`.

---

## 4. RBAC design

- **New resource `production`** (add to `CLIENT_RESOURCES` in
  `backend/app/modules/settings/seed.py`): **VIEW** = read Queue + WO list ·
  **READ** = + WO detail, Stations, Quality, Dispatch · **WRITE** = floor actions
  (progress, request QC, QC pass/hold/rework + log defects, packing, staging,
  dispatch). Guard with `require("production", Level.X)` in the router.
- **New resource `production_analytics`** (deferred to Phase 5, management-only,
  like the other `*_analytics`).
- **Manager authority** (release WO, override station allocation) = the existing
  **`production_manager` approver position** (WRITE + position via
  `engines.holds_position`/`may_approve`), **not** a new resource level. Release
  itself is the pipeline action.
- **Floor sub-roles** (`station_operator`, `qc_inspector`, `warehouse`,
  `logistics`) = lightweight **production functions** (a per-user tag) used for the
  Queue default-filter + audit attribution + UI affordances. **Soft** in the MVP
  (any `production` WRITE may act, and every action is audited). Hard boundaries
  are a documented later upgrade.
- **Default role grants** (add to `default_roles()` + rely on the existing
  backfill so live tenants get the key; re-run `scripts/backfill_tenant_roles.py`):

  | Role | `production` | `production_analytics` |
  |---|---|---|
  | Owner | WRITE (all-resources map) | WRITE |
  | Manager | WRITE | READ |
  | Member | WRITE (ops-module convention) | NONE |
  | Viewer | NONE | NONE |

---

## 5. Module relations (concrete hooks)

| Module | Direction | Hook |
|---|---|---|
| **Projects / pipeline** | read | project `code`, `crm_account_id`, Stage-3 `shop_drawing` + Stage-5 `bom` deliverables (version-pinned), Stage-7 target date (due back-calc) |
| **Projects / pipeline** | write | drive Stage-6 `checklist_done` sections + `production_rollup`; surface "Approve in pipeline" link (release stays `POST /projects/{id}/stages/6/approve`) |
| **Inventory** | write | consume against the Stage-5 reservation (the `issue` tagged `ref_module="projects"`) on material issue; **rework draws a NEW reservation (D1)**; flag shortfalls against the reservation balance |
| **Finance** | write | per-WO labor hours → job costs (`COST_TYPES`=labor…; Stage-6 `post_job_costs`); material draws down the Stage-5 commitment. **No cost surfaced in Production (D3).** |
| **Settings / RBAC** | — | new `production` (+`production_analytics`) resource; `production_manager` position already seeded in `approver_role_map` |
| **Dashboard** | later | optional Queue quick-action widget |

⚠️ **Traps to respect** (from prior build notes):
- **BOM shadowing** — find the project BOM by kind; a line-less `bom` deliverable
  can silently shadow the real one. Applies to WO generation + reservation consume.
- **`crm_accounts` vs `accounts`** — CRM customers live in `crm_accounts`;
  Finance's ledger is `accounts`. Don't cross them.
- **Test-suite mongod OOM** — run the backend suite in batches; a full serial run
  OOM-kills the ephemeral mongod ~70% in (connection-refused cascade, not real
  failures).

---

## 6. API surface (`/api/v1/production`, kebab-case)

- `GET /production/queue` — cross-project work list. Default filter *my function /
  not-done / due ≤14d*; sort by due; group by station. Query overrides for all.
- `GET /production/work-orders` — full register, filterable (project, status,
  station, function, due, revision_conflict).
- `POST /production/work-orders/propose` — D4 auto-propose from a project BOM
  (returns draft WOs, commits nothing).
- `POST /production/work-orders` — confirm/commit proposed WOs.
- `GET /production/work-orders/{id}` — detail (read-only refs to drawing/BOM/reservation).
- `POST /production/work-orders/{id}/release` — guarded by sync rule 1.
- `PATCH /production/work-orders/{id}/progress` — qty done, current station.
- `POST /production/work-orders/{id}/issue-material` — consume from reservation.
- `POST /production/work-orders/{id}/shortfall` — flag against reservation.
- `POST /production/work-orders/{id}/qc` — pass / hold / rework + defect log.
- `POST /production/work-orders/{id}/re-pin` — resolve a revision conflict.
- `GET /production/stations` · `PATCH /production/stations/{id}` ·
  `POST /production/work-orders/{id}/allocate` (override — `production_manager`).
- `GET /production/quality` — defect / rework / hold register.
- `POST /production/work-orders/{id}/pack` · `.../stage` · `.../dispatch` ·
  `GET /production/dispatch` · `.../manifest`.
- `GET /production/projects/{id}/rollup` — the per-section % (feeds the pipeline node).
- (Phase 5) `GET /production/analytics`.

---

## 7. Build phases

Standard module package shape (`__init__ · models · permissions · repository ·
service · router · seed`). Tests ship with each phase (rule 6). Commit at each
boundary (confirm before committing/pushing — repo is `origin/main`).

### Phase 0 — Wiring & foundation
- **Backend:** create `backend/app/modules/production/`; mount router under
  `/api/v1/production` in `main.py`. Add `production` + `production_analytics` to
  `CLIENT_RESOURCES`; add default grants to `default_roles()` (§4). Seed default
  stations. Register the Settings module toggle.
- **Frontend:** add `{ key: "production", label: "Production", route:
  "/app/production", icon: <Factory/> }` to `MODULES` in `client/ClientShell.tsx`
  **between projects and inventory**; create `client/production/` shell + routed
  placeholders (Queue, Work Orders, Stations, Quality, Dispatch); add TS types.
- **Tests:** seed test (resources present, stations seeded); nav visibility (NONE
  hides, WRITE shows); provisioning resource/role counts updated.
- **Prove:** a fresh tenant has the `production` resource + seeded stations; the
  nav item shows for a WRITE role and is hidden at NONE.

### Phase 1 — Work Order object + Queue  *(spec Phase 1)*
- **Backend:** WO model + CRUD; `propose` + confirm generation from the project
  BOM (D4); version-pinning + `revision_conflict` detection; Queue endpoint
  (default filter/sort/group per §6); due back-calc from Stage 7.
- **Frontend:** Queue (default landing), Work Orders register, WO detail with
  read-only pinned drawing/BOM/reservation refs.
- **Tests:** generation from a seeded Stage-6 project BOM (respect BOM-shadow
  trap); revision conflict raised on a newer deliverable version; Queue default
  filter; due back-calc; RBAC (VIEW vs WRITE).
- **Prove:** auto-propose WOs from a project's BOM → confirm → they appear in the
  Queue grouped by station, sorted by due.

### Phase 2 — Status model + QC hold + pipeline drive  *(spec Phase 2)*
- **Backend:** WO status machine (§2.2); release guard (sync rule 1); issue
  material → **consume the Stage-5 reservation** + shortfall flag; QC
  records/defects; **QC hold blocks only the WO**; **rework → new reservation
  (D1)**; drive Stage-6 `production`+`quality_control` sections + `production_rollup`
  (sync rules 2 & 4); labor hours → Finance job costs; "Approve in pipeline" link
  (no approve button here).
- **Frontend:** WO detail actions (progress, request QC), Quality view (defect
  log, hold + rework register), read-only gate/approval chips + the pipeline link,
  node % surfaced.
- **Tests:** QC hold on one WO doesn't freeze the project or a sibling WO; release
  blocked before Stage 5 approved; consume against reservation; rework draws a new
  reservation; section flips only when all WOs clear it; labor → job cost; fallback
  (no-WO project still marks manually).
- **Prove:** two WOs on one project; hold one at QC → the project isn't frozen and
  the sibling proceeds; when both clear production+QC, those two Stage-6 sections
  show complete.

### Phase 3 — Stations view + load balancing  *(spec Phase 3 — not before Phase 1)*
- **Backend:** station load/capacity aggregation across active WOs; auto-allocation
  by load; manager override (`production_manager`).
- **Frontend:** Stations view (load/capacity by work centre); allocation override
  (manager-gated).
- **Tests:** load aggregation; auto-allocation; override RBAC.
- **Prove:** a Queue with several WOs shows realistic per-station load; a manager
  reallocates one.

### Phase 4 — Packing + Dispatch + manifest  *(spec Phase 4)*
- **Backend:** packing list from WO; protection spec by material type;
  moisture-barrier/labels/handling record; dispatch load + vehicle calc; confirm
  delivery window with the PM; delivery note + manifest generation; notify site
  supervisor (in-app/activity, **not** an external send); drive Stage-6
  `packing_protection` + `delivery_planning` sections.
- **Frontend:** Dispatch view (packed → staged → shipped), manifest.
- **Tests:** packing/protection by material; manifest generation; delivery-window
  confirm; all four sections complete → Stage 6 releasable.
- **Prove:** a WO goes packed → staged, the manifest generates, and with all WOs
  cleared Stage 6 is releasable in the pipeline.

### Phase 5 — Production Analytics *(optional, cross-module pattern)*
- `production_analytics` resource + `GET /production/analytics` (VIEW = KPIs:
  throughput, on-time %, WIP, hold rate; READ = + charts by station/phase) +
  Analytics tab, reusing `shared/timebuckets.py` + `client/analytics/parts.tsx`.

### Hardening
- Confirm every Production write is audited; rate limits (already global); full
  test suite green (batched); production config.

---

## 8. Deferred / out of scope (explicitly)
- **Subcontracted-vendor workflow** (D2) — schema room only now.
- **Hard floor-role boundaries** — soft functions now (§4).
- **Cost on the floor** (D3) — never; stays in Finance.
- **External notifications** — site-supervisor notice is in-app/activity only.
- **Production analytics** — Phase 5, optional.

---

*End of plan. Update §1 only with the product owner; everything else is derived.*
