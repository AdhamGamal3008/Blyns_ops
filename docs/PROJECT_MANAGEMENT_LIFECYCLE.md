# Project Management — Full Lifecycle, Stages, Fields & Approvals

> **Review reference, not a spec.** Extracted from the actual source of truth so
> you can review every stage, its deliverables, and who approves what:
> - `backend/app/modules/projects/stage_definitions.json` — the 16 seeded stages, gates, approver map, report types
> - `backend/app/modules/projects/permissions.py` — the state/approval/gate/report/cost vocabularies + gate→document mapping
> - `docs/modules/PROJECT_MANAGEMENT.md` — the module spec (data models, engines, acceptance)
>
> Where the seed JSON and the prose spec disagree on wording, **the JSON wins**
> (it is what the system runs). Generated 2026-07-26.

---

## 1. What this module is

Each project is run as a **16-stage stage-gate state machine** for a wall
cladding / flooring / custom-furniture business. Projects always move **1 → 16 in
order**; a stage cannot be skipped, and **a stage cannot be left until three
things are all true**:

1. every **blocking entry gate** and **quality gate** on the stage passes,
2. the **Automated Decision Engine** validation passes, and
3. an **approver holding that stage's role approves** it.

Any one of those failing keeps the project parked in the stage. PM owns the
orchestration (stages, gates, approvals, deliverables, reports, job costs) and
**delegates domain data** to CRM (account link), Inventory (stock reserve/
consume), and Finance (commitments, job costs, invoicing).

Two engines drive every stage:

- **Automated Decision Engine** (per task): initiation → document check →
  dependency check → automated validation. Pass hands off to approval; fail
  raises a typed report and re-validates. Deterministic and idempotent (safe to
  re-run).
- **Universal Approval Engine** (per stage): `draft → auto_validation →
  manager_review → approved | rejected`. Reject generates a report, assigns an
  owner, increments `recovery_loops`, and reopens the stage.

---

## 2. Vocabulary (the legends you'll need while reviewing)

**Stage status lifecycle** (`StageInstance.status`):

| Status | Meaning |
|---|---|
| `pending` | project has not yet reached this stage |
| `in_progress` | active work; deliverables being prepared |
| `waiting` | **stalled** — a required document is missing (owner notified) |
| `blocked` | **stalled** — a preceding stage/task is incomplete (blocker recorded) |
| `validation` | auto-checks running |
| `pending_approval` | auto-checks passed; awaiting the human approver |
| `approved` | **terminal-per-stage** — advances the project to the next stage |
| `rejected` | approver rejected → recovery loop, stage reopens |
| `on_hold` | **stalled** — a *severe* quality-gate failure suspends the project |

Stalled = `waiting` / `blocked` / `on_hold` (not workable until something external changes). Advancing terminal = `approved`.

**Approval lifecycle** (`Approval.state`): `draft → auto_validation → manager_review → approved | rejected`.

**Gate types**: `document` · `dependency` · `measurement` (physical test vs. threshold) · `inspection` (checklist) · `budget` · `availability`. All seeded gates are **blocking**.

**Report types** (typed exception artifacts): `missing_information` · `issue` · `change` · `ncr` · `capa` · `rfi` · `qa` · `na`. Default report on a plain rejection = `change`.

**Deliverable kinds** (versioned, immutable audit trail — no version is ever overwritten): `shop_drawing` · `bom` · `scan` · `photo` · `report` · `certificate`.

**Job-cost types** (feed Finance): `labor` · `material` · `subcontractor` · `machine`.

**Project status**: `active` · `on_hold` · `completed` · `archived` · `cancelled`.

---

## 3. Who approves what (read this before the stage table)

Approver names below (`project_director`, `engineering_manager`, `client`, …) are
**positions, not people**. They resolve to real users through the editable
**Approver map** in Settings.

**Out of the box (seed default) every internal position resolves to the `owner`
(Owner) role, and `client` resolves to the `client_contact` portal role.** So on
a fresh tenant the Owner approves every internal stage and the client contact
signs the client stages — until an admin reassigns positions in
**Settings → Approvers**.

Rules that always hold:

