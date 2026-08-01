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
from pathlib import Path

from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ASCENDING, DESCENDING

_SEED_FILE = Path(__file__).with_name("stage_definitions.json")


def _load_seed() -> dict:
    with _SEED_FILE.open(encoding="utf-8") as fh:
        return json.load(fh)


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


async def _build_indexes(tenant_db: AsyncIOMotorDatabase) -> None:
    # Definition/config collections
    await tenant_db.stage_definitions.create_index("key", unique=True)
    await tenant_db.stage_definitions.create_index("order", unique=True)
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
    await _upsert_by(tenant_db.stage_definitions, data["stage_definitions"], "key")

    await tenant_db.pm_meta.update_one(
        {"_id": "state_machine"},
        {"$set": {"machine_version": target_version}},
        upsert=True,
    )
