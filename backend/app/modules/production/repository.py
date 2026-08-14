"""Production module data access (docs/PRODUCTION_MODULE_PLAN.md §3).

Collections live in the tenant DB. `work_orders` is the aggregate; `production_
stations` are the seeded work centres. Production also *reads* (never writes)
sibling collections in the same tenant DB — the project, its BOM + shop-drawing
deliverables (version-pinned), the product catalogue, and the CRM account — so it
imports their collection names rather than hard-coding strings.
"""

from __future__ import annotations

from datetime import UTC, datetime

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.modules.crm.repository import ACCOUNTS
from app.modules.inventory.repository import PRODUCTS, WAREHOUSES
from app.modules.projects.repository import DELIVERABLES, PROJECTS

STATIONS = "production_stations"
WORK_ORDERS = "work_orders"
PRODUCTION_ROLLUP = "production_rollup"
COUNTERS = "counters"

_LIVE = {"is_deleted": {"$ne": True}}


def _now() -> datetime:
    return datetime.now(UTC)


# --- stations ----------------------------------------------------------------

async def list_stations(db: AsyncIOMotorDatabase) -> list[dict]:
    """Active work centres, ordered by code."""
    return [s async for s in db[STATIONS].find({"is_active": True}).sort("code", 1)]


async def stations_map(db: AsyncIOMotorDatabase) -> dict[str, dict]:
    """{station_id: station} over all stations, for enriching WO rows."""
    return {str(s["_id"]): s async for s in db[STATIONS].find({})}


async def get_station(db: AsyncIOMotorDatabase, oid: ObjectId) -> dict | None:
    return await db[STATIONS].find_one({"_id": oid})


async def station_load(
    db: AsyncIOMotorDatabase, active_statuses: list[str]
) -> dict[str, dict]:
    """{station_id: {units, count}} — the remaining build work parked at each
    station (only WOs still in a producing state count against capacity)."""
    agg: list[dict] = [
        {"$match": {
            "status": {"$in": active_statuses},
            "current_station_id": {"$ne": None},
            **_LIVE,
        }},
        {"$group": {
            "_id": "$current_station_id",
            "units": {"$sum": {"$subtract": ["$qty.ordered", "$qty.done"]}},
            "count": {"$sum": 1},
        }},
    ]
    out: dict[str, dict] = {}
    async for d in db[WORK_ORDERS].aggregate(agg):
        out[str(d["_id"])] = {"units": float(d["units"] or 0), "count": int(d["count"])}
    return out


# --- cross-module reads (same tenant DB, read-only) --------------------------

async def get_project(db: AsyncIOMotorDatabase, oid: ObjectId) -> dict | None:
    return await db[PROJECTS].find_one({"_id": oid, **_LIVE})


async def reservable_bom(db: AsyncIOMotorDatabase, project_id: ObjectId) -> dict | None:
    """The BOM deliverable that carries product lines — never a line-less BOM
    *file* (the shadow trap; mirrors projects `_reserve_stock`). Newest wins."""
    return await db[DELIVERABLES].find_one(
        {"project_id": project_id, "kind": "bom", "is_deleted": {"$ne": True},
         "lines.0": {"$exists": True}},
        sort=[("created_at", -1)],
    )


async def has_any_bom(db: AsyncIOMotorDatabase, project_id: ObjectId) -> bool:
    """Whether the project has *any* BOM deliverable, line-carrying or not — a
    BOM attached only as gate evidence has an empty `lines[]`. Lets propose tell
    'no BOM at all' apart from 'a BOM with no product lines' (plan §2.1)."""
    doc = await db[DELIVERABLES].find_one(
        {"project_id": project_id, "kind": "bom", "is_deleted": {"$ne": True}},
        {"_id": 1},
    )
    return doc is not None


async def latest_shop_drawing(
    db: AsyncIOMotorDatabase, project_id: ObjectId
) -> dict | None:
    return await db[DELIVERABLES].find_one(
        {"project_id": project_id, "kind": "shop_drawing", "is_deleted": {"$ne": True}},
        sort=[("created_at", -1)],
    )


async def product(db: AsyncIOMotorDatabase, oid: ObjectId) -> dict | None:
    return await db[PRODUCTS].find_one({"_id": oid})