- To **approve/reject** a stage a user needs `projects` **WRITE** *and* membership
  of that stage's `approver_role`. To **submit** a stage needs `projects` WRITE only.
- **Client** approvals (stages 4, 5, 15, 16, and 6 conditionally) are only ever
  performed through **scoped client-portal access** (a `client_contact` with
  VIEW + `is_client_portal`), **never** by giving a client full module access.
- `approver_role` = the **primary** sign-off. `co_approver_roles` = additional
  required co-signers. `conditional_approvers` = only required when a condition
  is met (e.g. finance when over budget).

**Default approver map (seed):**

| Position | Resolves to (default) |
|---|---|
| project_director, design_manager, engineering_manager, engineering, procurement, procurement_manager, production_supervisor, qc_manager, qc, warehouse_manager, logistics, site_engineer, project_manager, site_supervisor, finance | `owner` |
| client | `client_contact` (portal, approval-only) |

---

## 4. The 16 stages at a glance

| # | Stage | Primary approver | Co / conditional | Blocking gates (entry ‖ quality) | Module effects |
|---|---|---|---|---|---|
| 1 | Lead Conversion & Project Creation | project_director | — | 5 documents | CRM: link account |
| 2 | Requirements Collection | design_manager | — | 4 documents | — |
| 3 | Site Survey | engineering_manager | — | dep: stage 2 ‖ substrate_soundness | — |
| 4 | Concept Design | design_manager | **co: client** | dep: stage 3 | — |
| 5 | Material Selection | procurement | **co: client** | dep: stage 4 | Inventory: check availability |
| 6 | Shop Drawings | engineering | *cond: client* | dep: stages 5 & 4 | — |
| 7 | Site Measurement Verification | engineering | — | 2 documents ‖ deviation_within_tolerance | — |
| 8 | Material Procurement | procurement_manager | *cond: finance (over budget)* | dep: stage 7 + BOM document | **Inventory: reserve stock · Finance: record commitment** |
| 9 | Factory Production | production_supervisor | — | dep: stage 8 | **Inventory: consume stock · Finance: post job costs** |
| 10 | Factory Quality Control | qc_manager | — | dep: stage 9 | — |
| 11 | Packing & Protection | warehouse_manager | — | dep: stage 10 | — |
| 12 | Delivery Planning | logistics | — | dep: stage 11 | — |
| 13 | Site Readiness Inspection | project_manager | **co: site_engineer** | temporal ‖ subfloor_flatness, concrete_rh_astm_f2170, substrate_soundness | — |
| 14 | Installation | site_supervisor | — | dep: stage 13 + acclimation ‖ timber MC, ambient RH/temp, fixing_channel_alignment, reveal_gap_3mm | — |
| 15 | Final Quality Inspection | project_manager | **co: qc, client** | dep: stage 14 | — |
| 16 | Client Handover | project_director | **co: client** | dep: stage 15 | **Finance: issue final invoice** |

---

## 5. Stage-by-stage detail

Each block lists: **Entry requirements** (what must exist to work the stage),
**Produces** (deliverables/outputs), **Automated tasks**, **Quality gates**
(physical, blocking), **Approval**, **Integrations**, and **Recovery** (what
happens on failure).

### Stage 1 — Lead Conversion & Project Creation  `lead_conversion`
- **Entry requirements** (all blocking documents): Approved **Quotation** (certificate) · Signed **Contract** (certificate) · **Client info** (report) · **Scope** (report) · **Initial drawings** (shop_drawing).
- **Produces:** the Project record + code, the folder hierarchy, the timeline & milestones, an assigned PM; a link to the CRM account.
- **Automated tasks:** create_project_record · build_folder_hierarchy · generate_timeline_milestones · assign_pm.
- **Quality gates:** none.
- **Approval:** primary **project_director**.
- **Integrations:** CRM → link account.
- **Recovery:** missing docs → **hold & notify Sales**, stage `waiting` (blocks scheduling until supplied).

### Stage 2 — Requirements Collection  `requirements_collection`
- **Entry requirements** (documents): **Architectural drawings** (shop_drawing) · **Design package** (shop_drawing) · **Material specs** (report) · **Client requirements** (report).
- **Produces:** a requirements checklist; a Missing-Information Report if anything is short.
- **Automated tasks:** verify_document_completeness · detect_missing_or_conflicting_drawings · generate_requirements_checklist.
- **Quality gates:** none.
- **Approval:** primary **design_manager**.
- **Recovery:** missing info → generate **Missing Information Report**, stage `waiting`; request docs and repeat.

