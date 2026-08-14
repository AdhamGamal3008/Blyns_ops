"""
Projects module — tenant seed.

Called by the provisioning engine when a company is onboarded (and again if the
`projects` module is enabled later). MUST be idempotent and safe to re-run:

  * Definition data (stage definitions, gate rules, phases, report types,
    approver map) is inserted with $setOnInsert, so a re-run never clobbers a
    tenant's later customizations — it only fills in anything missing.
  * Indexes use create_index, which is a no-op when the index already exists.

The seed content lives in stage_definitions.json next to this file so it can be
edited without touching code.
"""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ASCENDING, DESCENDING
from pymongo.errors import OperationFailure

_SEED_FILE = Path(__file__).with_name("stage_definitions.json")


def _load_seed() -> dict:
    with _SEED_FILE.open(encoding="utf-8") as fh:
        return json.load(fh)


def _concurrent_variant(seq_defs: list[dict]) -> list[dict]:
    """Derive the 'concurrent' template from the 'sequential' one
    (docs/CONCURRENT_WORKFLOW_PLAN.md): the same stages, but every stage between the
    first and the last depends only on the first stage, and the last (Handover)
    depends on all of them — so 2..N-1 run in parallel and N waits for every one.
    Document/quality gates, approvers and checklists are preserved; only dependency
    entry-gates are rebuilt."""
    by_order = {int(d["order"]): d for d in seq_defs}
    orders = sorted(by_order)
    first, last = orders[0], orders[-1]
    first_key = by_order[first]["key"]
    middle = [o for o in orders if first < o < last]

    out: list[dict] = []
    for o in orders:
        d = deepcopy(by_order[o])
        d["workflow_type"] = "concurrent"
        # keep non-dependency gates (documents, phase refs); rebuild dependencies
        gates = [g for g in (d.get("entry_gates") or []) if g.get("type") != "dependency"]
        if o == last:
            for mo in middle:
                mk = by_order[mo]["key"]
                gates.append({"key": f"{mk}_done", "type": "dependency",
                              "depends_on": mk, "blocking": True})
        elif o != first:
            gates.append({"key": f"{first_key}_started", "type": "dependency",
                          "depends_on": first_key, "blocking": True})
        d["entry_gates"] = gates
        out.append(d)
    return out


async def _drop_legacy_index(collection, name: str) -> None:
    """Drop a pre-workflow_type single-field unique index if present (no-op else)."""
    try:
        await collection.drop_index(name)
    except OperationFailure:
        pass


async def _upsert_by(collection, docs: list[dict], key_field: str) -> None:
    """Insert each doc if a doc with the same key_field does not already exist.

    $setOnInsert means existing (possibly tenant-edited) docs are left untouched.
    """
    for doc in docs:
        await collection.update_one(
            {key_field: doc[key_field]},
            {"$setOnInsert": doc},
            upsert=True,
        )


async def _upsert_stage_defs(collection, docs: list[dict]) -> None:
    """Stage defs are unique per (workflow_type, key); upsert on both so the two
    templates coexist and a re-run never clobbers a tenant's edits."""
    for doc in docs:
        await collection.update_one(
            {"workflow_type": doc["workflow_type"], "key": doc["key"]},
            {"$setOnInsert": doc},
            upsert=True,
        )


