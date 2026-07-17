"""Finance module — tenant seed (docs/modules/FINANCE.md §4). Idempotent."""

from __future__ import annotations

from datetime import UTC, datetime

from motor.motor_asyncio import AsyncIOMotorDatabase

# Starter chart of accounts: (code, name, type)
STARTER_CHART = [
    ("1000", "Cash", "asset"),
    ("1010", "Bank", "asset"),
    ("1100", "Accounts Receivable", "asset"),
    ("2000", "Accounts Payable", "liability"),
    ("2100", "Tax Payable", "liability"),
    ("3000", "Owner Equity", "equity"),
    ("4000", "Sales Income", "income"),
    ("5000", "COGS", "expense"),
]

# Sequential per-tenant numbering counters (INV-%04d, BILL-%04d).
NUMBERING_COUNTERS = ["invoice", "bill"]


async def seed(tenant_db: AsyncIOMotorDatabase) -> None:
    await tenant_db.accounts.create_index("code", unique=True)
    await tenant_db.journal_entries.create_index("date")
    await tenant_db.journal_entries.create_index("source.doc_id")
    await tenant_db.invoices.create_index("status")
    await tenant_db.invoices.create_index("due_date")
    await tenant_db.bills.create_index("due_date")
    await tenant_db.payments.create_index("ref_doc.id")

    # A document number must be unique — §2 mandates a gapless sequence, and a
    # duplicated invoice number is an audit failure. The atomic counter already
    # prevents this through the API; the index defends against anything that
    # writes a number by another path (an import, a migration, a data fix).
    #
    # PARTIAL, not a plain unique index: drafts carry `number: null` until they
    # post, and Mongo treats every missing/null key as the same value — a naive
    # unique index would reject the second draft.
    for coll in (tenant_db.invoices, tenant_db.bills):
        await coll.create_index(
            "number", unique=True,
            partialFilterExpression={"number": {"$type": "string"}},
        )

    now = datetime.now(UTC)
    for code, name, acc_type in STARTER_CHART:
        await tenant_db.accounts.update_one(
            {"code": code},
            {"$setOnInsert": {
                "code": code,
                "name": name,
                "type": acc_type,
                "parent_id": None,
                "is_active": True,
                "currency": "USD",
                "created_at": now,
            }},
            upsert=True,
        )

    for counter in NUMBERING_COUNTERS:
        await tenant_db.counters.update_one(
            {"_id": counter}, {"$setOnInsert": {"seq": 0}}, upsert=True
        )
