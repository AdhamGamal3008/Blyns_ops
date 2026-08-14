# Plan — Concurrent (parallel-stage) project workflow

> **This is an implementation plan, not a spec, and nothing here is built yet.**
> A future session must be able to execute it cold. Paths/line numbers are current
> as of **2026-08-14**; if a reference has moved, follow the real code.
>
> - Non-negotiables: fully custom; database-per-tenant; every write audited; tests
>   ship with the feature; config-driven; **existing sequential projects must be
>   byte-for-byte unaffected**.
> - Chosen approach: **Option A** — stages 2–8 are *real, full stages* that run in
>   parallel; only stage 9 (Handover) waits for all of them. Selectable per project
>   at creation (Stage 1).

## 0. What we're building, in one paragraph

Today every project runs one fixed 9-stage machine, strictly linear (1→2→…→9).
We add a second **workflow type** — `concurrent` — where, after Stage 1, stages
2–8 all open at once for different teams to work simultaneously, and Stage 9 only
becomes workable once **every** one of 2–8 is approved. The type is picked when the
project is created. We get there by making the stage engine **purely
dependency-driven** (it already evaluates declared `depends_on` gates; we just stop
force-enforcing linear order) and letting a per-project **template** decide the
shape: the `sequential` template keeps today's linear edges (behaves identically),
the `concurrent` template makes 2–8 depend only on Stage 1 and Stage 9 depend on
2–8.

## 1. Baseline — what exists to build on (read first)

