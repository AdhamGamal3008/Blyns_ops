"""Admin users + admin roles Mongo access (control plane)."""

from __future__ import annotations

from datetime import UTC, datetime

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.control_plane.admin_users.models import default_admin_roles


async def ensure_admin_indexes(control_db: AsyncIOMotorDatabase) -> None:
    await control_db.admin_users.create_index("email", unique=True)
    await control_db.admin_roles.create_index("name", unique=True)


async def seed_admin_roles(control_db: AsyncIOMotorDatabase) -> dict[str, ObjectId]:
    """Upsert the default admin roles; return {name: role_id}. Idempotent.

    `$setOnInsert` never clobbers an operator's later edits — but a resource ADDED to
    `ADMIN_RESOURCES` after a role was first seeded would otherwise never reach an
    already-seeded role (e.g. a new `ip_rules` never reaching an existing Super
    Admin). So we also **backfill** any missing resource keys to the role's default
    level, leaving existing (possibly-edited) levels untouched.
    """
    ids: dict[str, ObjectId] = {}
    for role in default_admin_roles():
        await control_db.admin_roles.update_one(
            {"name": role["name"]}, {"$setOnInsert": role}, upsert=True
        )
        doc = await control_db.admin_roles.find_one({"name": role["name"]})
        assert doc is not None  # just upserted
        current = doc.get("permissions") or {}
        missing = {
            f"permissions.{res}": level
            for res, level in role["permissions"].items()
            if res not in current
        }
        if missing:
            await control_db.admin_roles.update_one({"_id": doc["_id"]}, {"$set": missing})
        ids[role["name"]] = doc["_id"]
    return ids


async def get_admin_by_email(control_db: AsyncIOMotorDatabase, email: str) -> dict | None:
    return await control_db.admin_users.find_one({"email": email.lower()})


async def get_admin_by_id(
    control_db: AsyncIOMotorDatabase, admin_id: ObjectId | str
) -> dict | None:
    return await control_db.admin_users.find_one({"_id": ObjectId(admin_id)})


async def get_admin_role(control_db: AsyncIOMotorDatabase, role_id: ObjectId | str) -> dict | None:
    return await control_db.admin_roles.find_one({"_id": ObjectId(role_id)})


async def create_admin_user(
    control_db: AsyncIOMotorDatabase,
    email: str,
    name: str,
    password_hash: str,
    role_id: ObjectId,
) -> dict | None:
    """Create if the email is free; returns the doc or None if it existed."""
    now = datetime.now(UTC)
    result = await control_db.admin_users.update_one(
        {"email": email.lower()},
        {"$setOnInsert": {
            "email": email.lower(),
            "password_hash": password_hash,
            "name": name,
            "role_id": role_id,
            "is_active": True,
            "failed_attempts": 0,
            "locked_until": None,
            "refresh_jtis": [],
            "created_at": now,
            "updated_at": now,
        }},
        upsert=True,
    )
    if result.upserted_id is None:
        return None
    return await control_db.admin_users.find_one({"_id": result.upserted_id})
