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
> **All seven pass as of 2026-08-17** — the results table is under
> "Build status → Phase 5" at the end of this document.

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

### Phase 0 — DONE (2026-08-16)
Data foundation shipped; sequential + concurrent regression green (41 tests),
15 new/updated configuration + seed tests, ruff + mypy clean.

- `repository.py` — `ConfigScope` value object + `_stage_scope_query`/`_gate_scope_query`
  (generalising `_wf_query`), `project_configurations` accessors, `scope_of`,
  `default_scope`, `scope_for_project`. `stage_defs`/`stage_def_by_order`/
  `stage_def_by_key` take a `ConfigScope | str`; `gate_rule(s)` take an optional
  scope defaulting to the tenant's default config.
- `seed.py` — `_ensure_system_configs` (Standard + Concurrent, keyed by a unique
  sparse `system_key` so re-runs never mint new `_id`s), `_adopt_legacy_definitions`,
  `_upsert_scoped`, `_drop_superseded_indexes` + `_build_definition_indexes`
  (compound unique on `(configuration_id, config_version, key|order)`).
  `machine_version` 4.
- `models.py` / `service.py` — `ProjectCreate.configuration_id`; `_resolve_configuration`
  (explicit id wins, else the system config for the requested shape); projects
  persist `configuration_id` + `config_version`. `patch_gate_config` now updates by
  `_id` — `key` alone became ambiguous once each config carries its own copies.
- `scripts/migrate_projects_v4.py` — re-seed + pin existing projects at version 1.

**One deviation from §6 as written, deliberate:** the v3 → v4 bump does **NOT** run
`_reset_definitions`. That reset also wipes `approver_role_map`, which tenants edit
through Settings, and v4 changes no stage key or order. `_SKELETON_VERSION = 3` now
gates the reset to skeleton bumps only; v4 adopts a tenant's existing (possibly
edited) definitions in place.

### Phase 1 — DONE (2026-08-16)
The engine reads the configuration version each project pinned. `engines.py` no
longer mentions `workflow_type` at all.

- `engines.evaluate_stage` resolves `repo.scope_for_project(db, project)` once and
  uses it for the definition re-fetch (via the new `repo.in_scope`), the dependency
  `stage_def_by_key` lookup and every `gate_rule` lookup. `run_decision_engine` and
  `run_auto_validation` inherit it.
- `service._definition(principal, project, order)` now takes the **project** and
  resolves through its pinned scope — all 11 call sites updated. `_definition_in`
  distinguishes an undefined stage (404) from an unseeded configuration (409 with
  the migration hint), so the G-1 guard fires at every entry point rather than only
  at approve.
- Threaded: `_enter_unlocked_stages`, `timeline` (which now also returns
  `configuration_id` + `config_version`), the `_finalize_stage` guard and its
  `defs_by_order`, both rollback-target lookups, `record_gate_result` / `waive_gate`
  gate lookups, `_resolve_doc_stage`.
- `/config/stages|gates` now read the tenant's **default** configuration explicitly
  via `repo.default_scope` instead of falling through the legacy filter.
- 3 new tests prove the pin is honoured end-to-end: publishing a v2 that adds a
  document gate changes what NEW projects wait on and leaves a running project
  untouched; gate thresholds resolve per pinned version; timeline reports the pin.

**Correction to the Phase-0 note above:** `workflow_type` should NOT be fully retired.
It has two remaining legitimate jobs — on a **project** it is a denormalised mirror of
the pinned config's `workflow_shape` that the frontend renders (retire with the
frontend in Phase 4, if at all), and on **stage docs** it is the legacy-tolerance path
that keeps an un-migrated tenant working (G-1), so it must survive until every tenant
has run the v4 migration.

### Phase 2 — DONE (2026-08-16)
Configuration CRUD, version publishing and the gate catalog, all audited.
21 new tests in `tests/integration/test_projects_configurations_crud.py`.

- **New module `configurations.py`** (service, alongside `analytics.py`) — list /
  get / create-by-clone / patch / delete-guarded / publish-version / gate catalog.