| Thing | Where (real path:line) | Note for this feature |
|---|---|---|
| Stage machine (data) | `backend/app/modules/projects/stage_definitions.json` | 9 stages, each with `entry_gates` (incl. `dependency` gates w/ `depends_on`). Seeded into `tenant_db.stage_definitions`. |
| Dependency evaluation | `backend/app/modules/projects/engines.py:128-143` | Already checks declared `depends_on` gates — **keep**. |
| **Hardcoded linear loop** | `backend/app/modules/projects/engines.py:145-151` | `for order in range(1, definition["order"])` → "every lower-order stage must be approved." **This is the thing forcing linearity — remove it.** |
| Single-cursor advance | `backend/app/modules/projects/service.py:808-815` | On approve, `next_def = _definition(order+1)` and enters that one stage. **Generalize to enter-all-unlocked.** |
| Completion | `backend/app/modules/projects/service.py:796` | `if order >= LAST_STAGE_ORDER` → completed. **Keep as-is** (stage 9 depends on 2–8, so it can't approve early). |
| Lazy stage entry | `backend/app/modules/projects/service.py:176` `_enter_stage` | Creates one stage instance + runs the decision engine. Reused to enter each unlocked stage. |
| Create project | `backend/app/modules/projects/service.py:129` | Enters Stage 1 only. Add `workflow_type`. |
| Stage-def lookups | `repository.py:88` `stage_defs`, `:96` `stage_def_by_key`; `service.py:99` `_definition` | Make **workflow_type-aware**. |
| Seed + indexes | `backend/app/modules/projects/seed.py:24` (`_SEED_FILE`), `:47-48` (unique idx on `key` **and** `order`) | See gotcha G-1: unique index blocks two templates unless made compound. |
| Constants | `backend/app/modules/projects/permissions.py:62-63` | `FIRST_STAGE_ORDER=1`, `LAST_STAGE_ORDER=9`. |
| `ProjectCreate` | `backend/app/modules/projects/models.py` (`class ProjectCreate`) | Add `workflow_type`. |
| Pipeline UI | `frontend/src/client/projects/ProjectDetail.tsx:79` (stage rail), `StagePanel.tsx` | Renders a rail of all stages + the single active one via `current_stage_order`. Must show **multiple active** stages for concurrent. |
| Create form | `frontend/src/client/projects/ProjectsPage.tsx` | Add the workflow-type picker. |

**Load-bearing facts to preserve:**
- Integrations hook stage **keys**, not orders: Production drives `factory_release`,
  Finance/Inventory hook `material_procurement` / `final_inspection`. Key-based
  lookups survive re-shaping — **do not change stage keys**.
- Seed is idempotent (`$setOnInsert`); existing tenants already have stage docs
  **without** `workflow_type` → they need a backfill (G-2).
- `current_stage_order` is indexed and used for list filter/sort + the detail
  header. We keep it as a **representative pointer** (lowest active order), so those
  consumers keep working without a refactor.

## 2. Resolved values (no placeholders)

| Placeholder | Real value |
|---|---|
| Stage-def collection | `stage_definitions` (tenant DB) |
| Stage-instance collection | `stage_instances` (tenant DB) |
| Sequential type id | `"sequential"` (default) |
| Concurrent type id | `"concurrent"` |
| Project field | `workflow_type: "sequential" \| "concurrent"` |
| Stage-def field | `workflow_type` (same values) |
| API prefix | `/api/v1/projects` |
| Terminal stage | order **9** `final_inspection_handover` |

## 3. Deliverables

```
backend/app/modules/projects/stage_definitions.json      EDIT — add explicit dep on stage 4; add a "concurrent_stage_definitions" set
backend/app/modules/projects/seed.py                     EDIT — seed both templates; compound unique index; backfill workflow_type
backend/app/modules/projects/repository.py               EDIT — workflow_type-aware stage_defs / stage_def_by_key; active/unlocked helpers
backend/app/modules/projects/engines.py                  EDIT — drop the hardcoded linear loop (145-151); dependency-only gating
backend/app/modules/projects/service.py                  EDIT — workflow_type on create; enter-all-unlocked on approve; representative current_stage_order
backend/app/modules/projects/models.py                   EDIT — workflow_type on ProjectCreate (validated)
frontend/src/client/projects/ProjectsPage.tsx            EDIT — workflow-type picker in create form
frontend/src/client/projects/ProjectDetail.tsx           EDIT — render multiple active stages
frontend/src/client/projects/types.ts                    EDIT — workflow_type + multi-active types
backend/tests/integration/test_projects_concurrent.py    NEW  — concurrent lifecycle + sequential regression
frontend/src/__tests__/ConcurrentWorkflow.test.tsx       NEW  — picker + multi-active rail
```

## 4. Tasks (phased)

### Phase 0 — Data model + concurrent template (foundation)
- **stage_definitions.json**: (a) give **stage 4** (`measurement_verification`) an
  explicit `dependency` entry gate `depends_on: "design_package"` — today it relies
  on the hardcoded loop; once that loop is gone it must declare its real dependency
  or it would unlock early (G-3). (b) Add a **concurrent** stage set (same 9 keys,
  same approvers/gates) where stages 2–8 each have a single dependency gate
  `depends_on: "project_initiation"` and stage 9 depends on **all** of 2–8
  (`depends_on` list, or 7 dependency gates).
- **seed.py**: stamp `workflow_type: "sequential"` on the existing set; seed the
  `concurrent` set with `workflow_type: "concurrent"`. Replace the unique indexes on
  `key`/`order` with **compound** unique `(workflow_type, key)` and
  `(workflow_type, order)` (G-1). Backfill: `update_many({workflow_type: {$exists:
  false}}, {$set: {workflow_type: "sequential"}})` (G-2).
- **repository.py**: `stage_defs(db, workflow_type="sequential")`,
  `stage_def_by_key(db, key, workflow_type="sequential")` filter by type; add
  `active_stage_instances(db, project_id)` (entered, not approved).
- **models.py**: `ProjectCreate.workflow_type: Literal["sequential","concurrent"] = "sequential"`.
- **Prove:** a fresh tenant seeds both templates; `stage_defs(db)` still returns the
  9 sequential stages unchanged; `stage_defs(db, "concurrent")` returns the parallel set.

### Phase 1 — Dependency-driven engine
- **engines.py**: delete the `range(1, definition["order"])` loop (145-151). Gating
  is now the declared `depends_on` gates only (128-143), which the stage's
  `workflow_type` set already encodes. Pass the project's `workflow_type` into
  `stage_def_by_key` calls here.
- **service.py**:
  - `create_project`: persist `workflow_type`; `_definition`/first-stage lookups use it.
  - Approve (808-815): replace "enter order+1" with **enter-all-unlocked** — after
    marking a stage approved, find every not-yet-entered stage whose `depends_on`
    are all approved and `_enter_stage` each; recompute `current_stage_order`/`_key`
    = lowest-order active (entered, not approved) stage (fallback: the just-approved
    order). Completion check (796) unchanged.
  - `_definition(principal, order, workflow_type)` — thread the type through.
- **Prove:** every existing `test_projects.py` passes (sequential unchanged); a
  concurrent project: approve Stage 1 → stages 2–8 all become `in_progress` at once.

### Phase 2 — Selection at creation
- **models.py / service.py**: already carry `workflow_type`; validate it against the
  seeded templates. **ProjectsPage.tsx**: add a workflow-type picker (default
  Sequential) to the create form → send `workflow_type`.
- **Prove:** create a concurrent project via API and via the UI form.

### Phase 3 — Parallel pipeline UI
- **ProjectDetail.tsx / StagePanel.tsx / types.ts**: the stage rail already lists
  all stages; highlight **all** active ones, let the user open any active stage's
  panel; header shows "N stages · M active" for concurrent (keep "Stage X of N" for
  sequential). No new endpoint — the detail already returns all stage instances.
- **Prove:** open a concurrent project, advance two active stages independently,
  see Stage 9 stay locked until 2–8 are done.

### Phase 4 — Tests + hardening
- `test_projects_concurrent.py`: full concurrent lifecycle (1 → 2-8 parallel, any
  order → 9 blocked until all → 9 approves → completed) + a sequential-regression
  case. `ConcurrentWorkflow.test.tsx`: picker + multi-active rail.
- Confirm audits fire per stage; ruff/mypy/tsc clean; batched suite green.

## 5. Verification checklist

| # | Check | Command | Expected |
|---|---|---|---|
| 1 | Sequential unaffected | `pytest tests/integration/test_projects.py -q` | all green |
| 2 | Both templates seed | seed a tenant; count `stage_definitions` by type | 9 sequential + 9 concurrent |
| 3 | Parallel unlock | approve Stage 1 on a concurrent project | stages 2–8 all `in_progress` |
| 4 | Handover gate | try to submit/approve Stage 9 with any of 2–8 open | blocked (`dependencies_complete` fails) |
| 5 | Completion | approve all 2–8 then Stage 9 | project `completed` |
| 6 | UI | open a concurrent project | multiple active stages workable |
| 7 | Lint | `ruff check app && mypy app && (cd ../frontend && npx tsc --noEmit)` | clean |

## 6. Known gotchas — handle, don't rediscover

- **G-1 — unique index on `order`** (`seed.py:47-48`) blocks a second template with
  the same orders. Make the indexes **compound** on `(workflow_type, order)` and
  `(workflow_type, key)`.
- **G-2 — existing tenants** already have stage docs with no `workflow_type`. Backfill
  to `"sequential"` in the seed so they keep working after the index change.
- **G-3 — stage 4 has no declared dependency** (relies on the hardcoded loop). Add an
  explicit `depends_on: design_package` to the **sequential** template, or removing
  the loop lets stage 4 open in parallel with 1–3.
- **G-4 — `current_stage_order` consumers** (list filter/sort `service.py:118,121`;
  detail header) assume one active stage. Keep it as a *representative* pointer
  (lowest active order) so nothing breaks; the real gating is dependency-based.
- **G-5 — integration semantics**: the concurrent template reuses manufacturing stage
  keys, but `factory_release` genuinely needs `material_procurement` (materials
  reserved), `installation` needs `factory_release`, etc. **The seeded "all of 2–8
  parallel" set is a mechanism starting point**; the product owner must decide which
  concurrent stages keep real cross-dependencies (a general DAG) vs. truly
  independent team workstreams, before using it for real manufacturing projects.
  Production/Finance/Inventory hooks are key-based and keep working either way.

## Deviations from the source idea (intentional)

- **D-1 — engine, not per-type branching.** Rather than an `if concurrent:` fork, we
  make the engine purely dependency-driven and move the linear-vs-parallel decision
  into **data** (the template's `depends_on` edges). The sequential template's
  existing edges reproduce today's behavior exactly, so there's one code path and a
  strong regression guard.
- **D-2 — keep `current_stage_order`.** Instead of ripping out the single cursor
  (large blast radius), we keep it as a representative pointer. Lower risk, and the
  detail already returns all stage instances for the multi-active UI.

## Build status
- **Phase 0 — DONE** (commit `d4c2099`): data foundation; both templates seed;
  sequential unchanged; ruff/mypy clean.
- **Phase 1 — DONE**: engine is dependency-driven. `engines.py` evaluates the
  project's own template's gates and the hard-coded linear loop is gone;
  `_finalize_stage` enters every newly-unlocked stage (`_enter_unlocked_stages`)
  and keeps `current_stage_order` as the lowest active stage; timeline reports
  `workflow_type`. Verified: sequential regression (test_projects 19 +
  test_projects_v2 13 + production pipeline 6 = all green), concurrent stage 1 →
  2-8 open in parallel, 9 waits (test_projects_concurrent 6). ruff/mypy clean.
- **Phase 2 — DONE**: the New Project form has a Workflow picker (Sequential /
  Concurrent, default Sequential) that sends `workflow_type`; `Project`/`Timeline`
  TS types carry it. Verified: form sends the field (ProjectCreateWorkflow.test),
  tsc + 191 frontend green. (Concurrent value is accepted/persisted by the backend
  per Phase 1 tests.)
- **Phase 3 — DONE**: the project detail reflects the parallel shape — a
  "Concurrent" badge + "N of M stages complete · K in progress" header (sequential
  keeps "Stage X of N"), and a pipeline hint that 2-8 run in parallel. The stage
  rail already colours each stage by its own status and lets you open any active
  one, so no rail rewrite was needed. Verified: ConcurrentPipeline.test (concurrent
  vs sequential header); tsc + 193 frontend green.
- **Phase 4 — DONE**: full concurrent lifecycle test — create → approve Stage 1 →
  approve 2-8 in a scrambled order (Handover stays closed until the last) →
  Handover completes the project; every stage approved + completion audited
  (test_projects_concurrent.py, 7 tests). Hardening: whole backend suite batched
  green (settings/auth/dashboard/discovery/rbac/audit/production 176; crm/inventory/
  finance 91; projects 39; production pipeline 6; provisioning/admin 17), frontend
  193, ruff/mypy/tsc clean.

**FEATURE COMPLETE.** Concurrent projects are selectable at creation, run stages
2-8 in parallel, and complete only when Handover clears after all of them. See
gotcha G-5: the "all of 2-8 parallel" template is a mechanism starting point —
the product owner should review which concurrent stages keep real cross-deps
(e.g. procurement → production) before using it for real manufacturing projects.
