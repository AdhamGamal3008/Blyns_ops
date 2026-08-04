"""Discovery-booking Mongo access (control plane). No business rules — the
service owns those. Sorted newest-first; paginated for the admin list.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from bson import ObjectId
from bson.errors import InvalidId
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ReturnDocument

COLLECTION = "discovery_bookings"


def _now() -> datetime:
    return datetime.now(UTC)


def _oid(booking_id: str) -> ObjectId | None:
    try:
        return ObjectId(booking_id)
    except (InvalidId, TypeError):
        return None


async def ensure_discovery_booking_indexes(control_db: AsyncIOMotorDatabase) -> None:
    coll = control_db[COLLECTION]
    await coll.create_index([("created_at", -1)])
    await coll.create_index([("status", 1), ("created_at", -1)])


async def insert(control_db: AsyncIOMotorDatabase, doc: dict) -> dict:
    now = _now()
    doc.setdefault("status", "new")
    doc.setdefault("notes", [])
    doc.setdefault("created_at", now)
    doc.setdefault("updated_at", now)
    result = await control_db[COLLECTION].insert_one(doc)
    doc["_id"] = result.inserted_id
    return doc


async def list_bookings(
    control_db: AsyncIOMotorDatabase,
    status: str | None = None,
    skip: int = 0,
    limit: int = 25,
) -> tuple[list[dict], int]:
    query: dict[str, Any] = {}
    if status is not None:
        query["status"] = status
    coll = control_db[COLLECTION]
    total = await coll.count_documents(query)
    cursor = coll.find(query).sort([("created_at", -1)]).skip(skip).limit(limit)
    return [d async for d in cursor], total


async def get(control_db: AsyncIOMotorDatabase, booking_id: str) -> dict | None:
    oid = _oid(booking_id)
    if oid is None:
        return None
    return await control_db[COLLECTION].find_one({"_id": oid})


async def update(
    control_db: AsyncIOMotorDatabase,
    booking_id: str,
    set_fields: dict[str, Any],
    note: dict[str, Any] | None = None,
) -> dict | None:
    oid = _oid(booking_id)
    if oid is None:
        return None
    change: dict[str, Any] = {"$set": {**set_fields, "updated_at": _now()}}
    if note is not None:
        change["$push"] = {"notes": note}
    return await control_db[COLLECTION].find_one_and_update(
        {"_id": oid}, change, return_document=ReturnDocument.AFTER
    )
