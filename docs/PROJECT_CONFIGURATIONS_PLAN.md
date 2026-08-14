# Plan — Tenant-defined Project Configurations

> **This is an implementation plan, not a spec, and nothing here is built yet.**
> A future session must be able to execute it cold. Paths/line numbers current as
> of **2026-08-14**; if a reference has moved, follow the real code.
>
> - Non-negotiables: fully custom; database-per-tenant; every write audited; tests
>   ship with the feature; existing projects must keep working unchanged.
> - Builds directly on the concurrent-workflow feature
>   (`docs/CONCURRENT_WORKFLOW_PLAN.md`) — read that first; ~70% of the plumbing
>   (scoped stage definitions, compound indexes, engine threading, create-form
>   picker, migration) already exists and is generalised here.

## 0. What we're building, in one paragraph

Each tenant can define **multiple named project configurations** in Settings — e.g.
"Standard cladding", "Flooring — ASTM", "Fast-track joinery" — where a configuration
is a self-contained set of the 9 stages' **entry documents + quality gates +
thresholds + workflow shape** (sequential/concurrent). At project creation (Stage 1)
the user picks **which configuration applies**; the project **pins that
configuration's current version** and runs against it immutably for its whole life.
Editing a configuration later publishes a **new version** and never disturbs projects
already running on an older one. This generalises today's fixed `workflow_type`
(sequential | concurrent) into tenant-owned, versioned configurations and closes the
gap that the *set* of gates per stage was seed-static.

## 1. Locked decisions (from the product owner, 2026-08-14)

| # | Decision | Choice | Consequence |
|---|---|---|---|
| D1 | Editing a running config | **Version-pin per project** | Each Save publishes an immutable version; a project pins the version current at its creation. In-flight projects untouched. Mirrors the deliverable/WO version-pinning already in the code. |
| D2 | Editor depth (v1) | **Tune on the fixed 9-stage skeleton** | Stage keys/order/count + approver positions + integrations are FIXED. Per config, tenants edit each stage's entry documents, its quality gates (add/remove from a catalog + custom, set threshold/blocking) and the workflow shape. No add/remove/reorder of stages (keeps module key-hooks safe). |
| D3 | Approvers | **Tenant-global** | Configs reference approver *positions* (`project_director`, …); who holds a position stays one tenant-wide `approver_role_map`. Not duplicated per config. |

## 2. Baseline — what already exists to build on (read first)

| Thing | Where (real path) | Reuse |
|---|---|---|
| Scoped stage definitions | `backend/app/modules/projects/repository.py` `stage_defs/stage_def_by_key/stage_def_by_order(..., workflow_type)` + `_wf_query` | Generalise the `workflow_type` scope → `(configuration_id, config_version)`. |
| Compound unique indexes + template seed | `backend/app/modules/projects/seed.py` (`_upsert_stage_defs`, `_concurrent_variant`, compound `(workflow_type, key/order)`, `_drop_legacy_index`, `machine_version` 3) | Same pattern, keyed by config+version. |
| Concurrent shape derivation | `seed._concurrent_variant(seq_defs)` | Reused to build a config's concurrent dependencies from its sequential stages. |
| Engine reads the project's own template | `engines.evaluate_stage` (re-fetch by `workflow_type`); `service._enter_unlocked_stages`; `_finalize_stage` guard; `service.timeline` | Thread `configuration_id + config_version` instead of `workflow_type`. |
| Gate rules (per tenant, editable) | `gate_rules` collection; `repo.gate_rule/gate_rules`; `service.patch_gate_config`; `GET/PATCH /config/gates` | Re-scope to `(configuration_id, config_version)`; the field-level patch folds into version-publish. |
| Stage config patch | `service.patch_stage_config`; `PATCH /config/stages/{key}`; `models.StageConfigPatch` | Same — its fields become part of the version-publish payload. |
| Create-form workflow picker | `frontend/src/client/projects/ProjectsPage.tsx` ProjectModal | Becomes the configuration picker. |
| Project workflow field + validation | `service.create_project` (validate + persist `workflow_type`); `models.ProjectCreate.workflow_type` | Becomes `configuration_id` (+ pinned `config_version`). |
| Migration | `scripts/migrate_projects_v3.py` | Extend to seed the two system configs + re-scope existing docs + pin existing projects. |
| Settings surfaces | `frontend/src/client/settings/*Section.tsx`, `SettingsPage.tsx` | Add a **Project Configurations** section next to Approvers/Roles. |

**Load-bearing facts to preserve:**
- Module integrations hook stage **keys** (`factory_release`→Production, `material_procurement`/`final_inspection`→Inventory/Finance). D2 keeps keys fixed, so they keep working.
- Seed is idempotent (`$setOnInsert`); existing tenants need an explicit migration run (the concurrent feature already learned this — see gotcha G-1).
- Approver positions are referenced by key from stages; the tenant-global `approver_role_map` resolves them (D3).

## 3. Data model (tenant DB)

