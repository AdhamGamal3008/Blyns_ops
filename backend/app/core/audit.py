"""Audit & activity writers (docs/ARCHITECTURE.md §5).

Two writers, same signature shape. Every state-changing ADMIN endpoint calls
write_admin_audit (→ control.admin_audit_log); every state-changing CLIENT
endpoint calls write_activity (→ that tenant's activity_log). The client
Dashboard's activity panel and calendar read from activity_log.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.db import get_db_manager


async def write_admin_audit(
    actor_id: str,
    action: str,
    target: dict[str, Any] | None,
    details: dict[str, Any] | None = None,
) -> None:
    await get_db_manager().control.admin_audit_log.insert_one(
        {
            "actor_id": actor_id,
            "action": action,
            "target": target or {},
            "details": details or {},
            "occurred_at": datetime.now(UTC),
        }
    )


async def write_activity(
    tenant_db: AsyncIOMotorDatabase,
    actor_id: str,
    action: str,
    entity: dict[str, Any] | None,
    details: dict[str, Any] | None = None,
    *,
    actor_name: str | None = None,
    module: str | None = None,
) -> None:
    await tenant_db.activity_log.insert_one(
        {
            "actor_id": actor_id,
            "actor_name": actor_name,
            "action": action,
            "entity": entity or {},
            "module": module,
            "occurred_at": datetime.now(UTC),
            "details": details or {},
        }
    )
