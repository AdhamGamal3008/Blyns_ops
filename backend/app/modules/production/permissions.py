"""Production module RBAC surface + work-order vocabulary
(docs/PRODUCTION_MODULE_PLAN.md).

RBAC resource: `production` — VIEW sees the Queue/register, READ opens detail +
Stations/Quality/Dispatch, WRITE performs the floor actions. Release and station-
allocation override additionally require the `production_manager` approver
position, which the pipeline already owns (Stage 6 · Factory Release) — the
release approval itself stays a pipeline action, never hosted here (plan §2.3).
Cost is never surfaced in Production (plan D3): it lives on the project Finance tab.

`production_analytics` is a separate, management-only resource (VIEW = KPI row,
READ = + charts), mirroring the other `*_analytics` resources.
"""

from __future__ import annotations

RESOURCE = "production"
ANALYTICS_RESOURCE = "production_analytics"

# §2.2 Work Order lifecycle. A QC hold blocks only the affected WO — never the
# project or its pipeline stage (the reason the WO exists).
WO_STATUSES = [
    "queued", "released", "in_progress", "qc_pending", "qc_hold",
    "rework", "passed", "packed", "staged", "dispatched",
]
# "not-done" for the Queue default = anything still in flight. Only a dispatched
# WO has left the building; everything up to and including `staged` is live work.
DONE_STATUSES = frozenset({"dispatched"})

# §3 the Queue's default look-ahead window.
QUEUE_DEFAULT_DAYS = 14

# §2.1 The four WO phases. Their keys deliberately match the seeded v2 Stage 6 ·
# Factory Release `release_checklist` sections 1:1 — Production drives those
# sections from the WO rollup while the pipeline keeps the release approval.
WO_PHASES = ["production", "quality_control", "packing_protection", "delivery_planning"]

# §3 What a WO is blocked on, always named (never a bare boolean).
BLOCKED_BY_TYPES = ["material_shortfall", "qc_hold", "upstream_gate", "revision_conflict"]

# §4 Soft floor functions — drive the Queue default filter + audit attribution;
# NOT a hard RBAC boundary in the MVP. The hard authority is `production_manager`,
# which is the existing pipeline approver position (not a function listed here).
FUNCTIONS = ["station_operator", "qc_inspector", "warehouse", "logistics"]
