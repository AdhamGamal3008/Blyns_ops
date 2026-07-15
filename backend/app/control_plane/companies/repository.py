"""Company registry Mongo access (docs/MULTITENANCY.md §2). No business rules."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.control_plane.companies.models import OnboardCompanyPayload


async def ensure_company_indexes(control_db: AsyncIOMotorDatabase) -> None:
    await control_db.companies.create_index("slug", unique=True)
    await control_db.companies.create_index("db_name", unique=True)
    await control_db.companies.create_index("status")


async def get_by_slug(control_db: AsyncIOMotorDatabase, slug: str) -> dict | None:
    return await control_db.companies.find_one({"slug": slug})


async def get_by_db_name(control_db: AsyncIOMotorDatabase, db_name: str) -> dict | None:
    return await control_db.companies.find_one({"db_name": db_name})


async def get_by_id(control_db: AsyncIOMotorDatabase, company_id: ObjectId | str) -> dict | None:
    return await control_db.companies.find_one({"_id": ObjectId(company_id)})


async def reserve(
    control_db: AsyncIOMotorDatabase,
    payload: OnboardCompanyPayload,
    onboarded_by: str,
) -> dict:
    """Step 1 of provisioning: write the company doc with status="provisioning"."""
    now = datetime.now(UTC)
    doc = {
        "name": payload.name,
        "slug": payload.slug,
        "db_name": payload.db_name,
        "status": "provisioning",
        "seat_limit": payload.seat_limit,
        "seats_used": 0,
        "security": payload.security.model_dump(),
        "enabled_modules": payload.enabled_modules,
        "onboarded_by": onboarded_by,
        "provisioned_at": None,
        "created_at": now,
        "updated_at": now,
    }
    result = await control_db.companies.insert_one(doc)
    doc["_id"] = result.inserted_id
    return doc


async def update_fields(
    control_db: AsyncIOMotorDatabase,
    company_id: ObjectId,
    fields: dict[str, Any],
) -> None:
    fields["updated_at"] = datetime.now(UTC)
    await control_db.companies.update_one({"_id": company_id}, {"$set": fields})


async def inc_seats_used(
    control_db: AsyncIOMotorDatabase, company_id: ObjectId, delta: int = 1
) -> None:
    await control_db.companies.update_one(
        {"_id": company_id},
        {"$inc": {"seats_used": delta}, "$set": {"updated_at": datetime.now(UTC)}},
    )


async def delete(control_db: AsyncIOMotorDatabase, company_id: ObjectId) -> None:
    """Hard removal — only used by provisioning teardown (docs/MULTITENANCY.md §3)."""
    await control_db.companies.delete_one({"_id": company_id})
