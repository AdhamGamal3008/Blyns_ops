"""Dashboard module — tenant seed (docs/modules/CLIENT_DASHBOARD.md §5).

Dashboard stores no primary data; it reads other collections. It only needs the
activity_log indexes its feed queries use. Idempotent (create_index is a no-op
when the index exists).
"""

from __future__ import annotations

from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import DESCENDING


async def seed(tenant_db: AsyncIOMotorDatabase) -> None:
    await tenant_db.activity_log.create_index([("occurred_at", DESCENDING)])
    await tenant_db.activity_log.create_index("module")
    await tenant_db.activity_log.create_index("actor_id")