### Stage 3 — Site Survey  `site_survey`
- **Entry requirements:** dependency — stage 2 approved (`project_approved`).
- **Produces:** a survey report; field measurements, scans, and photos (scan/photo deliverables).
- **Automated tasks:** schedule_survey · assign_surveyor · collect_measurements_scans_photos · generate_survey_report.
- **Quality gates:** **substrate_soundness** (inspection checklist — structurally sound, no delamination, clean/dry, aligned/plumb).
- **Approval:** primary **engineering_manager**.
- **Recovery:** discrepancy → **flag out-of-tolerance, return to Concept Design** (stage `rejected`, target stage 4).

### Stage 4 — Concept Design  `concept_design`
- **Entry requirements:** dependency — stage 3 completed.
- **Produces:** a versioned design (with revision tracking), a material & budget estimate.
- **Automated tasks:** generate_design_version · track_revisions · compare_against_scope · estimate_material_and_budget.
- **Quality gates:** none.
- **Approval:** primary **design_manager** · **co-approver: client**.
- **Recovery:** client rejection → **record comments, generate V2, loop** (stage `rejected`, target stage 4).

### Stage 5 — Material Selection  `material_selection`
- **Entry requirements:** dependency — stage 4 approved (`concept_approved`).
- **Produces:** an approved material selection/spec; suggested alternatives where needed.
- **Automated tasks:** validate_compatibility · check_availability_leadtime_warranty_budget · suggest_alternatives.
- **Quality gates:** none.
- **Approval:** primary **procurement** · **co-approver: client**.
- **Integrations:** Inventory → check availability.
- **Recovery:** unavailable material → **search approved alternatives**, stage `in_progress`; request approval and update specs.

### Stage 6 — Shop Drawings  `shop_drawings`  *(physical phase: Shop Drawing & Submittal)*
- **Entry requirements:** dependencies — stage 5 (`materials_approved`) **and** stage 4 (`concept_approved`).
- **Produces:** production shop drawings **and the BOM** (shop_drawing + bom deliverables), clash & tolerance checks, version control.
- **Automated tasks:** generate_production_drawings_and_bom · detect_clashes · check_tolerances · version_control.
- **Quality gates:** none.
- **Approval:** primary **engineering** · **conditional: client** (when `client_review_required`).
- **Recovery:** rejection → **highlight issues, route to Engineering, new revision** (stage `rejected`, target stage 6).

### Stage 7 — Site Measurement Verification  `site_measurement_verification`  *(physical phase: Site Measurement Audit)*
- **Entry requirements** (documents): **Shop drawings** (shop_drawing) · **Raw site data** (scan).
- **Produces:** updated dimensions & recalculated quantities, a deviation record.
- **Automated tasks:** import_laser_scans · compare_against_drawings · detect_deviations · update_dimensions · recalculate_quantities.
- **Quality gates:** **deviation_within_tolerance** (measurement) — max **3 mm**; **severe ≥ 6 mm → `on_hold` and halts fabrication**.
- **Approval:** primary **engineering**.
- **Recovery:** severe deviation → **halt fabrication, update drawings, repeat verification** (stage `on_hold`).

### Stage 8 — Material Procurement  `material_procurement`  *(physical phase: Material Procurement)*
- **Entry requirements:** dependency — stage 7 verified (`shop_drawings_verified`) **and** the **BOM** document present (`bom_present`, kind `bom`).
- **Produces:** purchase orders; **reserved stock**; a recorded **budget commitment**; lead-time / delivery tracking.
- **Automated tasks:** generate_purchase_orders · reserve_inventory · track_lead_times · monitor_deliveries · predict_schedule_delays.
- **Quality gates:** none.
- **Approval:** primary **procurement_manager** · **conditional: finance** (when `over_budget`).
- **Integrations:** **Inventory → reserve stock · Finance → record commitment.** *(Implementation: the reservation is an Inventory `issue` tagged `ref_module="projects"` that commits `qty × cost_price` to `budget.committed`; integrations run while the stage is still `pending_approval` so a failed reservation is recoverable.)*
- **Recovery:** supplier delay → **split procurement, adjust schedule, notify PM** (stage `in_progress`).
- ⚠️ **Why the BOM kind matters:** stage 8 finds the BOM *by kind* to reserve stock. A BOM document attached at `bom_present` must keep kind `bom` (a BOM with no line items can silently shadow the real one — see the build-state notes).

