"""IP access rule Mongo access (docs/IP_ACCESS_CONTROL_PLAN.md §2-A). Control
plane, platform-wide. No business rules — the matcher (P2) and admin service (P5)
own those.

Rules are matched in-process from a small, admin-managed set (allow/deny entries
plus a handful of country codes), so we store the canonical `value` + `family` and
build `ipaddress` networks at match time rather than encoding 128-bit IPv6 bounds
into BSON. Soft-delete keeps an audit trail.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

COLLECTION = "ip_access_rules"

_LIVE = {"is_deleted": {"$ne": True}}


def _now() -> datetime:
    return datetime.now(UTC)


async def ensure_ip_rule_indexes(control_db: AsyncIOMotorDatabase) -> None:
    coll = control_db[COLLECTION]
    await coll.create_index([("kind", 1), ("match_type", 1), ("enabled", 1)])
    await coll.create_index("value")


async def insert(control_db: AsyncIOMotorDatabase, doc: dict) -> dict:
    now = _now()
    doc.setdefault("created_at", now)
    doc.setdefault("updated_at", now)
    doc.setdefault("is_deleted", False)
    result = await control_db[COLLECTION].insert_one(doc)
    doc["_id"] = result.inserted_id
    return doc


async def list_rules(
    control_db: AsyncIOMotorDatabase,
    kind: str | None = None,
    match_type: str | None = None,
    enabled: bool | None = None,
) -> list[dict]:
    query: dict[str, Any] = dict(_LIVE)
    if kind is not None:
        query["kind"] = kind
    if match_type is not None:
        query["match_type"] = match_type
    if enabled is not None:
        query["enabled"] = enabled
    return [
        d async for d in control_db[COLLECTION].find(query).sort([("created_at", -1)])
    ]


async def enabled_rules(control_db: AsyncIOMotorDatabase) -> list[dict]:
    """Every live, enabled rule — the input to the matching engine (P2)."""
    return [
        d async for d in control_db[COLLECTION].find({"enabled": True, **_LIVE})
    ]


async def get(control_db: AsyncIOMotorDatabase, oid: ObjectId | str) -> dict | None:
    return await control_db[COLLECTION].find_one({"_id": ObjectId(oid), **_LIVE})


async def find_duplicate(
    control_db: AsyncIOMotorDatabase, kind: str, match_type: str, value: str
) -> dict | None:
    """A live rule with the same identity — the service uses this to reject
    duplicates (kind + match_type + value)."""
    return await control_db[COLLECTION].find_one(
        {"kind": kind, "match_type": match_type, "value": value, **_LIVE}
    )


async def update(
    control_db: AsyncIOMotorDatabase, oid: ObjectId | str, fields: dict
) -> dict | None:
    fields["updated_at"] = _now()
    await control_db[COLLECTION].update_one({"_id": ObjectId(oid)}, {"$set": fields})
    return await get(control_db, oid)


async def soft_delete(
    control_db: AsyncIOMotorDatabase, oid: ObjectId | str, actor_id: str
) -> None:
    await control_db[COLLECTION].update_one(
        {"_id": ObjectId(oid)},
        {"$set": {"is_deleted": True, "deleted_at": _now(), "deleted_by": actor_id}},
    )
