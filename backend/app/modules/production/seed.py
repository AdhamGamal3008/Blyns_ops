"""Production module — tenant seed (docs/PRODUCTION_MODULE_PLAN.md §3). Idempotent.

Seeds the default work centres. These are examples for a cladding / flooring /
joinery factory and are tenant-editable — the material routes and capacities are
starting points, not fixed policy.
"""

from __future__ import annotations

from datetime import UTC, datetime

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.modules.production.repository import STATIONS, WORK_ORDERS

DEFAULT_STATIONS: list[dict] = [
    {"code": "CUT", "name": "Cutting / CNC",
     "material_types": ["panel", "sheet", "timber"], "capacity_units_per_day": 40},
    {"code": "EDGE", "name": "Edgebanding",
     "material_types": ["panel"], "capacity_units_per_day": 60},
    {"code": "ASSY", "name": "Assembly",
     "material_types": ["panel", "timber", "metal"], "capacity_units_per_day": 20},
    {"code": "FIN", "name": "Finishing / Spray",
     "material_types": ["panel", "timber"], "capacity_units_per_day": 25},
    {"code": "QC", "name": "QC Bench",
     "material_types": [], "capacity_units_per_day": 50},
    {"code": "PACK", "name": "Packing",
     "material_types": [], "capacity_units_per_day": 50},
]


async def seed(tenant_db: AsyncIOMotorDatabase) -> None:
    await tenant_db[STATIONS].create_index("code", unique=True)
    await tenant_db[STATIONS].create_index("is_active")

    # Work orders (Phase 1). Unique per tenant; queue/register filter on these.
    await tenant_db[WORK_ORDERS].create_index("code", unique=True)
    await tenant_db[WORK_ORDERS].create_index("project_id")
    await tenant_db[WORK_ORDERS].create_index("status")
    await tenant_db[WORK_ORDERS].create_index("current_station_id")
    await tenant_db[WORK_ORDERS].create_index("due_date")

    now = datetime.now(UTC)
    for station in DEFAULT_STATIONS:
        await tenant_db[STATIONS].update_one(
            {"code": station["code"]},
            {"$setOnInsert": {**station, "is_active": True, "created_at": now}},
            upsert=True,
        )