### Stage 9 — Factory Production  `factory_production`  *(physical phase: Shop Fabrication & Assembly)*
- **Entry requirements:** dependency — stage 8 materials received.
- **Produces:** work orders, machine/labor allocation, progress & KPI tracking, captured labor hours; **job costs posted to Finance**.
- **Automated tasks:** create_work_orders · allocate_machines_and_labor · track_progress · record_labor_hours · monitor_kpis.
- **Quality gates:** none.
- **Approval:** primary **production_supervisor**.
- **Integrations:** **Inventory → consume stock · Finance → post job costs.** *(A `material` job cost draws down the stage-8 commitment to zero as the actual is booked, so a reserved-then-consumed line counts once; `labor` posts as actual.)*
- **Recovery:** machine failure → **reschedule, reallocate machines, notify PM** (stage `in_progress`).

### Stage 10 — Factory Quality Control  `factory_qc`
- **Entry requirements:** dependency — stage 9 fabrication completed.
- **Produces:** QC checklists, dimension/surface/finish verification, packaging approval, defect data; an **NCR** on failure.
- **Automated tasks:** generate_checklists · verify_dimensions_surfaces_finishes · approve_packaging · capture_defect_data.
- **Quality gates:** none.
- **Approval:** primary **qc_manager**.
- **Recovery:** QC failure → **generate NCR, assign rework, repeat QC** (stage `rejected`, target stage 10).

### Stage 11 — Packing & Protection  `packing_protection`
- **Entry requirements:** dependency — stage 10 finished goods approved.
- **Produces:** packing type decision, labels + loading sequence, packaged-item tracking.
- **Automated tasks:** determine_packing_type · generate_labels_and_loading_sequence · track_packaged_items.
- **Quality gates:** none.
- **Approval:** primary **warehouse_manager**.
- **Recovery:** damage → **repackage + secondary QC** (stage `in_progress`).

### Stage 12 — Delivery Planning  `delivery_planning`
- **Entry requirements:** dependency — stage 11 packaged goods ready.
- **Produces:** an optimized delivery schedule, vehicle assignment, routing, and delivery documents; the **delivery date** (a calendar event).
- **Automated tasks:** optimize_delivery_schedule · assign_vehicle · generate_routing · generate_delivery_documents.
- **Quality gates:** none.
- **Approval:** primary **logistics**.
- **Recovery:** vehicle unavailable → **replacement, update ETA, notify client** (stage `in_progress`).

### Stage 13 — Site Readiness Inspection  `site_readiness`  *(physical phase: Site Prep & Moisture Testing)*
- **Entry requirements:** temporal — approaching delivery date.
- **Produces:** a readiness inspection; a punch list on failure.
- **Automated tasks:** check_civil_electrical_hvac_painting · verify_access_storage_safety.
- **Quality gates (all blocking):** **subfloor_flatness** (≤ 1/4″ over 10 ft) · **concrete_rh_astm_f2170** (in-situ RH ≤ 75% default, configurable per tenant/manufacturer) · **substrate_soundness** (inspection).
- **Approval:** primary **project_manager** · **co-approver: site_engineer**.
- **Recovery:** site not ready → **punch list, notify contractor, reschedule** (stage `on_hold`).