async def account_name(
    db: AsyncIOMotorDatabase, account_id: str | None
) -> str | None:
    if not account_id:
        return None
    try:
        doc = await db[ACCOUNTS].find_one({"_id": ObjectId(account_id)})
    except Exception:
        return None
    return (doc or {}).get("name")


async def deliverable_versions(
    db: AsyncIOMotorDatabase, ids: list[ObjectId]
) -> dict[str, int]:
    """{deliverable_id: current_version} — the newest revision on record, used to
    flag a WO pinned to a superseded drawing (plan §2.1)."""
    out: dict[str, int] = {}
    async for d in db[DELIVERABLES].find({"_id": {"$in": ids}}, {"current_version": 1}):
        out[str(d["_id"])] = int(d.get("current_version", 1))
    return out


# --- work orders -------------------------------------------------------------

async def next_wo_seq(db: AsyncIOMotorDatabase, project_id: ObjectId) -> int:
    """Per-project WO sequence — atomic, like Finance/Projects document numbers."""
    doc = await db[COUNTERS].find_one_and_update(
        {"_id": f"wo_{project_id}"}, {"$inc": {"seq": 1}},
        upsert=True, return_document=True,
    )
    return int(doc["seq"])


async def insert_work_order(db: AsyncIOMotorDatabase, doc: dict) -> dict:
    now = _now()
    doc.setdefault("created_at", now)
    doc.setdefault("updated_at", now)
    doc.setdefault("is_deleted", False)
    result = await db[WORK_ORDERS].insert_one(doc)
    doc["_id"] = result.inserted_id
    return doc


async def get_work_order(db: AsyncIOMotorDatabase, oid: ObjectId) -> dict | None:
    return await db[WORK_ORDERS].find_one({"_id": oid, **_LIVE})


async def list_work_orders(
    db: AsyncIOMotorDatabase, query: dict, skip: int = 0, limit: int = 25,
    sort: list[tuple[str, int]] | None = None,
) -> tuple[list[dict], int]:
    filt = {**query, **_LIVE}
    total = await db[WORK_ORDERS].count_documents(filt)
    cursor = (
        db[WORK_ORDERS].find(filt).sort(sort or [("created_at", -1)]).skip(skip).limit(limit)
    )
    return await cursor.to_list(length=limit), total


async def queue_work_orders(
    db: AsyncIOMotorDatabase, query: dict, limit: int = 500
) -> list[dict]:
    """The cross-project work list (unpaginated within a sane cap). Ordering is
    applied in the service so null due dates sort last, not first."""
    filt = {**query, **_LIVE}
    return await db[WORK_ORDERS].find(filt).limit(limit).to_list(length=limit)


async def live_work_orders(
    db: AsyncIOMotorDatabase, project_id: ObjectId
) -> list[dict]:
    """Every live WO on a project — the input to the Stage-6 checklist rollup."""
    return await db[WORK_ORDERS].find({"project_id": project_id, **_LIVE}).to_list(length=2000)


async def update_work_order(
    db: AsyncIOMotorDatabase, oid: ObjectId, fields: dict
) -> dict | None:
    fields["updated_at"] = _now()
    await db[WORK_ORDERS].update_one({"_id": oid}, {"$set": fields})
    return await get_work_order(db, oid)


# --- pipeline rollup (display cache, keyed by project_id) --------------------

async def upsert_rollup(
    db: AsyncIOMotorDatabase, project_id: ObjectId, sections: dict
) -> None:
    await db[PRODUCTION_ROLLUP].update_one(
        {"_id": project_id},
        {"$set": {"sections": sections, "updated_at": _now()}},
        upsert=True,
    )


async def get_rollup(
    db: AsyncIOMotorDatabase, project_id: ObjectId
) -> dict | None:
    return await db[PRODUCTION_ROLLUP].find_one({"_id": project_id})


# --- inventory (read a warehouse to draw rework stock from) ------------------

async def default_warehouse(db: AsyncIOMotorDatabase) -> dict | None:
    return await db[WAREHOUSES].find_one({"is_deleted": {"$ne": True}}, sort=[("code", 1)])
