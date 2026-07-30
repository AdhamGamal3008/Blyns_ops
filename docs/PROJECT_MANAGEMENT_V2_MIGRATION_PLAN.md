# Plan — Project Management v2.0 (16-stage → 9-stage workflow migration)

> **This is an implementation plan, not a spec, and nothing here is built yet.**
> A future session must be able to execute it cold. It migrates the existing
> **v1.0 16-stage** Project Management module to the **v2.0 9-stage** workflow.
>
> - **Business source of truth:** `docs/modules/PROJECT_WORKFLOW_V2_SOP.md`
>   (the "Bovali Studio — Project Delivery Workflow v2.0" SOP).
> - **Current module spec (v1.0):** `docs/modules/PROJECT_MANAGEMENT.md` — still
>   describes the 16-stage machine. **It must be revised as part of this work**
>   (see Phase 6) so the two stop disagreeing.
> - **No third-party AI/ML.** Everything stays in-house, deterministic, config-
>   driven — per the project non-negotiables (`CLAUDE.md`).
> - Paths/line numbers are current as of 2026-07-29. If a spec conflicts, follow
>   the real code.

---

## 0. What changes, in one table

| | v1.0 (built) | v2.0 (target) |
|---|---|---|
| Stages | 16 | **9** |
| Approver roles | 16 seeded positions | **6** |
| Blocking gates | 8 gate_rules, all blocking | **5 hard gates** (G1–G5); the other 4 demoted to *logged, not blocking* |
| Entry documents (Stage 1) | 5 | **3** |
| New engine behaviours | — | **auto-advancing stage**, **gate waiver** (director-only), **severe→rollback to an earlier stage**, **approver delegation** |
| Client approver | `client` position on Stages 4/5/6/15/16 via client-portal | **No client approver stage**; client acceptance folds into Stage 9 (`project_director`) + "written client acceptance" for open snags |

The redesign's own words: *"Nothing technical was deleted. Checks that used to
block now log."* Keep every measurement; change only whether it blocks.

---

## 1. Baseline — what exists today (read this first)

The module is thoroughly built and tested. Key files (`backend/app/modules/projects/`):

| File | Role | Migration impact |
|---|---|---|
| `stage_definitions.json` (473 L) | **The seed**: 16 stage_definitions + 8 gate_rules + report_types + approver_role_map + foundational_phases | **Rewritten** — the heart of this migration |
| `seed.py` (98 L) | Idempotent tenant seed. `_upsert_by` uses **`$setOnInsert` keyed by `key`** | **Changed** — see the migration trap in §3 |
| `engines.py` (350 L) | Automated Decision Engine + Universal Approval Engine + gate evaluators | **Extended** — auto-advance, waiver, rollback |
| `service.py` (1473 L) | Orchestration (create/enter, submit/approve/reject, integrations, deliverables, reports, job-costs, config) | **Extended** |
| `models.py` (220 L) | Pydantic payloads | New payloads (waiver, delegation) |
| `permissions.py` (70 L) | RBAC vocab, `GATE_DOCUMENT_KINDS`, `CLIENT_APPROVER_ROLE`, `DEFAULT_REJECT_REPORT` | Updated gate/kind maps |
| `router.py` (358 L) | API surface + `_approve_access`/`_document_access` (client-portal guards) | New endpoints (waive, delegation) |
| `repository.py` (208 L) | Mongo access, collection names | New collections (waivers/delegations if added) |

**Runtime collections** (`repository.py`): `projects`, `stage_definitions`,
`stage_instances`, `pm_tasks`, `gate_rules`, `gate_results`, `approvals`,
`deliverables`, `reports`, `job_costs`, `approver_role_map`,
`foundational_phases`, `counters`.

**How a project flows today** (unchanged mechanics we build on):
`create_project` → `_enter_stage` (upsert stage_instance `pending`, run decision
engine) → `submit_stage` (draft→auto_validation→`pending_approval`, or fail→Issue
Report) → `approve_stage` (re-validates, **runs integrations while still
`pending_approval`**, marks approved, advances) / `reject_stage` (typed report,
`bump_recovery`, on_hold-or-reopen).

**Load-bearing facts / traps to preserve** (from memory + code — do not regress):
1. **`crm_accounts` vs `accounts`** — CRM customers are `crm_accounts` (CRM
   `repo.ACCOUNTS`); Finance ledger is `accounts`. Stage 1 links via CRM.
2. **BOM shadowing** — stock reservation matches the BOM with `lines.0 $exists`
   (newest), so a `bom_present` *document* (kind `bom`, no lines) never shadows
   the real BOM. Keep this in the new Stage 5.