### Stage 14 — Installation  `installation`  *(physical phase: Cladding & Panel Assembly; + Core Material Acclimation window)*
- **Entry requirements:** dependencies — stage 13 cleared (`site_readiness_cleared`) **and** `acclimation_complete`.
- **Produces:** crew assignment, install & alignment tracking, daily reports + photos, issue tracking (RFIs/Issue Reports).
- **Automated tasks:** assign_crews · track_installation_and_alignment · compile_daily_reports_and_photos · track_issues.
- **Quality gates (all blocking):** **timber_moisture_content** (6–9%) · **ambient_rh_temp_log** (site-defined window, continuous logging) · **fixing_channel_alignment** (inspection: level/plumb/clip spacing/anchorage) · **reveal_gap_3mm** (3 mm ± 1).
- **Approval:** primary **site_supervisor**.
- **Recovery:** installation issue → **pause the zone, generate Issue Report, mandate Engineering review** (stage `on_hold`).
- **Acclimation note:** the acclimation period sits between delivery (stage 12) and installation (stage 14), enforced as the two moisture/RH gates above **plus** a dated `acclimation` calendar event so the window is visible.

### Stage 15 — Final Quality Inspection  `final_qc`
- **Entry requirements:** dependency — stage 14 installation completed.
- **Produces:** the **QA report**; a **CAPA** on failure.
- **Automated tasks:** generate_checklist · compare_to_drawings_via_photos · validate_tolerances · generate_qa_report.
- **Quality gates:** none.
- **Approval:** primary **project_manager** · **co-approvers: qc, client**.
- **Recovery:** inspection failure → **generate CAPA, assign rework, repeat inspection** (stage `rejected`, target stage 15).

### Stage 16 — Client Handover  `client_handover`  *(terminal)*
- **Entry requirements:** dependency — stage 15 QA report approved.
- **Produces (the handover pack):** Completion Certificate · Warranty · Manuals · As-built drawings · **Final Invoice** · archived documents.
- **Automated tasks:** generate_completion_certificate · generate_warranty · generate_manuals · generate_as_built_drawings · generate_final_invoice · archive_documents.
- **Quality gates:** none.
- **Approval:** primary **project_director** · **co-approver: client**.
- **Integrations:** **Finance → issue final invoice.**
- **Recovery:** none — **close the project** (stage `approved`, project `completed`; end of the state machine).

---

## 6. Physical-condition gates (thresholds you can tune per tenant)

All are **blocking**; thresholds are seeded defaults, editable in Settings.

| Gate | On stage(s) | Type | Default threshold | On fail |
|---|---|---|---|---|
| deviation_within_tolerance | 7 | measurement | ≤ 3 mm (severe ≥ 6 mm) | halt fabrication → `on_hold` |
| substrate_soundness | 3, 13 | inspection | pass/fail checklist | return to Design / punch list |
| subfloor_flatness | 13 | measurement | ≤ 1/4″ over 10 ft | punch list, reschedule |
| concrete_rh_astm_f2170 | 13 | measurement | RH ≤ 75% (ASTM F2170, configurable) | `on_hold`, block adhesive install |
| timber_moisture_content | 14 | measurement | MC 6–9% | lock installation, log, notify |
| ambient_rh_temp_log | 14 | measurement | site-defined RH/temp window | continue acclimation |
| fixing_channel_alignment | 14 | inspection | level/plumb/clip-spacing/anchorage | pause zone, Issue Report |
| reveal_gap_3mm | 14 | measurement | 3 mm ± 1 | rework, secondary check |

**7 foundational physical phases** (Part 1) overlay onto the workflow stages via `phase_ref`:

| Physical phase | Realized on stage |
|---|---|
| Shop Drawing & Submittal | 6 Shop Drawings |
| Site Measurement Audit | 7 Site Measurement Verification |
| Material Procurement | 8 Material Procurement |
| Shop Fabrication & Assembly | 9 Factory Production |
| Core Material Acclimation | 14 Installation (pre-install gate window) |
| Site Prep & Moisture Testing | 13 Site Readiness |
| Cladding & Panel Assembly | 14 Installation |

---

## 7. How a single stage actually advances (the loop applied to every stage)

