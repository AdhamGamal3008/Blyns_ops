"""CRM Mongo access (docs/modules/CRM.md). No business rules — the service
owns pipeline rules, conversion and audit. Soft delete only (BUILD.md §5).

Collection names match what the Phase 5 dashboard already reads
(`deals`, `crm_activities`) — see modules/dashboard/repository.py.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.modules.crm.permissions import TERMINAL_STAGES

# CRM's customer Account is `crm_accounts`, NOT `accounts` — `accounts` is the
# Finance chart of accounts (unique `code`), a different entity that CRM rows
# would collide with on a null code. See modules/crm/seed.py.
ACCOUNTS = "crm_accounts"
CONTACTS = "contacts"
LEADS = "leads"
DEALS = "deals"
ACTIVITIES = "crm_activities"

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
    db: AsyncIOMotorDatabase,
    coll: str,
    query: dict,
    skip: int = 0,
    limit: int = 25,
    sort: list[tuple[str, int]] | None = None,
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
        {"$set": {
            "is_deleted": True, "deleted_at": _now(), "updated_by": actor_id,
        }},
    )


async def hard_delete(db: AsyncIOMotorDatabase, coll: str, oid: ObjectId) -> None:
    """Only used to unwind a partially-completed lead conversion — a standalone
    mongod gives us no multi-document transaction, so the service compensates
    (same idiom as the control-plane seat claim in modules/settings/service.py)."""
    await db[coll].delete_one({"_id": oid})


# --- pipeline (§3 `/crm/pipeline`) -------------------------------------------

DEFAULT_PIPELINE = "default"


def pipeline_match(key: str) -> dict[str, Any]:
    """Match one pipeline's deals.

    A deal written without a `pipeline` (ad-hoc/legacy docs — the API always
    defaults it) belongs to the default pipeline. Both the board's buckets and
    its cards go through this, so they can never describe different sets.
    A Mongo `None` match also covers a missing field.
    """
    if key == DEFAULT_PIPELINE:
        return {"$or": [{"pipeline": key}, {"pipeline": None}]}
    return {"pipeline": key}


async def pipeline_buckets(
    db: AsyncIOMotorDatabase, pipeline_key: str, extra: dict | None = None
) -> dict[str, dict[str, Any]]:
    """Deals grouped by stage with counts and summed amounts (acceptance #3)."""
    match: dict[str, Any] = {**pipeline_match(pipeline_key), **_LIVE}
    if extra:
        match.update(extra)
    agg: list[dict] = [
        {"$match": match},
        {"$group": {
            "_id": "$stage",
            "count": {"$sum": 1},
            "amount": {"$sum": "$amount"},
        }},
    ]
    out: dict[str, dict[str, Any]] = {}
    async for doc in db[DEALS].aggregate(agg):
        out[doc["_id"]] = {
            "count": doc["count"], "amount": float(doc["amount"] or 0),
        }
    return out


async def open_deal_value(db: AsyncIOMotorDatabase) -> float:
    """Pipeline value KPI (§2) — open stages only."""
    agg: list[dict] = [
        {"$match": {"stage": {"$nin": list(TERMINAL_STAGES)}, **_LIVE}},
        {"$group": {"_id": None, "total": {"$sum": "$amount"}}},
    ]
    async for doc in db[DEALS].aggregate(agg):
        return float(doc["total"] or 0)
    return 0.0


async def count_by(db: AsyncIOMotorDatabase, coll: str, query: dict) -> int:
    return await db[coll].count_documents({**query, **_LIVE})
