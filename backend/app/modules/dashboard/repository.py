"""Dashboard Mongo access (docs/modules/CLIENT_DASHBOARD.md). No business
rules — the service applies RBAC/module filtering. Dashboard stores no
primary data; every query reads other modules' collections."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

# --- KPIs (§1) ---------------------------------------------------------------


async def kpi_open_projects(db: AsyncIOMotorDatabase) -> int:
    return await db.projects.count_documents(
        {"status": "active", "is_deleted": {"$ne": True}}
    )


async def kpi_overdue_tasks(db: AsyncIOMotorDatabase) -> int:
    """Overdue milestone entries on active projects. The PM module (Phase 10)
    refines this with stage/task due dates; the KPI key stays stable."""
    pipeline: list[dict] = [
        {"$match": {"status": "active", "is_deleted": {"$ne": True}}},
        {"$unwind": "$milestone_schedule"},
        {"$match": {"milestone_schedule.due_date": {"$lt": datetime.now(UTC)}}},
        {"$count": "n"},
    ]
    async for doc in db.projects.aggregate(pipeline):
        return doc["n"]
    return 0


async def kpi_open_deals(db: AsyncIOMotorDatabase) -> int:
    return await db.deals.count_documents(
        {"stage": {"$nin": ["won", "lost"]}, "is_deleted": {"$ne": True}}
    )


async def kpi_low_stock_items(db: AsyncIOMotorDatabase) -> int:
    """Delegates to the Inventory module so this KPI and its `/inventory/
    low-stock` list can never disagree about what "low" means."""
    from app.modules.inventory import repository as inventory_repo

    return await inventory_repo.low_stock_count(db)


async def kpi_unpaid_invoices_total(db: AsyncIOMotorDatabase) -> float:
    pipeline: list[dict] = [
        {"$match": {"status": {"$in": ["sent", "partly_paid"]}}},
        {"$group": {
            "_id": None,
            "total": {"$sum": {"$subtract": ["$total", "$paid_amount"]}},
        }},
    ]
    async for doc in db.invoices.aggregate(pipeline):
        return float(doc["total"])
    return 0.0


# --- Calendar (§2) -----------------------------------------------------------


def _event(
    module: str, etype: str, oid: Any, title: str, start: datetime,
    end: datetime | None, all_day: bool, entity_type: str, entity_id: Any,
) -> dict:
    return {
        "id": f"{module}:{etype}:{oid}",
        "source_module": module,
        "type": etype,
        "title": title,
        "start": start,
        "end": end,
        "all_day": all_day,
        "entity_ref": {"module": module, "type": entity_type, "id": str(entity_id)},
        "color_key": module,
    }


async def calendar_projects(db, start: datetime, end: datetime) -> list[dict]:
    """The PM module's full calendar contribution (PROJECT_MANAGEMENT.md §14):
    milestone dates, stage target dates, the Stage-12 delivery date, the
    acclimation window (§8), and gate deadlines."""
    events = []

    def _in_range(d: datetime | None) -> bool:
        return d is not None and start <= d <= end

    async for doc in db.projects.find({"is_deleted": {"$ne": True}}):
        pid, name = doc["_id"], doc["name"]

        for m in doc.get("milestone_schedule") or []:
            if _in_range(m.get("due_date")):
                events.append(_event(
                    "projects", "milestone", f"{pid}:{m['key']}",
                    f"{name} — {m['name']}", m["due_date"], None, True,
                    "project", pid,
                ))

        sched = doc.get("schedule") or {}

        for target in sched.get("stage_targets") or []:
            if _in_range(target.get("due_date")):
                events.append(_event(
                    "projects", "stage_due", f"{pid}:{target['stage_key']}",
                    f"{name} — {target['stage_key']} target", target["due_date"],
                    None, True, "project", pid,
                ))

        if _in_range(sched.get("delivery_date")):
            events.append(_event(
                "projects", "delivery", f"{pid}:delivery",
                f"{name} — delivery", sched["delivery_date"], None, True,
                "project", pid,
            ))

        # acclimation is a window; show it if it overlaps the requested range
        acc_start = sched.get("acclimation_start")
        if acc_start is not None:
            acc_end = sched.get("acclimation_end") or acc_start
            if acc_start <= end and acc_end >= start:
                events.append(_event(
                    "projects", "acclimation", f"{pid}:acclimation",
                    f"{name} — acclimation", acc_start,
                    sched.get("acclimation_end"), True, "project", pid,
                ))

        for gate in sched.get("gate_deadlines") or []:
            if _in_range(gate.get("due_at")):
                events.append(_event(
                    "projects", "gate_due", f"{pid}:{gate['gate_key']}",
                    f"{name} — {gate['gate_key']} due", gate["due_at"], None,
                    False, "project", pid,
                ))

    return events


async def calendar_crm(db, start: datetime, end: datetime) -> list[dict]:
    events = []
    async for doc in db.deals.find({
        "expected_close_date": {"$gte": start, "$lte": end},
        "stage": {"$nin": ["won", "lost"]},
        "is_deleted": {"$ne": True},
    }):
        events.append(_event(
            "crm", "deal_close", doc["_id"], doc["title"],
            doc["expected_close_date"], None, True, "deal", doc["_id"],
        ))
    async for doc in db.crm_activities.find({
        "due_at": {"$gte": start, "$lte": end}, "done": {"$ne": True},
        "is_deleted": {"$ne": True},
    }):
        events.append(_event(
            "crm", "task_due", doc["_id"], doc.get("subject", "CRM activity"),
            doc["due_at"], None, False, "activity", doc["_id"],
        ))
    return events


async def calendar_finance(db, start: datetime, end: datetime) -> list[dict]:
    events = []
    async for doc in db.invoices.find({
        "due_date": {"$gte": start, "$lte": end},
        "status": {"$in": ["sent", "partly_paid"]},
    }):
        events.append(_event(
            "finance", "invoice_due", doc["_id"],
            f"Invoice {doc.get('number', '')} due", doc["due_date"], None, True,
            "invoice", doc["_id"],
        ))
    async for doc in db.bills.find({
        "due_date": {"$gte": start, "$lte": end},
        "status": {"$in": ["sent", "partly_paid"]},
    }):
        events.append(_event(
            "finance", "bill_due", doc["_id"],
            f"Bill {doc.get('number', '')} due", doc["due_date"], None, True,
            "bill", doc["_id"],
        ))
    return events


async def calendar_settings(
    db, start: datetime, end: datetime, user_id: str, role_id: Any
) -> list[dict]:
    """Standalone company events, respecting visibility (SETTINGS.md §1.4)."""
    events = []
    async for doc in db.calendar_events.find({
        "start": {"$gte": start, "$lte": end}, "is_deleted": {"$ne": True},
    }):
        visibility = doc.get("visibility", "company")
        if visibility == "owner" and str(doc.get("created_by")) != user_id:
            continue
        if visibility == "role" and doc.get("role_id") not in (None, role_id):
            continue
        events.append(_event(
            "settings", "company_event", doc["_id"], doc["title"],
            doc["start"], doc.get("end"), bool(doc.get("all_day", True)),
            "calendar_event", doc["_id"],
        ))
    return events


# --- Activity feed (§3) -------------------------------------------------------


async def activity_page(
    db: AsyncIOMotorDatabase,
    query: dict,
    cursor: str | None,
    limit: int,
) -> tuple[list[dict], str | None]:
    if cursor:
        query = {**query, "_id": {"$lt": ObjectId(cursor)}}
    docs = await (
        db.activity_log.find(query).sort("_id", -1).limit(limit)
    ).to_list(length=limit)
    next_cursor = str(docs[-1]["_id"]) if len(docs) == limit else None
    return docs, next_cursor