3. **on_hold clear does NOT re-run the decision engine** (`_maybe_clear_hold`) —
   the breaching reading is still latest and would snap it back.
4. **Integrations run while `pending_approval`** so a failing side effect leaves
   the stage recoverable. Keep for the new Stage 5 (reserve) / Stage 9 (handover).
5. **Client approval keys off the seeded `is_client_portal` role flag**, never
   the role name (acceptance #9).
6. Reservation is an Inventory **`issue`** (no reservation primitive); commits
   `Σ cost_price×qty` to `budget.committed`; a **material** job cost draws
   `committed` down so reserved-then-consumed counts once.

---

## 2. Target — the 9 stages (v2.0)

Proposed `stage_definitions.json` shape (keys are new; keep them stable — tests,
`GATE_DOCUMENT_KINDS`, and any deep-links reference them). `approver_role: null`
marks the auto-advancing stage.

| # | key | name | approver_role | entry gates | quality gates (blocking) | recovery |
|---|-----|------|---------------|-------------|--------------------------|----------|
| 1 | `project_initiation` | Project Initiation | `project_director` | `loi_or_po`, `scope_boq_approved`, `site_access_confirmed` (3 docs) | — | missing_docs → `waiting` |
| 2 | `site_survey` | Site Survey & Technical Assessment | **`null` (auto-advance)** | dependency: stage 1 approved | — (record `substrate_soundness`, non-blocking) | — |
| 3 | `design_package` | Design Package | `design_manager` | dependency: stage 2 done | — | rejection → `rejected` (V2 loop) |
| 4 | `measurement_verification` | Measurement Verification & Design Freeze | `engineering` | `shop_drawings_present`, `raw_site_data_present` | **G1** `deviation_within_tolerance` (≤3mm; severe >6mm) | severe → **return_to_stage** `design_package` |
| 5 | `material_procurement` | Material Procurement | `procurement_manager` | `bom_present` (**G2**) + dependency: stage 4 | — | supplier_delay → `in_progress` |
| 6 | `factory_release` | Factory Release | `production_manager` | dependency: stage 5 (materials reserved) | — (4-section checklist, §5-C) | qc/damage → `rejected`/`in_progress` |
| 7 | `site_readiness` | Site Readiness Inspection | `project_manager` | dependency: stage 6 | **G3** `concrete_rh_astm_f2170`, **G4** `subfloor_flatness` | site_not_ready → `on_hold` |
| 8 | `installation` | Installation | `project_manager` | dependency: stage 7 cleared | **G5** `timber_moisture_content` | installation_issue → `on_hold` (issue report) |
| 9 | `final_inspection_handover` | Final Inspection & Client Handover | `project_director` | dependency: stage 8 | — (snag list, §5-C) | inspection_failure → `rejected` (capa); terminal on approve |

**Approver_role_map (6):** `project_director`, `design_manager`, `engineering`,
`procurement_manager`, `production_manager`, `project_manager` → default
`client_roles: ["owner"]`.
**Remove** the 11 obsolete positions: `engineering_manager`, `procurement`,
`production_supervisor`, `qc_manager`, `qc`, `warehouse_manager`, `logistics`,
`site_engineer`, `site_supervisor`, `finance`, `client`.
(`production_supervisor` → `production_manager` is effectively a rename.)

**Gate rules — the 5 hard gates:**
- Keep blocking: `deviation_within_tolerance` (G1, keep severe tier), `bom_present`
  (G2 — a **document** entry gate, not a measurement rule), `concrete_rh_astm_f2170`
  (G3), `subfloor_flatness` (G4), `timber_moisture_content` (G5).
- **Demote** (see decision D3): `substrate_soundness`, `ambient_rh_temp_log`,
  `fixing_channel_alignment`, `reveal_gap_3mm`.

**v1.0 → v2.0 mapping** (from SOP §6 — needed for the data migration in §3):

| v1.0 order | v1.0 key | → v2.0 order | v2.0 key |
|---|---|---|---|
| 1 | lead_conversion | 1 | project_initiation |
| 2 | requirements_collection | 1 | project_initiation |
| 3 | site_survey | 2 | site_survey |
| 4 | concept_design | 3 | design_package |
| 5 | material_selection | 3 | design_package |
| 6 | shop_drawings | 3 | design_package |
| 7 | site_measurement_verification | 4 | measurement_verification |
| 8 | material_procurement | 5 | material_procurement |
| 9 | factory_production | 6 | factory_release |
| 10 | factory_qc | 6 | factory_release |
| 11 | packing_protection | 6 | factory_release |
| 12 | delivery_planning | 6 | factory_release |
| 13 | site_readiness | 7 | site_readiness |
| 14 | installation | 8 | installation |
| 15 | final_qc | 9 | final_inspection_handover |
| 16 | client_handover | 9 | final_inspection_handover |

---

## 3. The seed & data-migration trap (READ — this will bite)

`seed.py` `_upsert_by` does `update_one({key}, {$setOnInsert: doc}, upsert=True)`
and `stage_definitions` has **unique indexes on both `key` AND `order`**. So on a
tenant that already has the v1.0 seed:
- A naive re-seed **fails**: new `design_package` (order 3) collides with the
  existing `site_survey` (order 3) on the unique `order` index → E11000.
- Even without the collision, `$setOnInsert` **never updates** existing docs and
  **never removes** the 7 dropped stages / 11 dropped roles / demoted gates.

**Therefore the seed must be version-aware.** Plan:
1. Add `"machine_version": 2` (top level) to `stage_definitions.json`.
2. Store the applied version per tenant (e.g. a `pm_meta` doc, or reuse
   `foundational_phases`/a `_meta` collection).
3. In `seed.py`, if the tenant's stored version `< 2`, **reset the definition
   collections** (`stage_definitions`, `gate_rules`, `approver_role_map`,
   `foundational_phases`, `report_types`) — `delete_many({})` then insert the v2
   set — then run the **in-flight project remap** (below), then record version 2.
   Fresh tenants (no version) just seed v2 directly. Runtime collections
   (`projects`, `stage_instances`, `gate_results`, …) are never wiped.
   > This intentionally discards tenant *customisations* to the stage templates
   > on the version bump. That is acceptable pre-production (see D1); if real
   > tenants existed, we'd merge instead.

**In-flight project remap** (only if D1 = "migrate", not "reset"): for every live
project, map `current_stage_order`/`current_stage_key` via the §2 table, and
collapse existing `stage_instances` to the 9-stage numbering (multiple v1.0
instances can map to one v2.0 stage — keep the furthest-progressed, or the
approved one). Provide this as `scripts/migrate_pm_v2.py`, runnable per tenant.

**Recommendation (D1):** the system is **pre-production** (demo `acme` tenant
only; nothing merged to `main` depends on live PM data). Do the **reset** path for
local/test and ship the version-aware seed + a migration script for
completeness. Re-provision the demo tenant rather than remap it.

---

## 4. New engine capabilities (the genuinely new code)

### 4-A. Auto-advancing stage (Stage 2)
Stage 2 has **no approver** and "auto-advances on completion".
- `stage_definitions.json`: Stage 2 gets `approver_role: null`, add
  `"auto_advance": true`.
- `service.submit_stage`: when `definition.get("auto_advance")` (or
  `approver_role is None`): run `run_auto_validation`; on pass, **advance inline**
  — reuse the approve path (mark instance `approved`, append `stage_history` with
  `result:"auto_advanced"`, enter the next stage) **without** `_assert_may_approve`
  and without a `pending_approval` limbo. Record an approval doc with
  `decision.by:"system"`, `state:"approved"` for the audit trail. On validation
  fail, behave as today (Issue Report, back to `in_progress`).
- Guard: still `projects` WRITE to trigger (the Engineering owner submits when the
  survey report is attached). Log `stage.auto_advanced`.
- **Extract** the "mark approved + advance to next / complete" tail of
  `approve_stage` (lines ~654–691) into a private `_advance_from(...)` helper so
  both `approve_stage` and the auto-advance path share it (no duplication).

### 4-B. Gate waiver (director-only, in writing, recorded)
A hard gate can be waived **only** by `project_director`, with a reason, recorded
against the project (SOP §3).
- **Model it as a passing gate_result with provenance** — minimal engine change,
  since `evaluate_stage` already treats any `gate_result` with `passed:true` as
  satisfied. A waiver is a `gate_results` doc:
  `{stage_instance_id, gate_key, type, passed:true, severe:false, waived:true,
  reason, waived_by, captured_at}`.
- New payload `GateWaive(reason: str  # min_length=1)` in `models.py`.
- New endpoint `POST /projects/{id}/stages/{order}/gates/{gate_key}/waive`
  (`router.py`), guarded so the caller holds the **`project_director`** position
  (`engines.may_approve(db, "project_director", user_id, role_name)`), not just
  `projects` WRITE. `service.waive_gate(...)` records the waiver result + logs
  `gate.waived`. Because it's a passing result, `run_auto_validation` /
  `evaluate_stage` now pass that gate — no other engine change needed.
- Surface `waived:true` gates in the handover pack's "gate records G1–G5" (SOP §9).

### 4-C. Severe deviation → return to an earlier stage (Stage 4 → Stage 3)
v1.0 severe → `on_hold`. v2.0 G1 severe → **return to Stage 3 for redesign**.
- Give Stage 4's recovery block `{"on":"severe_deviation","action":"return_to_stage",
  "target":"design_package","state":"rejected"}`.
- `service.reject_stage`: when `recovery.action == "return_to_stage"` (or a
  `recovery.target` names a different, earlier stage), **roll back**: set the
  project's `current_stage_order`/`current_stage_key` to the target stage, reopen
  the **target** stage instance (`in_progress`, run decision engine), and mark the
  current (Stage 4) instance `rejected`. Emit the typed report as usual. Log
  `stage.rolled_back` with `{from, to}`.
- `engines.next_status`: today `severe → on_hold`. Keep that as the *holding*
  state while awaiting the approver's decision, **but** the rollback happens on
  `reject`. (I.e. a severe reading blocks approval; the human rejects; the
  recovery rolls back to Stage 3.) Document this so it isn't "fixed" back to a
  silent auto-rollback.

### 4-D. Approver delegation (own phase — can ship after 4-A/B/C)
"An approver may delegate to a named deputy in writing for a defined period …
never to the person who executed the work." (SOP §2)
- New collection `approver_delegations`:
  `{approver_role, delegate_user_id, granted_by, reason, starts_at, ends_at,
  revoked:false, created_at}`. Index `approver_role`.
- `engines.may_approve`: also allow if an **active** delegation
  (`starts_at ≤ now ≤ ends_at`, `revoked:false`) for that role names this user.
- Endpoints under config: `GET/POST /projects/config/delegations`,
  `DELETE /projects/config/delegations/{id}` (revoke). Guard: the delegator must
  hold the role (or be `project_director`); recorded/audited (`delegation.granted`
  / `delegation.revoked`). Enforce **no self-delegation**; the "not the executor"
  rule is largely procedural — note it, don't over-engineer.
- **Scope note:** delegation is independent of the 16→9 migration. If time-boxing,
  ship Phases 1–5 first and treat 4-D as a fast-follow.

---

## 5. Work breakdown by area

### 5-A. Backend — definitions & seed
- Rewrite `stage_definitions.json` to the §2 target (9 stages, 6 roles, 5 gates,
  `machine_version:2`, Stage 2 `auto_advance`, Stage 4 `return_to_stage` recovery,
  Stage 1 three entry docs).
- `seed.py`: version-aware reset (§3) + record applied version.
- `permissions.py`: rebuild `GATE_DOCUMENT_KINDS` for the new entry-doc gate keys
  (`loi_or_po`, `scope_boq_approved`, `site_access_confirmed`,
  `shop_drawings_present`, `raw_site_data_present`, `bom_present` → keep `bom`).
  Update `LAST_STAGE_ORDER = 9`. Decide `CLIENT_APPROVER_ROLE` fate (D2).

### 5-B. Backend — engines & service
- `engines.py`: `_advance` extraction reuse (4-A), no change to gate evaluators.
- `service.py`: auto-advance in `submit_stage` (4-A); `waive_gate` (4-B); rollback
  branch in `reject_stage` (4-C); optional delegation checks (4-D). Keep the
  Stage-5 reservation (`_reserve_stock`) and Stage-9 handover (`_build_handover`)
  wired to the **new** stage keys (`material_procurement`, `final_inspection_handover`)
  in `_run_integrations`. Handover pack must add the **G1–G5 gate records** file
  (SOP §9) — extend `_build_handover`.
- `models.py`: `GateWaive`, delegation payloads.
- `router.py`: waive endpoint + delegation endpoints; keep/retire client-portal
  guards per D2.

### 5-C. Demoted checks, checklists, snags (needs D3)
- **Demoted checks** (substrate soundness / ambient RH / channel alignment / 3mm
  reveal): **recommended** — keep them as `gate_rules` with **`blocking:false`**
  attached to the right stage's `quality_gates` (Stage 2 / Stage 8 / Stage 9). The
  engine already skips non-blocking gates, so `record_gate_result` captures the
  data without gating. Low code, data still in `gate_results` for the handover.
- **Factory Release checklist** (Stage 6, 4 sections: production / QC / packing /
  delivery): model as a required set of non-blocking `inspection`-style gates or a
  structured `checklist` on the stage instance; **all four must be complete before
  the single release approval** — enforce in `run_auto_validation` for Stage 6.
- **Snag list** (Stage 9): reuse the **Reports** model — a snag is a `report`
  (type `na`/`issue`) that must be `resolved`/`closed` before approval, unless
  there's a recorded **written client acceptance** (D2). Enforce "no open snags at
  approval" in `run_auto_validation` for Stage 9.

### 5-D. Frontend (`frontend/src/client/projects/`)
- **Un-hardcode 16** → derive the total from the stages/timeline length:
  `ProjectsPage.tsx:62,122`, `ProjectDetail.tsx:99` ("Stage X of 16"), and the
  comments in `types.ts`/both files. The timeline stepper is already backend-
  driven, so 9 stages render automatically once the seed changes.
- `StagePanel.tsx`: hide the approve/reject controls on the **auto-advance** stage
  (show "auto-advances on completion"); add a **Waive gate** control visible only
  to a `project_director` (backend enforces); render **waived** gate badges.
- Stage 6 **Factory Release checklist** UI (4 sections); Stage 9 **snag list** UI
  (reuse Reports section patterns); demoted checks as recorded fields (findings
  register / daily log) via the existing gate-result capture form.
- Update `DeliverablesSection`/handover to show the G1–G5 defence file.

### 5-E. Tests (ship with the feature — non-negotiable rule 6)
Rewrite the 3 files (they encode the 16-stage machine):
- `backend/tests/integration/test_projects.py` (920 L) — new stage keys/orders,
  6 roles, the 5 gates; a full walk 1→9; **auto-advance Stage 2 has no approver**;
  **gate waiver only by project_director**; **severe G1 rolls back to Stage 3**;
  Stage 6 checklist blocks release until complete; Stage 9 open-snag blocks handover.
- `backend/tests/integration/test_projects_documents.py` (318 L) — new
  `GATE_DOCUMENT_KINDS`, Stage-1 three-doc set, BOM-shadowing guard preserved at
  the new Stage 5.
- `backend/tests/unit/test_projects_engines.py` (150 L) — gate evaluators
  unchanged; add `_advance`/auto-advance, waiver-as-passing-result, rollback.
- Frontend: `ProjectsPage.test.tsx` (asserts "3/16 · Site survey" — update),
  plus a StagePanel test for the auto-advance/waiver affordances.
- Keep `ruff + mypy + tsc` clean; full backend + frontend suites green.

### 5-F. Docs
- Revise `docs/modules/PROJECT_MANAGEMENT.md` to describe the 9-stage machine
  (§7 stages table, §8 gates, §9 roles, §5/§6 engines incl. auto-advance/waiver/
  rollback/delegation, §12 new endpoints, §15 acceptance). Cross-link the SOP.

---

## 6. Open decisions — **ALL RESOLVED 2026-07-29** (see §10 for what was chosen)

Safe defaults are chosen; a future session should get the user's call on these,
because each changes the shape of the work:

- **D1 — Migration strategy.** *Default: reset+re-seed for local/test (pre-
  production) + a version-aware seed and `scripts/migrate_pm_v2.py` for future
  tenants.* Alternative: full in-flight remap now.
- **D2 — Client-portal fate.** v2.0 has no `client` approver stage. *Default:
  keep the `is_client_portal` machinery and repurpose it for **Stage 9 "written
  client acceptance"** of open snags (a scoped client sign-off artifact), rather
  than deleting acceptance #9's infrastructure.* Alternative: remove client-portal
  entirely (then `_approve_access`/`_document_access`/`is_client_approval` and the
  `client_contact` seed can be retired).
- **D3 — Demoted-check modelling.** *Default: non-blocking `gate_rules`
  (`blocking:false`) reusing `record_gate_result`.* Alternative: dedicated
  findings-register / daily-log / snag structures for richer UX.
- **D4 — Delegation now or fast-follow.** *Default: ship Phases 1–5, then 4-D.*
- **D5 — Acclimation.** v1.0 Stage 14 required `acclimation_complete`; the SOP is
  silent on it. *Default: fold acclimation into the Stage 8 timber-MC gate (G5)
  evidence + daily log; drop the separate entry gate.* Confirm with the client.
- **D6 — Stage 4 severe trigger.** *Default: severe reading blocks approval; the
  approver rejects and the recovery rolls back to Stage 3 (human in the loop).*
  Alternative: auto-rollback the instant a severe reading is recorded.

---

## 7. Suggested order of work (phased; commit at each boundary)

0. **Confirm D1–D6.** Then branch `pm-v2-workflow`.
1. **Seed + migration.** Rewrite `stage_definitions.json`; version-aware `seed.py`;
   `permissions.py` gate/kind maps + `LAST_STAGE_ORDER=9`; migration script.
   *Prove:* provision a fresh tenant → 9 stage_definitions, 6 roles, 5 blocking gates.
2. **Core state machine.** `_advance` extraction; auto-advance Stage 2; rollback in
   `reject_stage`; wire integrations to new stage keys. Tests green for a 1→9 walk.
3. **Gate waiver.** Model + endpoint + RBAC + engine pass-through + handover records.
4. **Checklists & snags** (Stage 6 / Stage 9) + demoted-check capture (per D3).
5. **Frontend.** Un-hardcode 16; auto-advance/waiver affordances; checklist/snag UI.
6. **Delegation** (per D4).
7. **Docs.** Revise `PROJECT_MANAGEMENT.md`; update memory (`blyns-phase10-state`).
8. Full suites green (`ruff`/`mypy`/`tsc`); live-verify a project 1→9 on the demo
   tenant; **confirm before pushing** (repo rule).

---

## 8. Acceptance criteria (definition of done — from the SOP)

- A project runs **9 stages**; **Stage 2 auto-advances** with no approver; the
  other 8 need their single role's approval.
- Exactly **6 approver roles**; nobody else can advance a stage.
- Exactly **5 blocking gates** (G1–G5). The 4 demoted checks are **captured but
  never block**.
- A **hard gate is waivable only by `project_director`**, with a recorded reason;
  the waiver is audited and appears in the handover defence file.
- A **severe G1 deviation returns the project to Stage 3** (redesign), not a
  verbal pass, not a silent hold.
- **Stage 5** reserves BOM stock via Inventory (G2) and commits budget; **Stage 9**
  builds the handover pack **including the G1–G5 gate records**.
- Stage 6 release is blocked until all four checklist sections are complete; Stage
  9 handover is blocked while a snag is open (absent written client acceptance).
- Delegation lets a named deputy approve within a defined period (if D4 in scope).
- v1.0 references to "16" are gone from UI and docs; `PROJECT_MANAGEMENT.md`
  matches the code; full test suites + `ruff`/`mypy`/`tsc` green.

---

## 9. Risks & edge cases

- **Seed re-run on an existing tenant** — the `order` unique-index collision (§3)
  is the single biggest trap. The version-aware reset must run *before* any v2
  insert. Test the upgrade path on a tenant that already has v1 seed.
- **In-flight projects** at a v1.0 stage with no v2.0 approval equivalent (e.g. a
  project mid-"delivery_planning" → collapses into `factory_release`): decide
  whether it re-enters `factory_release` as `in_progress` or is treated as past it.
- **Auto-advance loops** — guard that an auto-advance stage whose validation keeps
  failing sits in `in_progress` with an Issue Report (never spins).
- **Waiver + severe** — a director waiving a *severe* G1 overrides the rollback;
  that is deliberate (the SOP lets the director waive any hard gate) but must be
  loudly audited.
- **`_run_integrations` stage-key coupling** — it currently switches on
  `"material_procurement"` and `"client_handover"`; update to the new keys
  (`material_procurement` stays; `client_handover` → `final_inspection_handover`)
  or the reservation/handover silently stops firing.
- **Frontend "of 16"** is in copy *and* a divisor — grep for `16` before shipping.
- **Client-portal dead code** if D2 = remove — ensure `client_contact` seed and the
  guards are retired together, and acceptance-#9 tests updated, not left dangling.

---

# 10. SESSION HANDOVER — start here (written 2026-07-29)

## 10.1 Repo state

- **Branch: `pm-v2-workflow`** (branched off `quick-actions-personalization`, so it
  also carries commits `7e8378c` + `2ea47ca` — that quick-actions work is already
  pushed and is unrelated to this migration).
- **NOTHING of the PM v2 work is committed.** It is all uncommitted working-tree
  changes. The user will commit **after their own testing** — do not commit or push
  without asking.
- Uncommitted files:
  - `M backend/app/modules/projects/stage_definitions.json` (rewritten to v2)
  - `M backend/app/modules/projects/seed.py` (version-aware reset)
  - `M backend/app/modules/projects/permissions.py`
  - `M backend/app/modules/projects/service.py`
  - `?? backend/tests/integration/test_projects_seed.py` (new, 2 tests green)
  - `?? backend/tests/integration/test_projects_v2.py` (new, 3 tests green)
  - `?? docs/PROJECT_WORKFLOW_V2_SOP.md`, `?? docs/PROJECT_MANAGEMENT_V2_MIGRATION_PLAN.md`
  - (`docs/PROJECT_MANAGEMENT_LIFECYCLE.md` is untracked and **unrelated** — leave it.)

## 10.2 Decisions locked (do not re-litigate)

| # | Decision | Chosen | Status |
|---|---|---|---|
| D1 | Migration strategy | **Reset + version-aware seed**; no in-flight remap; re-provision the demo tenant | ✅ built |
| D2 | Client portal | **Remove entirely** (no `client` approver in v2.0) | ⏳ **not started** |
| D3 | Demoted checks | Non-blocking `gate_rules` (`blocking:false`) | ✅ built (seed) |
| D4 | Delegation | Ship last | ⏳ not started |
| D5 | Acclimation | Folded into the Stage 8 G5 timber-MC gate; no separate entry gate | ✅ built (seed) |
| D6 | Severe trigger | **CHANGED from the original default** → severe reading **auto-rolls back** the project the moment it is recorded (SOP: "returns the project to Stage 3", automatic). The manual reject path also rolls back via the same helper. | ✅ built |

## 10.3 DONE — verified green

**Phase 1 · Seed foundation**
- `stage_definitions.json` fully rewritten: **9 stages**, **6 approver roles**,
  **5 hard gates** (G1 `deviation_within_tolerance`, G2 `bom_present` document
  gate, G3 `concrete_rh_astm_f2170`, G4 `subfloor_flatness`, G5
  `timber_moisture_content`) + **4 demoted** to `blocking:false`
  (`substrate_soundness`, `ambient_rh_temp_log`, `fixing_channel_alignment`,
  `reveal_gap_3mm`). `machine_version: 2`. Stage 2 has `auto_advance:true` and
  `approver_role:null`. Stage 4 recovery is `{"action":"return_to_stage",
  "target":"design_package"}`. No `client` role in `approver_role_map`.
  Stage keys: `project_initiation`, `site_survey`, `design_package`,
  `measurement_verification`, `material_procurement`, `factory_release`,
  `site_readiness`, `installation`, `final_inspection_handover`.
- `seed.py`: `_applied_version()` (reads `pm_meta.state_machine`; definitions but
  no marker ⇒ v1), `_reset_definitions()` wipes the 5 **definition** collections
  only, then re-seeds and stamps `machine_version`. **This is what defuses the
  unique-`order`-index collision described in §3.** Runtime collections untouched.
- `permissions.py`: `GATE_DOCUMENT_KINDS` rebuilt for the new gate keys
  (`loi_or_po`, `scope_boq_approved`, `site_access_confirmed`,
  `shop_drawings_present`, `raw_site_data_present`, `bom_present`→`bom`);
  `LAST_STAGE_ORDER = 9`.

**Phase 2 · Core state machine** (all in `service.py`)
- `_finalize_stage(...)` — extracted shared tail of approve/auto-advance. Runs
  integrations **before** marking approved (preserves the recoverability
  guarantee), writes `stage_history` with `result:"auto_advanced"` when
  `decision_by == "system"`, advances or completes at `LAST_STAGE_ORDER`.
- `submit_stage` — new branch: if `auto_advance` or `approver_role is None`,
  validate then `_finalize_stage(decision_by="system")`, returns
  `{"auto_advanced": True, ...}`, logs `stage.auto_advanced`.
- `_rollback_to(...)` — new helper: current stage → `rejected`, project moved back
  to the target stage, target instance reopened `in_progress` + re-evaluated,
  project status forced back to `active`, logs `stage.rolled_back`.
- `record_gate_result` — a **severe** reading now opens the recovery report and,
  when the stage's recovery is `return_to_stage`, calls `_rollback_to`; response
  gains `rolled_back_to`. (Non-rollback stages keep the old `on_hold` behaviour.)
- `reject_stage` — three-way: rollback (via `_rollback_to`) / `on_hold` / reopen.
- `_run_integrations` — handover key renamed `client_handover` →
  `final_inspection_handover`; `material_procurement` unchanged.
- `_build_handover` — adds the 5th document, **"Gate Records G1–G5 (Technical
  Defence File)"**, and stamps `stage_key: "final_inspection_handover"`.

**Tests written (5, all green):**
- `test_projects_seed.py` — fresh tenant seeds v2 shape; **version bump from a
  simulated v1 tenant resets legacy definitions** (the order-collision path).
- `test_projects_v2.py` — full **1→9 walk to `completed`** (asserts 5 handover
  docs); **Stage 2 approve is 403 but submit advances**; **severe G1 (8.0mm)
  auto-returns the project to `design_package`, status stays `active`**.
- `ruff` + `mypy` clean (91 source files) after every step.

## 10.4 REMAINING — do in this order

> Run `cd backend && .venv/bin/python -m pytest tests/integration/test_projects_v2.py
> tests/integration/test_projects_seed.py -q` to confirm the base is still green
> before starting. Test harness note: `test_projects.py` exposes a **config-driven**
> helper set (`_advance`, `_machine_config`, `_passing_payload`, `_supply`,
> `_gate_result`) that adapts to the 9-stage seed automatically — reuse it.

### P1 — Rewrite the legacy backend tests (**biggest chunk; do first**)
Current: **21 failed / 26 passed** across the three legacy files. They fail because
they assert v1.0 specifics (16 stages, old stage keys, `client` approvals, old
gate→stage attachments, old document kinds) — not because the machine is broken.
- `backend/tests/integration/test_projects.py` (920 L) — bulk of the failures.
- `backend/tests/integration/test_projects_documents.py` (318 L) — 7 failures; new
  `GATE_DOCUMENT_KINDS`, Stage-1's 3-document set. **Keep the BOM-shadowing test**
  (must still target the new Stage 5 `material_procurement`).
- `backend/tests/unit/test_projects_engines.py` (150 L) — gate evaluators are
  unchanged; add coverage for `_finalize_stage` / auto-advance / `_rollback_to`.

### P2 — Remove the client portal (D2)
Exact call sites already scoped:
- `backend/app/modules/projects/engines.py:21,335–342` — delete
  `is_client_approval()` + the `CLIENT_APPROVER_ROLE` import.
- `backend/app/modules/projects/permissions.py:63` — delete `CLIENT_APPROVER_ROLE`.
- `backend/app/modules/projects/service.py:~616–620` — delete the client branch in
  `_assert_may_approve`.
- `backend/app/modules/projects/router.py:43–85,197,207,285` — collapse
  `_approve_access` → `_write` and `_document_access` → `_read`.
- `backend/app/modules/settings/seed.py:27–67` — drop the `client_contact` role and
  the `is_client_portal` flag plumbing.
- `backend/app/auth/client_auth.py:189` — drop `is_client_portal` from `/auth/me`.
- Frontend: `ClientMe`/types + any portal-conditional UI; drop the acceptance-#9
  tests. Grep `is_client_portal` to confirm nothing dangles.

### P3 — Gate waiver (SOP §3 — director-only)
Per §4-B: model a waiver as a **passing `gate_results` doc** with
`{waived:true, reason, waived_by}` so the engines need no change.
`GateWaive(reason: str)` in `models.py`; `service.waive_gate(...)`; endpoint
`POST /projects/{id}/stages/{order}/gates/{gate_key}/waive` guarded by
`engines.may_approve(db, "project_director", ...)`; log `gate.waived`; surface
waived gates in the handover defence file.

### P4 — Stage 6 checklist + Stage 9 snags
- Stage 6 `factory_release` already seeds `release_checklist` (4 sections:
  production / quality_control / packing_protection / delivery_planning) — enforce
  in `run_auto_validation` that all four are complete before release.
- Stage 9: block approval while a snag report is open, unless a recorded **written
  client acceptance** exists (since the client portal is gone, model this as a
  recorded field/report on the project_director approval).

### P5 — Frontend
- **Un-hardcode 16**: `ProjectsPage.tsx:62,122`, `ProjectDetail.tsx:99` ("Stage X
  of 16"), plus stale comments in `types.ts` / both files → derive from the
  timeline length.
- `StagePanel.tsx`: hide approve/reject on the auto-advance stage (show
  "auto-advances on completion"); add a director-only **Waive gate** control;
  render waived-gate badges; Stage 6 checklist UI; Stage 9 snag UI.
- Update `ProjectsPage.test.tsx` (asserts `"3/16 · Site survey"`).

### P6 — Delegation (D4, §4-D) — optional/last
New `approver_delegations` collection + `may_approve` extension + config endpoints.

### P7 — Docs & memory
- Revise `docs/modules/PROJECT_MANAGEMENT.md` — it **still documents the 16-stage
  machine** and now contradicts the code. Update §7 stages, §8 gates, §9 roles,
  §5/§6 engines (auto-advance, waiver, rollback), §12 endpoints, §15 acceptance.
- Update the `blyns-pm-v2-workflow` memory to "in progress" with what shipped.

## 10.5 Gotchas the next session will hit

1. **`get_stage` nests the instance** — status is `data["instance"]["status"]`, not
   `data["status"]`. (Cost a test failure this session.)
2. **`next_status` still maps severe → `on_hold`.** That is deliberate: it holds the
   stage while the reading stands. The rollback happens in `record_gate_result`
   *after* the engine runs. Don't "simplify" one without the other.
3. **`_maybe_clear_hold` must NOT re-run the decision engine** (existing comment
   explains why: the breaching reading is still the latest and would snap it back).
4. **BOM shadowing guard** (`lines.0 $exists`, newest-first) must survive into
   Stage 5 — an empty BOM *document* attached at `bom_present` would otherwise
   silently reserve nothing.
5. Legacy tests reference `acclimation_complete`, `client` approvals, and
   `factory_qc`/`packing_protection`/`delivery_planning` — all gone in v2.
6. `stage_definitions` has **unique indexes on both `key` and `order`** — any
   future stage-set change needs another `machine_version` bump + reset.