### `project_configurations` (new — one doc per named config)
```
_id, name, description, workflow_shape ("sequential"|"concurrent"),
current_version (int), is_system (bool), is_default (bool), is_active (bool),
created_at/by, updated_at/by
```
- Two **system** configs seeded per tenant: "Standard" (sequential) and "Concurrent"
  (`is_system=true`, non-deletable). These carry the current 9 stages + 8 gate rules.

### `stage_definitions` + `gate_rules` — re-scoped
- Drop the `workflow_type` field; add **`configuration_id`** + **`config_version`**.
- Compound unique: `(configuration_id, config_version, key)` and `(…, order)` on
  `stage_definitions`; `(configuration_id, config_version, key)` on `gate_rules`.
- Each config **version** holds a full immutable copy of its 9 stage docs + its gate
  rules. (Bounded: ~17 docs per config-version.)

### `gate_catalog` (new — the tenant's library of gate definitions)
The tenant-wide catalog the editor attaches from: the **8 built-ins** (seeded,
read-only) + **tenant-created custom gates** `{key, name, type, default threshold,
blocking}`. Attaching a catalog gate to a stage **copies** its definition into that
config-version's `gate_rules`, where the threshold/blocking are then tuned. Custom
gates are created here. This collection is what actually **closes the gap** you
flagged — adding a gate to a stage is now a config edit, not a seed change.

### `projects` — pins the config
- Add **`configuration_id`** + **`config_version`**; **remove `workflow_type`**
  entirely — the sequential/concurrent shape now lives on the pinned config as
  `workflow_shape`. The Phase-0 migration maps every existing project's old
  `workflow_type` onto the matching system config (§6 P0).

### Versioning mechanic (D1) — client-side draft, publish-from-payload
- **No server-side draft.** The editor loads the config's current version, edits it
  entirely client-side, and **Publish** POSTs the full edited set (all 9 stages' entry
  docs + quality gates + thresholds + shape) as an **immutable new version**
  (`current_version+1`). There is nothing to reconcile server-side and no "someone's
  unsaved draft" state to manage. `project_configurations.current_version` advances.
- `create_project` **pins** `config_version = current_version` at creation; the engine
  always reads `(project.configuration_id, project.config_version)`. A published version
  is never mutated, so a running project's stages/gates can't shift under it.
- **Pruning (hardening only):** a version that no live project pins (and isn't the
  current) may be garbage-collected — not needed for correctness.

**Audit:** every config create/edit/publish/activate/set-default → tenant `activity_log`.

## 4. RBAC (no new resource)
The closest existing analog is the **approver-role map** — also project-machine config,
edited under **`settings` WRITE** (`PATCH /settings/approver-roles`), while the
pipeline *reads* the machine under `projects`. Follow it exactly:
- **Managing configurations** (create / clone / edit / publish / rename / set-default /
  activate / delete): **`settings` WRITE**. The editor lives in the Settings page next
  to Approvers/Roles, so the same admins who set approvers build configs.
- **Reading configurations for the Stage-1 picker**: **`projects` READ** — a PM
  creating a project can list/pick configs without Settings access (mirrors
  `GET /projects/config/stages`, already `projects` READ).
- Verified precedent: every `/settings/*` endpoint is `require("settings", …)`
  (`settings/router.py:31-32`); `settings` is already a `CLIENT_RESOURCE`. **No new
  RBAC resource, backfill, or role-tier change is needed.**

## 5. API surface (`/api/v1/projects/config`)
Guards: **[S-W]** = `settings` WRITE (tenant-admin management); **[P-R]** = `projects`
READ (anyone who can create a project).
- **[P-R]** `GET  /configurations` — active configs for the Stage-1 picker (name, shape, default).
- **[S-W]** `GET  /configurations/{id}` — a config's current version: its 9 stages + gates (feeds the editor).
- **[S-W]** `POST /configurations` — create by **cloning** a base (`{name, base_configuration_id}`).
- **[S-W]** `PATCH /configurations/{id}` — rename / set default / activate-deactivate.
- **[S-W]** `DELETE /configurations/{id}` — non-system only; blocked if any live project pins it.
- **[S-W]** `POST /configurations/{id}/versions` — **publish** a new immutable version
  from the full editor payload (per-stage entry docs + quality gates + thresholds + shape).
- **[S-W]** `GET/POST/DELETE /gate-catalog` — the tenant's gate-definition library (built-ins read-only + custom).
- The existing `PATCH /config/gates|stages` are **superseded** by version-publish and
  re-homed into the editor; keep them working against the tenant's *default* config
  during the transition, then remove.

## 5a. Out of scope for v1 (explicit)
- Add / remove / reorder **stages**, or changing stage keys/order (D2 — this is what
  protects the Production/Finance/Inventory key-hooks). The 9-stage skeleton is fixed;
  only its gates/documents/shape vary per config.
- **Per-config approvers** (D3 — approvers stay one tenant-global map).
- A visual drag-and-drop pipeline builder — the editor is a form per stage.
- Cross-tenant config sharing / a template marketplace.
- Server-side drafts or collaborative editing (publish-from-payload only).

## 6. Build phases  (size: S ≈ ½ day · M ≈ 1–2 days · L ≈ 3–5 days)

