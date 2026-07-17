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

PROJECT_STATUSES = ["active", "on_hold", "completed", "archived", "cancelled"]

# §3.7 deliverable kinds.
DELIVERABLE_KINDS = ["shop_drawing", "bom", "scan", "photo", "report", "certificate"]

# §3.9 job-cost types.
COST_TYPES = ["labor", "material", "subcontractor", "machine"]

FIRST_STAGE_ORDER = 1
LAST_STAGE_ORDER = 16

# §9: `client` is a position resolved through the approver map like any other,
# but it is only ever exercised through scoped client-portal access — never by
# granting a client contact full `projects` access (acceptance #9).
CLIENT_APPROVER_ROLE = "client"

# The recovery `on` → report type the engine raises when a stage is rejected
# (§5.5, acceptance #5). A stage's own recovery block overrides this.
DEFAULT_REJECT_REPORT = "change"
