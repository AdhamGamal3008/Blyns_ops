"""Project Management RBAC surface + state-machine vocabulary
(docs/modules/PROJECT_MANAGEMENT.md).

RBAC resource: `projects` — READ for GET, WRITE for mutations. approve/reject
additionally require membership of the stage's `approver_role` (§9).
"""

from __future__ import annotations

RESOURCE = "projects"

# §4 stage lifecycle.
STAGE_STATES = [
    "pending", "waiting", "blocked", "in_progress", "validation",
    "pending_approval", "approved", "rejected", "on_hold",
]
# A stage sitting in one of these is not workable until something external changes.
STALLED_STATES = frozenset({"waiting", "blocked", "on_hold"})
TERMINAL_STAGE_STATE = "approved"

# §3.6 approval lifecycle.
APPROVAL_STATES = ["draft", "auto_validation", "manager_review", "approved", "rejected"]

# §2 gate types.
GATE_TYPES = ["document", "dependency", "measurement", "inspection", "budget", "availability"]

# §3.8 typed exception artifacts (the seeded report_types registry mirrors these).
REPORT_TYPES = ["missing_information", "issue", "change", "ncr", "capa", "rfi", "qa", "na"]
OPEN_REPORT_STATUSES = ["open", "in_progress"]

# v2.0 SOP §9: at Stage 9 an open snag (a `na` report) blocks the handover unless
# a written client acceptance is recorded. Kept distinct from `issue` so a
# transient automated-validation report never counts as an outstanding snag.
SNAG_REPORT_TYPES = ["na"]

PROJECT_STATUSES = ["active", "on_hold", "completed", "archived", "cancelled"]

# §3.7 deliverable kinds.
DELIVERABLE_KINDS = ["shop_drawing", "bom", "scan", "photo", "report", "certificate"]

# §4: a stage's document gate IS the document's identity — the gate already says
# what is required, so evidence attached at a gate never asks for a kind. This
# maps each seeded document gate to the kind it stores as; anything unmapped
# stores as a generic `report`. `bom_present` must stay `bom` — Stage 5 finds the
# BOM by kind to reserve stock through Inventory (v2.0 workflow).
GATE_DOCUMENT_KINDS = {
    # Stage 1 · Project Initiation — the 3 required entry documents
    "loi_or_po": "certificate",
    "scope_boq_approved": "report",
    "site_access_confirmed": "report",
    # Stage 4 · Measurement Verification
    "shop_drawings_present": "shop_drawing",
    "raw_site_data_present": "scan",
    # Stage 5 · Material Procurement (G2)
    "bom_present": "bom",
}
DEFAULT_GATE_DOCUMENT_KIND = "report"

# §3.9 job-cost types.
COST_TYPES = ["labor", "material", "subcontractor", "machine"]

FIRST_STAGE_ORDER = 1
LAST_STAGE_ORDER = 9  # v2.0 workflow: 9-stage machine (was 16)

# v2.0 Stage 9 · Final Inspection & Client Handover — the terminal stage whose
# automated validation enforces snag closure (SOP §9).
HANDOVER_STAGE_KEY = "final_inspection_handover"

# The recovery `on` → report type the engine raises when a stage is rejected
# (§5.5, acceptance #5). A stage's own recovery block overrides this.
DEFAULT_REJECT_REPORT = "change"