### Phase 0 — Data model + system configs + migration  **(L)**
- `project_configurations` collection + indexes; re-scope `stage_definitions`/`gate_rules`
  to `(configuration_id, config_version)` (generalise `seed._upsert_stage_defs`,
  compound indexes, `_wf_query`→`_config_query`). Seed the two **system** configs
  (Standard = current sequential set; Concurrent = derived). `machine_version` 4.
- `ProjectCreate.configuration_id`; persist `configuration_id + config_version`.
- **Extend `scripts/migrate_projects_v3.py`** (or a v4): create the two system configs,
  re-tag existing `workflow_type` docs onto them (`sequential`→Standard,
  `concurrent`→Concurrent) at `config_version=1`, and pin existing projects
  (`workflow_type`→`configuration_id`+`config_version=1`).
- **Prove:** a migrated tenant has 2 system configs; existing projects resolve their
  stages via the pinned config; sequential + concurrent regression green.

### Phase 1 — Engine threads configuration + version  **(S — generalises existing threading)**
- Replace `workflow_type` threading with `(configuration_id, config_version)` in
  `engines.evaluate_stage`, `service._enter_unlocked_stages`, `_finalize_stage` guard,
  `timeline`, and the **gate-rule lookups** (`repo.gate_rule(key, config_id, version)`).
- **Prove:** the full concurrent lifecycle + sequential regression pass unchanged
  (system configs reproduce today's behaviour).

### Phase 2 — Configuration CRUD (backend)  **(M)**
- `project_configurations` service + router (§5): list / create-by-clone / rename /
  set-default / activate / delete-guarded / publish. Publishing a version takes the
  full payload (per-stage entry docs + gates + thresholds + shape). Gate catalog
  (built-ins + custom-gate create). All audited.
- **Prove:** clone Standard → edit a threshold + add a gate to a stage → publish v2 →
  a NEW project on that config sees v2; an OLD project still sees v1.

### Phase 3 — Settings editor (frontend)  **(L — the biggest new surface)**
- Settings → **Project Configurations**: list; create (name + base); the per-stage
  editor (entry documents, quality gates from the catalog + thresholds/blocking,
  workflow shape); Save = publish version; set default; activate/deactivate.
- **Prove:** build a "Flooring — ASTM" config end-to-end in the UI.

### Phase 4 — Selection at Stage 1  **(S)**
- ProjectModal "Workflow" picker → **Configuration** picker (active configs, default
  pre-selected, shape shown as a hint). Project detail shows the config name + version.
- **Prove:** create a project on a custom config; its timeline/gates reflect that config.

### Phase 5 — Tests + hardening  **(M)**
- Version-pin isolation (edit-after-create doesn't move a running project); delete
  guard; RBAC; migration idempotency; batched suite green.

## 7. Verification checklist
| # | Check | Expected |
|---|---|---|
| 1 | Sequential + concurrent regression | green (system configs = today) |
| 2 | Clone + edit + publish | new version; catalog gate added to a stage |
| 3 | Version-pin isolation | editing a config leaves a running project's gates/docs unchanged |
| 4 | Delete guard | can't delete a config a live project pins; can't delete a system config |
| 5 | Create picker | project pins the chosen config + current version |
| 6 | Migration | existing tenants get 2 system configs; existing projects pinned |
| 7 | Lint | ruff + mypy + tsc clean |

## 8. Known gotchas
- **G-1 — migration must be RUN.** Like the concurrent feature, the version bump won't
  reach existing tenants automatically. Run the migration script; guard `create_project`
  and `_finalize_stage` so an un-migrated tenant fails clean, not with a 500 (that guard
  already exists from the concurrent bugfix — generalise it to "configuration seeded").
- **G-2 — stage keys are the integration contract.** D2 forbids changing keys/order in
  v1 for this reason. If the advanced tier ever adds/removes stages, the module hooks
  (Production/Finance/Inventory) need a key-presence check + graceful degradation.
- **G-3 — copy-on-attach keeps configs isolated.** Attaching a `gate_catalog` gate to
  a stage **copies** its definition into that config-version's `gate_rules`; tuning the
  threshold/blocking there must never write back to the catalog or to another config.
  The catalog holds reusable *definitions*; a config-version holds its own tuned copies.
- **G-4 — default/active invariants.** Exactly one default; at least one active config;
  a system config can't be deleted or fully deactivated.
- **G-5 — gate results are validated against the pinned version.** A stage instance's
  submitted gate results reference gate keys that must exist in the project's *pinned*
  config-version — which they do, since the engine reads that version. Don't validate
  against the config's *current* version.

## Deviations from the concurrent-workflow design (intentional)
- **D-1 — `workflow_type` becomes a configuration property, not a top-level enum.** The
  two enum values survive as the two seeded system configs, so the concept and the
  back-compat mapping are preserved while the mechanism generalises.
- **D-2 — versioned, not live.** The concurrent feature read the tenant template live
  (fine for two fixed shapes). Editable tenant configs require version-pinning (D1) to
  avoid moving goalposts mid-project.

## Build status
_not built yet._