async def _build_indexes(tenant_db: AsyncIOMotorDatabase) -> None:
    # Definition/config collections. Stage definitions are scoped by workflow_type
    # (docs/CONCURRENT_WORKFLOW_PLAN.md), so key/order are unique *per type* — drop
    # the legacy single-field unique indexes and make them compound.
    await _drop_legacy_index(tenant_db.stage_definitions, "key_1")
    await _drop_legacy_index(tenant_db.stage_definitions, "order_1")
    await tenant_db.stage_definitions.create_index(
        [("workflow_type", ASCENDING), ("key", ASCENDING)], unique=True
    )
    await tenant_db.stage_definitions.create_index(
        [("workflow_type", ASCENDING), ("order", ASCENDING)], unique=True
    )
    await tenant_db.gate_rules.create_index("key", unique=True)
    await tenant_db.foundational_phases.create_index("key", unique=True)
    await tenant_db.report_types.create_index("type", unique=True)
    await tenant_db.approver_role_map.create_index("approver_role", unique=True)
    await tenant_db.approver_delegations.create_index("approver_role")

    # Runtime collections (per PROJECT_MANAGEMENT.md section 13)
    await tenant_db.projects.create_index("status")
    await tenant_db.projects.create_index("current_stage_order")
    await tenant_db.projects.create_index("pm_id")
    await tenant_db.projects.create_index("crm_account_id")
    await tenant_db.projects.create_index("code", unique=True)

    await tenant_db.stage_instances.create_index(
        [("project_id", ASCENDING), ("stage_order", ASCENDING)], unique=True
    )
    await tenant_db.stage_instances.create_index("status")

    await tenant_db.pm_tasks.create_index("stage_instance_id")
    await tenant_db.pm_tasks.create_index("status")

    await tenant_db.gate_results.create_index("stage_instance_id")
    await tenant_db.gate_results.create_index("gate_key")

    await tenant_db.approvals.create_index("stage_instance_id")
    await tenant_db.approvals.create_index("state")

    await tenant_db.deliverables.create_index(
        [("project_id", ASCENDING), ("kind", ASCENDING)]
    )
    await tenant_db.reports.create_index(
        [("project_id", ASCENDING), ("type", ASCENDING), ("status", ASCENDING)]
    )
    await tenant_db.job_costs.create_index("project_id")

    # Activity feed (shared) — ensure the fields this module queries are indexed
    await tenant_db.activity_log.create_index([("occurred_at", DESCENDING)])
    await tenant_db.activity_log.create_index("module")


_DEFINITION_COLLECTIONS = (
    "stage_definitions", "gate_rules", "report_types",
    "approver_role_map", "foundational_phases",
)


async def _applied_version(tenant_db: AsyncIOMotorDatabase) -> int:
    """The workflow machine_version this tenant is on. A tenant seeded before
    pm_meta existed has definitions but no marker → treat it as version 1."""
    meta = await tenant_db.pm_meta.find_one({"_id": "state_machine"})
    if meta is not None:
        return int(meta.get("machine_version", 1))
    if await tenant_db.stage_definitions.count_documents({}) > 0:
        return 1
    return 0


async def _reset_definitions(tenant_db: AsyncIOMotorDatabase) -> None:
    """Wipe the DEFINITION collections so a machine-version bump doesn't leave the
    superseded machine's stages/roles/gates behind (a plain $setOnInsert re-seed
    can neither update nor remove them, and the unique `order` index would collide
    on insert). Runtime collections — projects, stage_instances, gate_results,
    approvals, … — are never touched here (docs/PROJECT_MANAGEMENT_V2_MIGRATION_PLAN.md §3).
    NOTE: in-flight projects on the old numbering are NOT remapped by this reset;
    the migration strategy (D1) is reset + re-provision, so run this only where
    losing the old definitions is intended."""
    for coll in _DEFINITION_COLLECTIONS:
        await tenant_db[coll].delete_many({})


async def seed(tenant_db: AsyncIOMotorDatabase) -> None:
    """Idempotent entry point invoked by the provisioning engine."""
    data = _load_seed()
    target_version = int(data.get("machine_version", 1))

    await _build_indexes(tenant_db)

    current = await _applied_version(tenant_db)
    if 1 <= current < target_version:
        await _reset_definitions(tenant_db)

    await _upsert_by(tenant_db.foundational_phases, data["foundational_phases"], "key")
    await _upsert_by(tenant_db.gate_rules, data["gate_rules"], "key")
    await _upsert_by(tenant_db.report_types, data["report_types"], "type")
    await _upsert_by(tenant_db.approver_role_map, data["approver_role_map"], "approver_role")

    # Stage definitions: the JSON set is the 'sequential' template; the 'concurrent'
    # template is derived (docs/CONCURRENT_WORKFLOW_PLAN.md). Backfill first so any
    # legacy docs (seeded before workflow_type existed) join the sequential set and
    # the compound unique index stays consistent.
    await tenant_db.stage_definitions.update_many(
        {"workflow_type": {"$exists": False}},
        {"$set": {"workflow_type": "sequential"}},
    )
    sequential = [{**d, "workflow_type": "sequential"} for d in data["stage_definitions"]]
    await _upsert_stage_defs(tenant_db.stage_definitions, sequential)
    await _upsert_stage_defs(
        tenant_db.stage_definitions, _concurrent_variant(data["stage_definitions"])
    )

    await tenant_db.pm_meta.update_one(
        {"_id": "state_machine"},
        {"$set": {"machine_version": target_version}},
        upsert=True,
    )
