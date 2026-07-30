"""Project Management Mongo access (docs/modules/PROJECT_MANAGEMENT.md §13).

No business rules — the engines own the state machine. Collection names match
what modules/projects/seed.py indexes and what the Phase 5 dashboard already
reads (`projects.milestone_schedule`).
"""

from __future__ import annotations

from datetime import UTC, datetime

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

PROJECTS = "projects"
STAGE_DEFS = "stage_definitions"
STAGE_INSTANCES = "stage_instances"
TASKS = "pm_tasks"
GATE_RULES = "gate_rules"
GATE_RESULTS = "gate_results"
APPROVALS = "approvals"
DELIVERABLES = "deliverables"
REPORTS = "reports"
JOB_COSTS = "job_costs"
APPROVER_MAP = "approver_role_map"
PHASES = "foundational_phases"
COUNTERS = "counters"

_LIVE = {"is_deleted": {"$ne": True}}


def _now() -> datetime:
    return datetime.now(UTC)


async def insert(db: AsyncIOMotorDatabase, coll: str, doc: dict) -> dict:
    now = _now()
    doc.setdefault("created_at", now)
    doc.setdefault("updated_at", now)
    doc.setdefault("is_deleted", False)
    result = await db[coll].insert_one(doc)
    doc["_id"] = result.inserted_id
    return doc


async def get(db: AsyncIOMotorDatabase, coll: str, oid: ObjectId) -> dict | None:
    return await db[coll].find_one({"_id": oid, **_LIVE})


async def list_docs(
    db: AsyncIOMotorDatabase, coll: str, query: dict, skip: int = 0,
    limit: int = 25, sort: list[tuple[str, int]] | None = None,
) -> tuple[list[dict], int]:
    filt = {**query, **_LIVE}
    total = await db[coll].count_documents(filt)
    cursor = db[coll].find(filt).sort(sort or [("created_at", -1)]).skip(skip).limit(limit)
    return await cursor.to_list(length=limit), total


async def update(
    db: AsyncIOMotorDatabase, coll: str, oid: ObjectId, fields: dict
) -> dict | None:
    fields["updated_at"] = _now()
    await db[coll].update_one({"_id": oid}, {"$set": fields})
    return await get(db, coll, oid)


async def soft_delete(
    db: AsyncIOMotorDatabase, coll: str, oid: ObjectId, actor_id: str
) -> None:
    await db[coll].update_one(
        {"_id": oid},
        {"$set": {"is_deleted": True, "deleted_at": _now(), "updated_by": actor_id}},
    )


async def next_code(db: AsyncIOMotorDatabase) -> str:
    """PRJ-0001… — atomic, like Finance's document numbering."""
    doc = await db[COUNTERS].find_one_and_update(
        {"_id": "project"}, {"$inc": {"seq": 1}}, upsert=True, return_document=True,
    )
    return f"PRJ-{int(doc['seq']):04d}"


# --- stage definitions / config (seeded, tenant-editable) --------------------

async def stage_defs(db: AsyncIOMotorDatabase) -> list[dict]:
    return [d async for d in db[STAGE_DEFS].find({}).sort([("order", 1)])]


async def stage_def_by_order(db: AsyncIOMotorDatabase, order: int) -> dict | None:
    return await db[STAGE_DEFS].find_one({"order": order})


async def stage_def_by_key(db: AsyncIOMotorDatabase, key: str) -> dict | None:
    return await db[STAGE_DEFS].find_one({"key": key})


async def gate_rules(db: AsyncIOMotorDatabase) -> list[dict]:
    return [d async for d in db[GATE_RULES].find({})]


async def gate_rule(db: AsyncIOMotorDatabase, key: str) -> dict | None:
    return await db[GATE_RULES].find_one({"key": key})


async def approver_map(db: AsyncIOMotorDatabase) -> list[dict]:
    return [d async for d in db[APPROVER_MAP].find({})]


async def approver_entry(db: AsyncIOMotorDatabase, role: str) -> dict | None:
    return await db[APPROVER_MAP].find_one({"approver_role": role})


# --- stage instances ---------------------------------------------------------

