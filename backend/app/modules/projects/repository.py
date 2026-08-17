"""Project Management Mongo access (docs/modules/PROJECT_MANAGEMENT.md §13).

No business rules — the engines own the state machine. Collection names match
what modules/projects/seed.py indexes and what the Phase 5 dashboard already
reads (`projects.milestone_schedule`).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

PROJECTS = "projects"
PROJECT_CONFIGS = "project_configurations"
GATE_CATALOG = "gate_catalog"
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
DELEGATIONS = "approver_delegations"
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


# --- project configurations & definition scope -------------------------------

# Stage definitions and gate rules belong to ONE VERSION OF ONE CONFIGURATION
# (docs/PROJECT_CONFIGURATIONS_PLAN.md §3). A tenant carries a full immutable copy
# of both per config-version, so every lookup must say which set it means — that
# is a ConfigScope. This generalises the workflow_type scoping the concurrent
# workflow introduced: the two shapes survive as the two seeded system configs.


@dataclass(frozen=True)
class ConfigScope:
    """Which definition set a lookup reads.

    A tenant on machine_version 4+ scopes by `(configuration_id, config_version)`.
    A tenant the v4 migration has not reached yet has neither field on its
    definition docs, so `configuration_id is None` degrades the scope to the
    legacy workflow_type filter — that is what keeps live tenants working before
    the migration runs (PROJECT_CONFIGURATIONS_PLAN.md G-1).
    """

    configuration_id: ObjectId | None = None
    config_version: int | None = None
    workflow_type: str = "sequential"

    @property
    def is_legacy(self) -> bool:
        return self.configuration_id is None


def _legacy_wf_query(workflow_type: str) -> dict:
    """A tenant seeded before workflow_type existed carries stage docs with no such
    field; those are the sequential machine, so a missing field reads as sequential."""
    if workflow_type == "sequential":
        return {"$or": [{"workflow_type": "sequential"},
                        {"workflow_type": {"$exists": False}}]}
    return {"workflow_type": workflow_type}


def _config_query(scope: ConfigScope) -> dict:
    return {
        "configuration_id": scope.configuration_id,
        "config_version": scope.config_version,
    }


def _stage_scope_query(scope: ConfigScope) -> dict:
    return _legacy_wf_query(scope.workflow_type) if scope.is_legacy else _config_query(scope)


def _gate_scope_query(scope: ConfigScope) -> dict:
    # Pre-v4 gate rules were one tenant-wide set with no scoping field at all.
    return {} if scope.is_legacy else _config_query(scope)


def _as_scope(scope: ConfigScope | str) -> ConfigScope:
    """Accept a bare workflow_type from call sites the Phase-1 threading has not
    reached yet — those still resolve through the legacy filter, which the seeded
    system configs keep answering correctly."""
    return scope if isinstance(scope, ConfigScope) else ConfigScope(workflow_type=scope)


def in_scope(definition: dict, scope: ConfigScope) -> bool:
    """Whether a definition doc belongs to `scope` — how a caller detects it was
    handed another configuration's copy of the same stage (same key, same order,
    different gates)."""
    if scope.is_legacy:
        return definition.get("workflow_type", "sequential") == scope.workflow_type
    return (
        definition.get("configuration_id") == scope.configuration_id
        and definition.get("config_version") == scope.config_version
    )


def scope_of(config: dict) -> ConfigScope:
    """The scope reading a configuration's CURRENT version — what a project pins
    at creation, and what the config editor loads."""
    return ConfigScope(
        config["_id"],
        int(config.get("current_version", 1)),
        config.get("workflow_shape", "sequential"),
    )


async def project_configs(
    db: AsyncIOMotorDatabase, active_only: bool = False
) -> list[dict]:
    query: dict = {**_LIVE}
    if active_only:
        query["is_active"] = {"$ne": False}
    return [
        d async for d in db[PROJECT_CONFIGS].find(query).sort([("name", 1)])
    ]


async def project_config(db: AsyncIOMotorDatabase, oid: ObjectId) -> dict | None:
    return await db[PROJECT_CONFIGS].find_one({"_id": oid, **_LIVE})


async def default_project_config(db: AsyncIOMotorDatabase) -> dict | None:
    """The configuration a project gets when none is chosen. Falls back to the
    Standard system config so a tenant is never left without one (G-4)."""
    return await db[PROJECT_CONFIGS].find_one(
        {"is_default": True, **_LIVE}
    ) or await db[PROJECT_CONFIGS].find_one(
        {"is_system": True, "workflow_shape": "sequential", **_LIVE}
    )


async def system_config(
    db: AsyncIOMotorDatabase, workflow_shape: str
) -> dict | None:
    """The seeded, non-deletable configuration reproducing one of the two original
    workflow shapes — how a pre-v4 `workflow_type` maps onto a configuration."""
    return await db[PROJECT_CONFIGS].find_one(
        {"is_system": True, "workflow_shape": workflow_shape, **_LIVE}
    )


async def projects_on_config(
    db: AsyncIOMotorDatabase, config_id: ObjectId
) -> int:
    """How many live projects pin a configuration — the delete guard (G-4)."""
    return await db[PROJECTS].count_documents({"configuration_id": config_id, **_LIVE})


async def highest_config_version(
    db: AsyncIOMotorDatabase, config_id: ObjectId
) -> int:
    """The largest version number this configuration has stage definitions for.

    Normally equal to its `current_version`, but a publish that failed partway
    leaves docs at a version the config never adopted. Numbering the next publish
    above THAT (rather than above current_version) means a retry lands on a free
    version instead of colliding with the debris forever.
    """
    doc = await db[STAGE_DEFS].find_one(
        {"configuration_id": config_id}, sort=[("config_version", -1)]
    )
    return int(doc["config_version"]) if doc else 0


async def active_config_count(db: AsyncIOMotorDatabase) -> int:
    return await db[PROJECT_CONFIGS].count_documents(
        {"is_active": {"$ne": False}, **_LIVE}
    )


# --- gate catalog (the tenant's reusable gate definitions) --------------------

async def gate_catalog(db: AsyncIOMotorDatabase) -> list[dict]:
    return [
        d async for d in db[GATE_CATALOG].find(_LIVE).sort([("name", 1)])
    ]


async def gate_catalog_entry(db: AsyncIOMotorDatabase, key: str) -> dict | None:
    return await db[GATE_CATALOG].find_one({"key": key, **_LIVE})


async def default_scope(db: AsyncIOMotorDatabase) -> ConfigScope:
    """The scope for reads with no project context — the /config/* browsing
    endpoints. Legacy (unscoped) on a tenant with no configurations yet."""
    config = await default_project_config(db)
    return scope_of(config) if config else ConfigScope()


async def scope_for_project(
    db: AsyncIOMotorDatabase, project: dict
) -> ConfigScope:
    """The definition set a project runs against — the configuration VERSION it
    pinned at creation, never the config's current version (D1/G-5): a published
    version is immutable, so a running project's stages and gates cannot shift.

    A project created before v4 carries no pin. It falls back to the system config
    matching its workflow_type at **version 1** — the version the v4 migration
    stamps existing definitions with — so a later publish cannot move it either.
    """
    workflow_type = project.get("workflow_type", "sequential")
    config_id = project.get("configuration_id")
    if config_id is not None:
        return ConfigScope(config_id, int(project.get("config_version", 1)), workflow_type)
    config = await system_config(db, workflow_type)
    return ConfigScope(config["_id"], 1, workflow_type) if config else ConfigScope(
        workflow_type=workflow_type
    )


# --- stage definitions / config (seeded, tenant-editable) --------------------

async def stage_defs(
    db: AsyncIOMotorDatabase, scope: ConfigScope | str = "sequential"
) -> list[dict]:
    return [
        d async for d in
        db[STAGE_DEFS].find(_stage_scope_query(_as_scope(scope))).sort([("order", 1)])
    ]


async def stage_def_by_order(
    db: AsyncIOMotorDatabase, order: int, scope: ConfigScope | str = "sequential"
) -> dict | None:
    return await db[STAGE_DEFS].find_one(
        {**_stage_scope_query(_as_scope(scope)), "order": order}
    )


async def stage_def_by_key(
    db: AsyncIOMotorDatabase, key: str, scope: ConfigScope | str = "sequential"
) -> dict | None:
    return await db[STAGE_DEFS].find_one(
        {**_stage_scope_query(_as_scope(scope)), "key": key}
    )


async def gate_rules(
    db: AsyncIOMotorDatabase, scope: ConfigScope | None = None
) -> list[dict]:
    resolved = scope if scope is not None else await default_scope(db)
    return [d async for d in db[GATE_RULES].find(_gate_scope_query(resolved))]


async def gate_rule(
    db: AsyncIOMotorDatabase, key: str, scope: ConfigScope | None = None
) -> dict | None:
    """A gate rule is only unique WITHIN a config-version, so an unscoped lookup
    would pick an arbitrary copy — callers with a project in hand must pass its
    scope. `None` means "the tenant's default configuration"."""
    resolved = scope if scope is not None else await default_scope(db)
    return await db[GATE_RULES].find_one({**_gate_scope_query(resolved), "key": key})


async def approver_map(db: AsyncIOMotorDatabase) -> list[dict]:
    return [d async for d in db[APPROVER_MAP].find({})]


async def approver_entry(db: AsyncIOMotorDatabase, role: str) -> dict | None:
    return await db[APPROVER_MAP].find_one({"approver_role": role})


# --- approver delegations (SOP §2) -------------------------------------------

async def list_delegations(db: AsyncIOMotorDatabase) -> list[dict]:
    return [
        d async for d in db[DELEGATIONS].find(_LIVE).sort([("created_at", -1)])
    ]


async def has_active_delegation(
    db: AsyncIOMotorDatabase, approver_role: str, user_id: str,
    now: datetime | None = None,
) -> bool:
    """True if a live, un-revoked delegation of `approver_role` names `user_id`
    and the current time is inside its [starts_at, ends_at] window."""
    moment = now or _now()
    doc = await db[DELEGATIONS].find_one({
        "approver_role": approver_role,
        "delegate_user_id": user_id,
        "revoked": False,
        "starts_at": {"$lte": moment},
        "ends_at": {"$gte": moment},
        **_LIVE,
    })
    return doc is not None


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


# --- analytics aggregations (docs/PROJECT_ANALYTICS_PLAN.md §2) ---------------
# Read-only portfolio rollups. Every pipeline filters soft-deletes via _LIVE.
# stage_instances carry no is_deleted (never soft-deleted), so _LIVE is a
# harmless no-op there — but active projects are always _LIVE-filtered first.

# A correlated $lookup that attaches each project's CURRENT stage instance as
# `cur` (matched on project_id AND stage_order == the project's current order).
_CURRENT_STAGE_LOOKUP: list[dict] = [
    {"$lookup": {
        "from": STAGE_INSTANCES,
        "let": {"pid": "$_id", "ord": "$current_stage_order"},
        "pipeline": [{"$match": {"$expr": {"$and": [
            {"$eq": ["$project_id", "$$pid"]},
            {"$eq": ["$stage_order", "$$ord"]},
        ]}}}],
        "as": "cur",
    }},
    {"$unwind": {"path": "$cur", "preserveNullAndEmptyArrays": True}},
]


async def analytics_status_counts(db: AsyncIOMotorDatabase) -> dict[str, int]:
    agg: list[dict] = [
        {"$match": _LIVE}, {"$group": {"_id": "$status", "n": {"$sum": 1}}},
    ]
    return {d["_id"]: int(d["n"]) async for d in db[PROJECTS].aggregate(agg)}


async def analytics_stalled_count(
    db: AsyncIOMotorDatabase, stalled: list[str], terminal: list[str]
) -> int:
    """Non-terminal projects that are `on_hold`, or whose current stage sits in a
    stalled state (waiting/blocked/on_hold)."""
    agg: list[dict] = [
        {"$match": {**_LIVE, "status": {"$nin": terminal}}},
        *_CURRENT_STAGE_LOOKUP,
        {"$match": {"$or": [
            {"status": "on_hold"},
            {"cur.status": {"$in": stalled}},
        ]}},
        {"$count": "n"},
    ]
    async for d in db[PROJECTS].aggregate(agg):
        return int(d["n"])
    return 0


async def analytics_overdue_count(
    db: AsyncIOMotorDatabase, now: datetime, exclude_statuses: list[str]
) -> int:
    return await db[PROJECTS].count_documents({
        **_LIVE,
        "status": {"$nin": exclude_statuses},
        "schedule.delivery_date": {"$lt": now},
    })


async def analytics_open_report_count(
    db: AsyncIOMotorDatabase, statuses: list[str]
) -> int:
    return await db[REPORTS].count_documents({**_LIVE, "status": {"$in": statuses}})


async def analytics_budget_totals(db: AsyncIOMotorDatabase) -> dict[str, float]:
    agg: list[dict] = [
        {"$match": _LIVE},
        {"$group": {
            "_id": None,
            "planned": {"$sum": "$budget.planned"},
            "committed": {"$sum": "$budget.committed"},
            "actual": {"$sum": "$budget.actual"},
        }},
    ]
    async for d in db[PROJECTS].aggregate(agg):
        return {k: float(d.get(k) or 0) for k in ("planned", "committed", "actual")}
    return {"planned": 0.0, "committed": 0.0, "actual": 0.0}


async def analytics_active_by_stage(db: AsyncIOMotorDatabase) -> dict[int, int]:
    """Active project count keyed by current_stage_order."""
    agg: list[dict] = [
        {"$match": {**_LIVE, "status": "active"}},
        {"$group": {"_id": "$current_stage_order", "n": {"$sum": 1}}},
    ]
    return {
        int(d["_id"]): int(d["n"])
        async for d in db[PROJECTS].aggregate(agg) if d["_id"] is not None
    }


async def analytics_time_in_current_stage(
    db: AsyncIOMotorDatabase, now: datetime
) -> dict[int, dict]:
    """Per current-stage-order: avg days active projects have sat in that stage
    (now − entered_at) and how many. Keyed by stage_order."""
    agg: list[dict] = [
        {"$match": {**_LIVE, "status": "active"}},
        *_CURRENT_STAGE_LOOKUP,
        {"$match": {"cur": {"$exists": True}}},
        {"$group": {
            "_id": "$cur.stage_order",
            "avg_ms": {"$avg": {"$subtract": [now, "$cur.entered_at"]}},
            "count": {"$sum": 1},
        }},
    ]
    return {
        int(d["_id"]): {
            "avg_days": round(float(d["avg_ms"] or 0) / 86_400_000, 1),
            "count": int(d["count"]),
        }
        async for d in db[PROJECTS].aggregate(agg) if d["_id"] is not None
    }


async def analytics_top_projects(
    db: AsyncIOMotorDatabase, limit: int
) -> list[dict]:
    """Largest projects by planned budget — the ones where planned-vs-actual
    adherence matters most."""
    agg: list[dict] = [
        {"$match": _LIVE},
        {"$project": {
            "_id": 0, "code": 1, "name": 1,
            "planned": {"$ifNull": ["$budget.planned", 0]},
            "actual": {"$ifNull": ["$budget.actual", 0]},
        }},
        {"$sort": {"planned": -1, "actual": -1}},
        {"$limit": limit},
    ]
    return [d async for d in db[PROJECTS].aggregate(agg)]


async def analytics_cost_by_type(db: AsyncIOMotorDatabase) -> dict[str, float]:
    agg: list[dict] = [
        {"$match": _LIVE},
        {"$group": {"_id": "$cost_type", "amount": {"$sum": "$amount"}}},
    ]
    return {
        d["_id"]: float(d["amount"] or 0)
        async for d in db[JOB_COSTS].aggregate(agg) if d["_id"]
    }


async def analytics_exceptions_by_type_status(
    db: AsyncIOMotorDatabase, statuses: list[str]
) -> list[dict]:
    agg: list[dict] = [
        {"$match": {**_LIVE, "status": {"$in": statuses}}},
        {"$group": {
            "_id": {"type": "$type", "status": "$status"}, "n": {"$sum": 1},
        }},
    ]
    return [
        {"type": d["_id"]["type"], "status": d["_id"]["status"], "n": int(d["n"])}
        async for d in db[REPORTS].aggregate(agg)
    ]


async def analytics_monthly_counts(
    db: AsyncIOMotorDatabase, date_field: str, since: datetime
) -> dict[str, int]:
    """Project counts bucketed by 'YYYY-MM' of `date_field` (created_at for
    started, completed_at for completed), from `since` onward. Docs where the
    field is null (e.g. not-yet-completed) drop out at the range match."""
    agg: list[dict] = [
        {"$match": {**_LIVE, date_field: {"$gte": since}}},
        {"$group": {
            "_id": {"$dateToString": {"format": "%Y-%m", "date": f"${date_field}"}},
            "n": {"$sum": 1},
        }},
    ]
    return {
        d["_id"]: int(d["n"])
        async for d in db[PROJECTS].aggregate(agg) if d["_id"]
    }
