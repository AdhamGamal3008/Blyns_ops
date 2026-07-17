"""Inventory Mongo access (docs/modules/INVENTORY.md). No business rules — the
service owns movement rules and audit.

Collection names match what the Phase 5 dashboard already reads (`products`,
`stock_levels`) — see modules/dashboard/repository.py.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

PRODUCTS = "products"
WAREHOUSES = "warehouses"
MOVEMENTS = "movements"
STOCK_LEVELS = "stock_levels"

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


# --- the stock cache (§2) ----------------------------------------------------

async def claim_stock(
    db: AsyncIOMotorDatabase, product_id: ObjectId, warehouse_id: ObjectId,
    delta: float, allow_negative: bool,
) -> bool:
    """Apply `delta` to on_hand atomically, refusing to go negative.

    §2 asks for the cache to move "transactionally" with the movement. A
    standalone mongod has no multi-document transaction, but a single
    conditional `$inc` on one document is atomic on its own — so the guard and
    the write happen in one uninterruptible step. A read-then-write check would
    let two concurrent issues each see enough stock and both succeed.

    Returns False when the guard rejected the decrement (INSUFFICIENT_STOCK).
    """
    key = {"product_id": product_id, "warehouse_id": warehouse_id}
    if delta >= 0 or allow_negative:
        await db[STOCK_LEVELS].update_one(
            key,
            {"$inc": {"on_hand": delta}, "$set": {"updated_at": _now()}},
            upsert=True,
        )
        return True
    # decrement: only if enough is on hand right now
    result = await db[STOCK_LEVELS].find_one_and_update(
        {**key, "on_hand": {"$gte": -delta}},
        {"$inc": {"on_hand": delta}, "$set": {"updated_at": _now()}},
    )
    return result is not None


async def release_stock(
    db: AsyncIOMotorDatabase, product_id: ObjectId, warehouse_id: ObjectId,
    delta: float,
) -> None:
    """Undo a claim — used only to compensate a failed ledger write."""
    await db[STOCK_LEVELS].update_one(
        {"product_id": product_id, "warehouse_id": warehouse_id},
        {"$inc": {"on_hand": -delta}, "$set": {"updated_at": _now()}},
    )


async def on_hand(
    db: AsyncIOMotorDatabase, product_id: ObjectId, warehouse_id: ObjectId
) -> float:
    doc = await db[STOCK_LEVELS].find_one(
        {"product_id": product_id, "warehouse_id": warehouse_id}
    )
    return float(doc["on_hand"]) if doc else 0.0


async def ledger_sum(
    db: AsyncIOMotorDatabase, product_id: ObjectId, warehouse_id: ObjectId
) -> float:
    """The ledger's own signed total — the integrity reference for the cache
    (§2 "recomputable from the ledger", acceptance #1)."""
    agg: list[dict] = [
        {"$match": {"product_id": product_id, "warehouse_id": warehouse_id}},
        {"$group": {"_id": None, "total": {"$sum": "$qty"}}},
    ]
    async for doc in db[MOVEMENTS].aggregate(agg):
        return float(doc["total"] or 0)
    return 0.0


async def stock_levels(
    db: AsyncIOMotorDatabase, query: dict, skip: int = 0, limit: int = 25
) -> tuple[list[dict], int]:
    total = await db[STOCK_LEVELS].count_documents(query)
    cursor = db[STOCK_LEVELS].find(query).sort([("on_hand", 1)]).skip(skip).limit(limit)
    return await cursor.to_list(length=limit), total


# --- low stock (§2) ----------------------------------------------------------
#
# ONE definition, used by both `/inventory/low-stock` and the dashboard's
# `low_stock_items` KPI (modules/dashboard/repository.py delegates here). If the
# list and the KPI computed this separately they would drift apart and the
# dashboard would contradict the module.
#
# `reorder_point > 0` matters: an item with no reorder point configured is not
# "low", it is unconfigured — otherwise every zero-stock item with no reorder
# policy would be flagged forever.

LOW_STOCK_AGG: list[dict] = [
    {"$lookup": {
        "from": PRODUCTS, "localField": "product_id",
        "foreignField": "_id", "as": "product",
    }},
    {"$unwind": "$product"},
    {"$match": {
        "product.is_active": True,
        "product.is_deleted": {"$ne": True},
        "product.reorder_point": {"$gt": 0},
        "$expr": {"$lte": ["$on_hand", "$product.reorder_point"]},
    }},
]


async def low_stock(db: AsyncIOMotorDatabase) -> list[dict]:
    agg = [*LOW_STOCK_AGG, {"$sort": {"on_hand": 1}}]
    return [doc async for doc in db[STOCK_LEVELS].aggregate(agg)]


async def low_stock_count(db: AsyncIOMotorDatabase) -> int:
    agg = [*LOW_STOCK_AGG, {"$count": "n"}]
    async for doc in db[STOCK_LEVELS].aggregate(agg):
        return int(doc["n"])
    return 0


async def count_by(db: AsyncIOMotorDatabase, coll: str, query: dict) -> int:
    return await db[coll].count_documents({**query, **_LIVE})


async def any_stock_for_product(
    db: AsyncIOMotorDatabase, product_id: ObjectId
) -> dict[str, Any] | None:
    return await db[STOCK_LEVELS].find_one(
        {"product_id": product_id, "on_hand": {"$ne": 0}}
    )
