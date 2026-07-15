"""Inventory module — tenant seed (docs/modules/INVENTORY.md §4). Idempotent."""

from __future__ import annotations

from datetime import UTC, datetime

from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ASCENDING


async def seed(tenant_db: AsyncIOMotorDatabase) -> None:
    await tenant_db.products.create_index("sku", unique=True)
    await tenant_db.products.create_index("is_active")
    await tenant_db.movements.create_index(
        [("product_id", ASCENDING), ("warehouse_id", ASCENDING), ("occurred_at", ASCENDING)]
    )
    await tenant_db.stock_levels.create_index(
        [("product_id", ASCENDING), ("warehouse_id", ASCENDING)], unique=True
    )

    # Default: one `Main WH` warehouse.
    await tenant_db.warehouses.update_one(
        {"code": "WH1"},
        {"$setOnInsert": {
            "name": "Main WH",
            "code": "WH1",
            "address": {},
            "is_active": True,
            "created_at": datetime.now(UTC),
        }},
        upsert=True,
    )
