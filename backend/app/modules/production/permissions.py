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

# §2.2 the legal status moves. Each is enforced on the matching transition
# endpoint. Phase 4 opens the dispatch lane: passed → packed → staged →
# dispatched, where `dispatched` is the terminal (the WO has left the building).
ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "queued": {"released"},
    "released": {"in_progress"},
    "in_progress": {"qc_pending"},
    "qc_pending": {"passed", "qc_hold"},
    "qc_hold": {"rework"},
    "rework": {"in_progress"},
    "passed": {"packed"},
    "packed": {"staged"},
    "staged": {"dispatched"},
    "dispatched": set(),
}

# A WO "clears" a phase once its status has reached (and not regressed below) it.
# production counts a made-but-held unit (it is physically built, awaiting QC);
# quality_control counts only a passed unit. Drives the Stage-6 checklist rollup.
PHASE_CLEARED: dict[str, set[str]] = {
    "production": {"qc_pending", "qc_hold", "passed", "packed", "staged", "dispatched"},
    "quality_control": {"passed", "packed", "staged", "dispatched"},
    "packing_protection": {"packed", "staged", "dispatched"},
    "delivery_planning": {"staged", "dispatched"},
}
# Sections Production drives into the pipeline checklist (§2.3 sync rule 2). All
# four are now WO-driven: production + quality_control clear during the build,
# packing_protection at `packed`, delivery_planning at `staged` (a confirmed
# schedule, not arrival — sync rule 5). A project with ≥1 WO has Production own
# every section; a no-WO project keeps manual marking (sync rule 4).
DRIVEN_SECTIONS: tuple[str, ...] = (
    "production", "quality_control", "packing_protection", "delivery_planning",
)

# §Phase 4 — the protection spec is derived from the WO's material (its product
# category ↔ a substring match, like the station suggestion). A sane factory
# default set for a cladding / joinery shop; tenant-tunable policy is a later
# upgrade. `moisture_barrier` True stamps a barrier reference on the packing doc.
PROTECTION_SPECS: dict[str, dict] = {
    "panel":  {"type": "pallet", "protection_spec": "edge guards + corner blocks",
               "moisture_barrier": True,  "handling": ["keep flat", "max 4 high"]},
    "sheet":  {"type": "pallet", "protection_spec": "banded to pallet + slip sheet",
               "moisture_barrier": True,  "handling": ["keep flat"]},
    "timber": {"type": "bundle", "protection_spec": "shrink-wrap + battens",
               "moisture_barrier": True,  "handling": ["keep dry"]},
    "metal":  {"type": "crate",  "protection_spec": "VCI film + strapping",
               "moisture_barrier": True,  "handling": ["sharp edges"]},
    "glass":  {"type": "crate",  "protection_spec": "foam-lined crate",
               "moisture_barrier": False, "handling": ["fragile", "keep upright",
                                                        "two-person lift"]},
}
DEFAULT_PROTECTION: dict = {
    "type": "carton", "protection_spec": "boxed + labelled",
    "moisture_barrier": False, "handling": [],
}

# §Phase 4 — the vehicle is suggested from the staged load. The catalogue carries
# no product weight, so the unit count is the load proxy; anything over the top
# band takes the heavy vehicle. Ascending by unit ceiling.
VEHICLE_BANDS: tuple[tuple[float, str], ...] = (
    (20, "van"),
    (80, "3.5t truck"),
    (200, "7.5t truck"),
)
HEAVY_VEHICLE = "articulated lorry"

# §3 A WO still loads its production station while it has building work left —
# from queued through rework. Once it reaches QC (qc_pending+) production is done
# and it no longer counts against the station's capacity.
ACTIVE_AT_STATION: frozenset[str] = frozenset(
    {"queued", "released", "in_progress", "rework"}
)

# Pipeline stage keys Production reads/mirrors (never writes a gate).
MATERIAL_PROCUREMENT_KEY = "material_procurement"  # Stage 5 — must be approved to release
FACTORY_RELEASE_KEY = "factory_release"            # Stage 6 — the checklist Production drives

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
