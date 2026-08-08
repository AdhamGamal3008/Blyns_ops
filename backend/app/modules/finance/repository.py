"""Finance Mongo access (docs/modules/FINANCE.md). No business rules — the
service owns posting, balancing and status math.

Collection names match what the Phase 5 dashboard already reads (`invoices`,
`bills`) — see modules/dashboard/repository.py.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

ACCOUNTS = "accounts"          # the chart of accounts (CRM customers = crm_accounts)
JOURNAL = "journal_entries"
INVOICES = "invoices"
BILLS = "bills"
PAYMENTS = "payments"
COUNTERS = "counters"

_LIVE = {"is_deleted": {"$ne": True}}


def _now() -> datetime:
    return datetime.now(UTC)


async def insert(db: AsyncIOMotorDatabase, coll: str, doc: dict) -> dict:
    now = _now()
    doc.setdefault("created_at", now)
    doc.setdefault("updated_at", now)
    doc.setdefault("is_deleted", False)
    result = await db[coll].insert_one(doc)
    doc["_id"] = result.inserted_id
    return doc


async def get(db: AsyncIOMotorDatabase, coll: str, oid: ObjectId) -> dict | None:
    return await db[coll].find_one({"_id": oid, **_LIVE})


async def list_docs(
    db: AsyncIOMotorDatabase, coll: str, query: dict, skip: int = 0,
    limit: int = 25, sort: list[tuple[str, int]] | None = None,
) -> tuple[list[dict], int]:
    filt = {**query, **_LIVE}
    total = await db[coll].count_documents(filt)
    cursor = db[coll].find(filt).sort(sort or [("created_at", -1)]).skip(skip).limit(limit)
    return await cursor.to_list(length=limit), total


async def update(
    db: AsyncIOMotorDatabase, coll: str, oid: ObjectId, fields: dict
) -> dict | None:
    fields["updated_at"] = _now()
    await db[coll].update_one({"_id": oid}, {"$set": fields})
    return await get(db, coll, oid)


async def soft_delete(
    db: AsyncIOMotorDatabase, coll: str, oid: ObjectId, actor_id: str
) -> None:
    await db[coll].update_one(
        {"_id": oid},
        {"$set": {"is_deleted": True, "deleted_at": _now(), "updated_by": actor_id}},
    )


async def account_by_code(db: AsyncIOMotorDatabase, code: str) -> dict | None:
    return await db[ACCOUNTS].find_one({"code": code, **_LIVE})


# --- numbering (§2) ----------------------------------------------------------

async def next_number(db: AsyncIOMotorDatabase, counter: str, prefix: str) -> str:
    """Claim the next sequential number atomically.

    `find_one_and_update` with `$inc` is atomic on the counter document, so two
    concurrent posts can never take the same number. The seed creates the
    counters; upsert covers a tenant provisioned before one existed.
    """
    doc = await db[COUNTERS].find_one_and_update(
        {"_id": counter}, {"$inc": {"seq": 1}}, upsert=True, return_document=True,
    )
    return f"{prefix}-{int(doc['seq']):04d}"


# --- reports (§2) ------------------------------------------------------------

async def trial_balance(
    db: AsyncIOMotorDatabase, start: datetime | None, end: datetime | None
) -> list[dict]:
    """Sum debits/credits per account over the posted ledger."""
    match: dict[str, Any] = {"posted": True, **_LIVE}
    if start or end:
        date: dict[str, Any] = {}
        if start:
            date["$gte"] = start
        if end:
            date["$lte"] = end
        match["date"] = date
    agg: list[dict] = [
        {"$match": match},
        {"$unwind": "$lines"},
        {"$group": {
            "_id": "$lines.account_id",
            "debit": {"$sum": "$lines.debit"},
            "credit": {"$sum": "$lines.credit"},
        }},
        {"$lookup": {
            "from": ACCOUNTS, "localField": "_id",
            "foreignField": "_id", "as": "account",
        }},
        {"$unwind": "$account"},
        {"$sort": {"account.code": 1}},
    ]
    return [doc async for doc in db[JOURNAL].aggregate(agg)]


async def aging_rows(
    db: AsyncIOMotorDatabase, coll: str, open_statuses: list[str]
) -> list[dict]:
    """Open AR/AP documents with their outstanding balance."""
    agg: list[dict] = [
        {"$match": {"status": {"$in": open_statuses}, **_LIVE}},
        {"$addFields": {
            "outstanding": {"$subtract": ["$total", {"$ifNull": ["$paid_amount", 0]}]},
        }},
        {"$match": {"outstanding": {"$gt": 0}}},
        {"$sort": {"due_date": 1}},
    ]
    return [doc async for doc in db[coll].aggregate(agg)]


async def entries_for_doc(db: AsyncIOMotorDatabase, doc_id: str) -> list[dict]:
    return [
        d async for d in db[JOURNAL].find({"source.doc_id": doc_id, **_LIVE})
        .sort([("created_at", 1)])
    ]


# --- analytics aggregations (docs/PROJECT_ANALYTICS_PLAN.md §6-D, Finance) ----
# Read-only rollups over invoices/bills. AR/AP outstanding + aging reuse
# aging_rows (open docs with a positive outstanding balance).

async def analytics_status_totals(
    db: AsyncIOMotorDatabase, coll: str
) -> dict[str, dict]:
    """Invoices or bills grouped by status → {status: {count, total}}."""
    agg: list[dict] = [
        {"$match": _LIVE},
        {"$group": {"_id": "$status", "count": {"$sum": 1}, "total": {"$sum": "$total"}}},
    ]
    return {
        d["_id"]: {"count": int(d["count"]), "total": float(d["total"] or 0)}
        async for d in db[coll].aggregate(agg) if d["_id"]
    }


async def analytics_monthly_totals(
    db: AsyncIOMotorDatabase, coll: str, statuses: list[str], since: datetime
) -> dict[str, float]:
    """Σ total per 'YYYY-MM' of issue_date, over the given statuses, from `since`."""
    agg: list[dict] = [
        {"$match": {**_LIVE, "status": {"$in": statuses}, "issue_date": {"$gte": since}}},
        {"$group": {
            "_id": {"$dateToString": {"format": "%Y-%m", "date": "$issue_date"}},
            "total": {"$sum": "$total"},
        }},
    ]
    return {
        d["_id"]: float(d["total"] or 0)
        async for d in db[coll].aggregate(agg) if d["_id"]
    }