1. Project reaches the stage → status **`in_progress`**.
2. Team supplies the **entry documents / evidence** (attached at each document gate — the gate itself names what it stores, e.g. `bom_present` → a `bom`). A missing required doc → **`waiting`** (owner notified); an incomplete predecessor → **`blocked`** (blocker recorded).
3. Log any **measurement/inspection gate results** (`.../gates/{gateKey}/result`).
4. **Submit** (`POST .../stages/{order}/submit`, needs `projects` WRITE) → **auto-validation**: constraints, budget, compliance, and *all blocking gates passed*. Fail → typed **Issue/Change report** raised, stage back to `in_progress`.
5. Pass → **`pending_approval`**, routed to the stage's **approver_role** (+ any co/conditional approvers).
6. The approver (**`projects` WRITE + that approver role**) **approves** → stage **`approved`**, next stage becomes `in_progress`, activity emitted. Or **rejects (+comment)** → typed report generated, owner assigned, **`recovery_loops` ++**, stage reopens.
7. A **severe** quality-gate failure sends the stage to **`on_hold`** until the recovery report is resolved.

**Endpoints** (`/api/v1/projects/{id}/...`): `stages`, `stages/{order}`, `stages/{order}/submit|approve|reject`, `stages/{order}/gates/{gateKey}/result`, `stages/{order}/tasks/{taskKey}/run`, `deliverables` (+ `/revisions`), `reports` (+ PATCH to progress/resolve), `job-costs`, and config: `config/stages|gates|approver-roles`.

---

## 8. Typed reports (what gets raised, and where)

| Report | Raised at | Trigger |
|---|---|---|
| `missing_information` | stage 2 | required docs/info short |
| `issue` | stages 7, 14, any | site deviation, install issue |
| `change` | any | **default on any plain rejection** (change order) |
| `ncr` | stage 10 | factory QC failure |
| `capa` | stage 15 | final inspection failure |
| `rfi` | stage 14 | request for information during install |
| `qa` | stage 15 | quality-assurance output |

Every rejection generates the correct typed report, assigns an owner, increments `recovery_loops`, and reopens the stage. Reports track `open → in_progress → resolved → closed`.

---

## 9. Cross-module effects (where PM touches CRM / Inventory / Finance)

| Stage | Module | Effect |
|---|---|---|
| 1 | CRM | link the project to a CRM account |
| 5 | Inventory | check material availability |
| 8 | Inventory | **reserve stock** (issue tagged `ref_module="projects"`) |
| 8 | Finance | **record the budget commitment** (`qty × cost_price` → `budget.committed`) |
| 9 | Inventory | **consume stock** |
| 9 | Finance | **post job costs** (labor actuals; material draws down the stage-8 commitment) |
| 16 | Finance | **issue the final invoice** |

Integrations at stages 8/9 run while the stage is still `pending_approval`, so a failed reservation is recoverable rather than half-committed.

---

## 10. Calendar & activity footprint

- **Calendar events** emitted: `milestone`, `stage_due`, `delivery` (stage 12), `acclimation` (pre-14 window), `gate_due`.
- **Activity log** events: `project.created`, `stage.entered`, `stage.submitted`, `stage.approved`, `stage.rejected`, `gate.passed`, `gate.failed`, `report.opened`, `report.resolved`, `deliverable.revised`.

---

## 11. Key data records (fields to expect)

- **Project:** `code`, `name`, `crm_account_id`, `scope`, `current_stage_order/key`, `status`, `pm_id`, `team_ids`, `milestone_schedule[]`, `budget{planned, committed, actual, currency}`, `stage_history[]`.
- **StageInstance:** `project_id`, `stage_order/key`, `status`, `entered_at`, `gate_results[]`, `task_results[]`, `approval_id`, `recovery_loops`, `blocking_reason`.
- **Approval:** `stage_instance_id`, `approver_role`, `assigned_to`, `state`, `auto_validation{passed, checks[]}`, `decision{by, at, comment}`, `change_report_id`.
- **Deliverable:** `kind`, `title`, `current_version`, `versions[]` (each `v`, `file_ref`, `author_id`, `at`, `note`), `immutable_audit[]` — **every revision kept, nothing overwritten or deleted**.
- **Report:** `type`, `title`, `details`, `owner_id`, `status`.
- **JobCost:** `stage_key`, `cost_type`, `hours`, `quantity`, `unit_cost`, `amount`, `posted_to_finance_ref`.

---

*End of reference. To change any stage, gate threshold, or approver assignment, edit
`stage_definitions.json` (re-seed is idempotent and never overwrites tenant-customized
copies) or use the `config/*` endpoints / Settings → Approvers.*
