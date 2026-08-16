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
from datetime import UTC, datetime
from pathlib import Path

from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ASCENDING, DESCENDING
from pymongo.errors import OperationFailure

_SEED_FILE = Path(__file__).with_name("stage_definitions.json")

# The two non-deletable configurations every tenant gets, reproducing the two
# workflow shapes exactly (docs/PROJECT_CONFIGURATIONS_PLAN.md §3, D-1). Tenant-
# defined configurations are cloned from these in Phase 2.
_SYSTEM_CONFIGS: tuple[dict, ...] = (
    {
        "system_key": "standard",
        "name": "Standard",
        "description": "The default 9-stage pipeline — each stage opens when the "
                       "one before it is approved.",
        "workflow_shape": "sequential",
        "is_default": True,
    },
    {
        "system_key": "concurrent",
        "name": "Concurrent",
        "description": "Stages 2-8 open together off Stage 1 and run in parallel; "
                       "Stage 9 waits for every one of them.",
        "workflow_shape": "concurrent",
        "is_default": False,
    },
)

# The machine version at which the stage SKELETON (keys, orders, the stage set
# itself) last changed. Only a bump across this line invalidates a tenant's
# definitions and warrants the destructive reset below; later bumps — v4 scopes
# the same 9 stages to a configuration — adopt what is already there.
_SKELETON_VERSION = 3


def _load_seed() -> dict:
    with _SEED_FILE.open(encoding="utf-8") as fh:
        return json.load(fh)


def concurrent_variant(seq_defs: list[dict]) -> list[dict]:
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
    """Drop a superseded unique index if present (no-op else)."""
    try:
        await collection.drop_index(name)
    except OperationFailure:
        pass


async def _drop_superseded_indexes(tenant_db: AsyncIOMotorDatabase) -> None:
    """Definition uniqueness is now per config-version, so every narrower unique
    index has to go BEFORE the scoped docs are written — the second configuration's
    copy of a stage/gate collides with any of them."""
    for name in ("key_1", "order_1", "workflow_type_1_key_1", "workflow_type_1_order_1"):
        await _drop_legacy_index(tenant_db.stage_definitions, name)
    await _drop_legacy_index(tenant_db.gate_rules, "key_1")


async def _build_definition_indexes(tenant_db: AsyncIOMotorDatabase) -> None:
    """Created only AFTER the scoped docs are written, so a tenant mid-adoption
    never trips a unique constraint the new scoping is about to satisfy."""
    for field in ("key", "order"):
        await tenant_db.stage_definitions.create_index(
            [("configuration_id", ASCENDING), ("config_version", ASCENDING),
             (field, ASCENDING)],
            unique=True,
        )
    await tenant_db.gate_rules.create_index(
        [("configuration_id", ASCENDING), ("config_version", ASCENDING),
         ("key", ASCENDING)],
        unique=True,
    )


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


async def _upsert_scoped(collection, docs: list[dict], key_field: str) -> None:
    """Definition docs are unique per (configuration_id, config_version, key) —
    upsert on the full scope so every configuration keeps its own copy (G-3) and a
    re-run never clobbers a tenant's edits."""
    for doc in docs:
        await collection.update_one(
            {
                "configuration_id": doc["configuration_id"],
                "config_version": doc["config_version"],
                key_field: doc[key_field],
            },
            {"$setOnInsert": doc},
            upsert=True,
        )


async def _ensure_system_configs(tenant_db: AsyncIOMotorDatabase) -> dict[str, dict]:
    """Seed (idempotently) the two system configurations and return them by
    system_key. Their _ids are what every definition doc and every project pins,
    so they must stay stable across re-runs — hence $setOnInsert on system_key."""
    await tenant_db.project_configurations.create_index(
        "system_key", unique=True, sparse=True
    )
    now = datetime.now(UTC)
    for spec in _SYSTEM_CONFIGS:
        await tenant_db.project_configurations.update_one(
            {"system_key": spec["system_key"]},
            {"$setOnInsert": {
                **spec,
                "current_version": 1,
                "is_system": True,
                "is_active": True,
                "is_deleted": False,
                "created_at": now,
                "updated_at": now,
                "created_by": "system",
            }},
            upsert=True,
        )
    return {
        c["system_key"]: c
        async for c in tenant_db.project_configurations.find({"is_system": True})
    }