- **`gate_catalog` collection**, seeded with the 8 built-ins (`is_builtin`,
  undeletable) + tenant-created custom gates. Attaching copies the definition into
  the config-version's `gate_rules` (G-3); deleting a catalog entry leaves
  published versions working.
- **Endpoints** under `/api/v1/projects/config/…`: `configurations`,
  `configurations/{id}`, `configurations/{id}/versions`, `gate-catalog`.
  `GET /configurations` is **`projects` READ** (the Stage-1 picker); everything
  else is **`settings` WRITE** — no new RBAC resource, exactly as §4 predicted.
- **G-4 invariants enforced:** exactly one default (setting one demotes the other);
  the default can be neither cleared nor deactivated; at least one active config;
  system configs are never deletable; a config a live project pins is never
  deletable (deactivate instead, which leaves running projects alone).
- **Publish semantics:** stages the payload omits carry over unchanged; dependency
  edges are carried over and re-derived **only** when `workflow_shape` changes
  (the seeded sequential chain uses semantic gate keys — `design_frozen`,
  `goods_released` — that cannot be regenerated, so they must not be rebuilt on
  every publish). Unknown stage keys and uncatalogued gates are rejected (D2/G-2).

**Behaviour change worth knowing:** `create_project` with no `configuration_id`
now resolves to the tenant's **default configuration** rather than always the
Standard system config. `workflow_type: "concurrent"` still maps to the Concurrent
system config for back-compat. Without this, setting a custom config as default had
no effect on project creation.

### Phase 3 — DONE (2026-08-16)
Settings → **Project configurations**. 14 new frontend tests; 207 frontend tests
green; `tsc --noEmit` clean.