async def stage_instance(
    db: AsyncIOMotorDatabase, project_id: ObjectId, order: int
) -> dict | None:
    return await db[STAGE_INSTANCES].find_one(
        {"project_id": project_id, "stage_order": order}
    )


async def stage_instances(db: AsyncIOMotorDatabase, project_id: ObjectId) -> list[dict]:
    return [
        d async for d in db[STAGE_INSTANCES].find({"project_id": project_id})
        .sort([("stage_order", 1)])
    ]


async def upsert_stage_instance(
    db: AsyncIOMotorDatabase, project_id: ObjectId, order: int, doc: dict
) -> dict:
    """Unique on (project_id, stage_order) per §13 — one instance per stage."""
    await db[STAGE_INSTANCES].update_one(
        {"project_id": project_id, "stage_order": order},
        {"$setOnInsert": doc},
        upsert=True,
    )
    found = await stage_instance(db, project_id, order)
    assert found is not None
    return found


async def set_stage_fields(
    db: AsyncIOMotorDatabase, instance_id: ObjectId, fields: dict
) -> dict | None:
    fields["updated_at"] = _now()
    await db[STAGE_INSTANCES].update_one({"_id": instance_id}, {"$set": fields})
    return await db[STAGE_INSTANCES].find_one({"_id": instance_id})


# --- gate results ------------------------------------------------------------

async def latest_gate_result(
    db: AsyncIOMotorDatabase, instance_id: ObjectId, gate_key: str
) -> dict | None:
    return await db[GATE_RESULTS].find_one(
        {"stage_instance_id": instance_id, "gate_key": gate_key},
        sort=[("captured_at", -1)],
    )


async def gate_results_for(
    db: AsyncIOMotorDatabase, instance_id: ObjectId
) -> list[dict]:
    return [
        d async for d in db[GATE_RESULTS].find({"stage_instance_id": instance_id})
        .sort([("captured_at", 1)])
    ]


async def waived_gate_results(
    db: AsyncIOMotorDatabase, project_id: ObjectId
) -> list[dict]:
    """Every director-waived hard gate on a project — the handover's technical
    defence file (SOP §9) records these alongside the measured readings."""
    return [
        d async for d in db[GATE_RESULTS].find(
            {"project_id": project_id, "waived": True}
        ).sort([("captured_at", 1)])
    ]


# --- approvals ---------------------------------------------------------------

async def open_approval(
    db: AsyncIOMotorDatabase, instance_id: ObjectId
) -> dict | None:
    return await db[APPROVALS].find_one({
        "stage_instance_id": instance_id,
        "state": {"$nin": ["approved", "rejected"]},
    })


async def approval(db: AsyncIOMotorDatabase, oid: ObjectId) -> dict | None:
    return await db[APPROVALS].find_one({"_id": oid})


# --- reports -----------------------------------------------------------------

async def open_reports(
    db: AsyncIOMotorDatabase, project_id: ObjectId, statuses: list[str]
) -> list[dict]:
    return [
        d async for d in db[REPORTS].find({
            "project_id": project_id, "status": {"$in": statuses}, **_LIVE,
        })
    ]


async def open_snags(db: AsyncIOMotorDatabase, project_id: ObjectId) -> list[dict]:
    """Open snag reports (SOP §9) — a `na` report that is not yet resolved."""
    from app.modules.projects.permissions import (
        OPEN_REPORT_STATUSES,
        SNAG_REPORT_TYPES,
    )
    return [
        d async for d in db[REPORTS].find({
            "project_id": project_id,
            "type": {"$in": SNAG_REPORT_TYPES},
            "status": {"$in": OPEN_REPORT_STATUSES},
            **_LIVE,
        })
    ]


async def job_cost_totals(db: AsyncIOMotorDatabase, project_id: ObjectId) -> float:
    agg: list[dict] = [
        {"$match": {"project_id": project_id, **_LIVE}},
        {"$group": {"_id": None, "total": {"$sum": "$amount"}}},
    ]
    async for doc in db[JOB_COSTS].aggregate(agg):
        return float(doc["total"] or 0)
    return 0.0