async def _adopt_legacy_definitions(
    tenant_db: AsyncIOMotorDatabase, standard_id, concurrent_id
) -> None:
    """v3 → v4: definitions a tenant already carries — including any edits it made
    to stage names, approvers or gate thresholds — are adopted into the matching
    system configuration at version 1 rather than being wiped and re-seeded. v4
    changes no stage key and no stage order, so nothing about a running project
    moves; only the scoping fields are added."""
    # pre-v3 docs predate workflow_type entirely; those are the sequential machine
    await tenant_db.stage_definitions.update_many(
        {"workflow_type": {"$exists": False}},
        {"$set": {"workflow_type": "sequential"}},
    )
    for workflow_type, config_id in (
        ("sequential", standard_id), ("concurrent", concurrent_id)
    ):
        await tenant_db.stage_definitions.update_many(
            {"workflow_type": workflow_type, "configuration_id": {"$exists": False}},
            {"$set": {"configuration_id": config_id, "config_version": 1}},
        )
    # Gate rules were one tenant-wide set; it becomes Standard's. The Concurrent
    # configuration gets its own inserted copies below — never a shared doc (G-3).
    await tenant_db.gate_rules.update_many(
        {"configuration_id": {"$exists": False}},
        {"$set": {"configuration_id": standard_id, "config_version": 1}},
    )


def gate_label(key: str) -> str:
    """A human label for a gate key — the catalog needs one and the seed data
    carries none. `timber_moisture_content` → `Timber moisture content`."""
    words = key.replace("_", " ").strip()
    return words[:1].upper() + words[1:] if words else key


async def _seed_gate_catalog(tenant_db: AsyncIOMotorDatabase, rules: list[dict]) -> None:
    """The tenant's library of reusable gate DEFINITIONS
    (docs/PROJECT_CONFIGURATIONS_PLAN.md §3). Attaching one to a stage copies it
    into that config-version's gate_rules, where the threshold is then tuned —
    the catalog entry itself is never written back to (G-3).

    The 8 seeded gates are built-ins: they may be attached and tuned per
    configuration, but not edited or deleted here.
    """
    await tenant_db.gate_catalog.create_index("key", unique=True)
    for rule in rules:
        await tenant_db.gate_catalog.update_one(
            {"key": rule["key"]},
            {"$setOnInsert": {
                **rule,
                "name": gate_label(rule["key"]),
                "is_builtin": True,
                "is_deleted": False,
            }},
            upsert=True,
        )


async def _build_indexes(tenant_db: AsyncIOMotorDatabase) -> None:
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
    """Wipe the DEFINITION collections so a SKELETON version bump doesn't leave the
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
    await _drop_superseded_indexes(tenant_db)

    # A bump that redraws the stage skeleton invalidates what is there; a bump that
    # only re-scopes it (v3 → v4) must NOT — the reset would also discard the
    # tenant's approver_role_map, which Settings lets it edit.
    current = await _applied_version(tenant_db)
    if 1 <= current < min(target_version, _SKELETON_VERSION):
        await _reset_definitions(tenant_db)

    await _upsert_by(tenant_db.foundational_phases, data["foundational_phases"], "key")
    await _upsert_by(tenant_db.report_types, data["report_types"], "type")
    await _upsert_by(tenant_db.approver_role_map, data["approver_role_map"], "approver_role")

    # Every stage definition and gate rule belongs to one version of one
    # configuration (docs/PROJECT_CONFIGURATIONS_PLAN.md §3). Seed the two system
    # configs first — their _ids are the scope everything below is written under —
    # then adopt whatever the tenant already carries into them.
    configs = await _ensure_system_configs(tenant_db)
    standard_id = configs["standard"]["_id"]
    concurrent_id = configs["concurrent"]["_id"]
    await _adopt_legacy_definitions(tenant_db, standard_id, concurrent_id)

    # Stage definitions: the JSON set is the 'sequential' template and belongs to
    # Standard; the 'concurrent' template is derived (docs/CONCURRENT_WORKFLOW_PLAN.md)
    # and belongs to Concurrent. Both are seeded at version 1.
    sequential = [
        {**d, "workflow_type": "sequential",
         "configuration_id": standard_id, "config_version": 1}
        for d in data["stage_definitions"]
    ]
    concurrent = [
        {**d, "configuration_id": concurrent_id, "config_version": 1}
        for d in concurrent_variant(data["stage_definitions"])
    ]
    await _upsert_scoped(tenant_db.stage_definitions, sequential, "key")
    await _upsert_scoped(tenant_db.stage_definitions, concurrent, "key")

    # Each configuration holds its OWN copies of the gate rules, so tuning a
    # threshold on one can never reach another (G-3).
    for config_id in (standard_id, concurrent_id):
        await _upsert_scoped(
            tenant_db.gate_rules,
            [{**g, "configuration_id": config_id, "config_version": 1}
             for g in data["gate_rules"]],
            "key",
        )

    await _seed_gate_catalog(tenant_db, data["gate_rules"])
    await _build_definition_indexes(tenant_db)

    await tenant_db.pm_meta.update_one(
        {"_id": "state_machine"},
        {"$set": {"machine_version": target_version}},
        upsert=True,
    )