- `client/settings/configurationTypes.ts` — shared types + `humanize` (mirrors the
  backend's `seed.gate_label`).
- `ConfigurationsSection.tsx` — the list (name, shape, version, default/built-in/
  inactive badges) with Edit stages / Set default / Activate-Deactivate / Delete,
  plus the clone modal. Every mutating control is hidden without `settings` WRITE.
- `ConfigurationEditor.tsx` — the per-stage editor. Loads the current version,
  edits **entirely in local state**, and Save publishes the whole set as the next
  version (§3 publish-from-payload — nothing is half-saved server-side). Per stage:
  entry documents (add/rename/blocking/remove) and quality gates attached from the
  catalog with their thresholds tuned inline. Workflow shape is a top-level select.
  A banner states that the 9 stages are fixed (D2), and each stage shows its
  approver position read-only.
- `GateCatalogModal` — create a tenant's own measurement/inspection gate.

**Prove — done in the real UI against the local `acme` tenant:** cloned Standard →
"Flooring — ASTM" (v1) → added an `astm_f2170_report` document to Stage 1, attached
`concrete_rh_astm_f2170` to it, retuned `max_rh_pct` 75 → 70 → published v2.
Verified in Mongo: v1 untouched (3 docs, no gates, threshold 75); v2 has 4 docs, the
attached gate, threshold 70, still 9 stages, and Stage 5 carried over with its
approver and dependency chain intact.

**Bug found and fixed during the prove:** a threshold is a free-form object mixing
numbers, strings and booleans (`{max_rh_pct: 75, method: "ASTM F2170", configurable:
true}`). Rendering every field as a text input coerced `true` → `"true"` and
`75` → `"75"` on edit, which would silently stop the gate evaluating. `ThresholdField`
now picks its control from the seeded value's type and preserves it; a test pins it.

### Phase 4 — DONE (2026-08-16)
Selection at Stage 1. 213 frontend tests green (6 new/rewritten); backend
configuration suite 40 green; ruff + mypy + tsc clean.

- `ProjectsPage.tsx` — the Workflow select is now a **Configuration** picker fed by
  `GET /projects/config/configurations?active_only=true`, with the tenant's default
  preselected and the shape + description + pinned version spelled out in the hint.
  It sends `configuration_id`; `workflow_type` is no longer sent from the UI at all.
- `ProjectDetail.tsx` — the header carries a `"<name> v<version>"` badge. The
  version is part of the identity, not a footnote: two projects on the same
  configuration can be running different versions.
- `service.timeline` also returns `configuration_name`, resolved server-side so the
  detail header needs no second round-trip to turn an id into a label.
- The picker **hides itself** when the workspace has no configurations (an
  un-migrated tenant), and the create payload then omits `configuration_id` so the
  legacy fallback still applies (G-1) — the form never blocks.

**Prove — done in the running app against the local `acme` tenant:** created
"ASTM Flooring — Block C" on the custom "Flooring — ASTM" configuration. Its header
reads `Flooring — ASTM v2`, Stage 1 lists four entry requirements including the
`astm_f2170_report` added in the Phase-3 prove, and its Quality Gates show
`Concrete rh astm f2170` — a gate the Standard configuration does not put on Stage 1
at all. A backend test pins the same thing plus the converse: a project on the
default configuration sees none of it.

`ProjectCreateWorkflow.test.tsx` was rewritten for the picker. Note for whoever
touches it: Radix's `SelectValue` does not render its label in jsdom until the
listbox mounts, so preselection is asserted through the hint (which names the
default's version) and the submitted payload, not the trigger's text.

### Phase 5 — DONE (2026-08-17) · **the feature is complete**
7 new hardening tests in `test_projects_configurations_hardening.py`; the whole
suite green in batches: **391 backend integration + 110 unit + 213 frontend**.

Hardening applied to `publish_version`:
- **Numbering steps over debris.** The next version is `max(current_version,
  highest version present) + 1`, so a publish that died partway no longer blocks
  every retry at that number forever.
- **A racing publish is rejected, not silently lost.** Two editors reading the same
  `current_version` both compute the same next one; the compound unique index
  catches the loser, who now gets a 409 telling them to reload. Overwriting would
  have destroyed the winner's published version with nobody the wiser.
  *`insert_many` reports a duplicate key as `BulkWriteError`, **not**
  `DuplicateKeyError` — they are siblings, so catching only the latter lets it
  escape as a 500. The first version of this fix had exactly that bug; the race
  test is what found it.*
- `create_gate_catalog_entry` likewise falls back to the unique index, since its
  pre-check is not atomic.

Tests added:
- **Version-pin isolation across a full lifecycle** — a project is driven through
  all nine stages while a v2 adding a blocking document *and* a quality gate to
  Stage 5 is published mid-flight. It completes on v1 throughout; a project started
  after the publish gets both additions. This is the strongest statement of D1.
- **Delete guard covers completed projects**, whose definitions are still needed to
  render their history.
- **Migration idempotency** — the real `scripts/migrate_projects_v4.py` is loaded
  and run twice: stable config ids, no duplicated definitions, nothing re-pinned.
- **Migration maps each project to its own shape** — concurrent projects land on
  Concurrent (and resolve the 7-edge parallel DAG), sequential and pre-v3 projects
  on Standard.
- **Every management route is `settings` WRITE** (8 routes asserted), while the
  Stage-1 picker stays readable on `projects` READ alone.

#### Verification checklist (§7) results — ALL PASSING (2026-08-17)
| # | Check | Result |
|---|---|---|
| 1 | Sequential + concurrent regression | green — 41 tests, system configs reproduce today |
| 2 | Clone + edit + publish | green — new version; catalog gate attached to a stage |
| 3 | Version-pin isolation | green — holds across a full nine-stage lifecycle |
| 4 | Delete guard | green — system configs and pinned configs both refused |
| 5 | Create picker | green — project pins the chosen config + current version |
| 6 | Migration | green — idempotent; 2 system configs; projects pinned by shape |
| 7 | Lint | green — ruff + mypy + tsc clean |

### Known follow-ups (deliberately not in v1)
- **Orphaned definitions.** Deleting a configuration soft-deletes the config doc
  but leaves its `stage_definitions` / `gate_rules` behind. §3 calls pruning
  hardening-only and not needed for correctness; it stays unbuilt.
- The migration has **only been run against the local dev tenants** so far.
