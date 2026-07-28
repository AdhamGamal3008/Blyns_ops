"""Dashboard module — tenant seed (docs/modules/CLIENT_DASHBOARD.md §5).

Dashboard stores no primary data; it reads other collections. It only needs the
activity_log indexes its feed queries use. Idempotent (create_index is a no-op
when the index exists).
"""

from __future__ import annotations

from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ASCENDING, DESCENDING


async def seed(tenant_db: AsyncIOMotorDatabase) -> None:
    await tenant_db.activity_log.create_index([("occurred_at", DESCENDING)])
    await tenant_db.activity_log.create_index("module")
    await tenant_db.activity_log.create_index("actor_id")
    # Quick-action ranking reads one user's recent events newest-first
    # (docs/QUICK_ACTIONS_PERSONALIZATION_PLAN.md §1); this compound index serves
    # that exact shape. The single-field `actor_id` index above stays for the
    # activity feed's actor filter.
    await tenant_db.activity_log.create_index(
        [("actor_id", ASCENDING), ("occurred_at", DESCENDING)]
    )
    # Per-user quick-action personalization (pins/hides): one doc per user
    # (docs/QUICK_ACTIONS_PERSONALIZATION_PLAN.md Phase 2).
    await tenant_db.quick_action_prefs.create_index("actor_id", unique=True)
