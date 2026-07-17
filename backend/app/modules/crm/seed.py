"""CRM module — tenant seed (docs/modules/CRM.md §4). Idempotent.

Collection naming: CRM's customer Account lives in `crm_accounts`, not
`accounts`. CRM.md §4 and FINANCE.md §4 both name `accounts` for two different
entities (customer company vs. chart-of-accounts ledger line), and Finance's
unique `accounts.code` index rejects code-less CRM rows. The `crm_` prefix
follows `crm_activities` and FINANCE.md's own `customer_ref.crm_account_id`.
"""

from __future__ import annotations

from datetime import UTC, datetime

from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ASCENDING

DEFAULT_PIPELINE_STAGES = ["new", "qualified", "proposal", "negotiation", "won", "lost"]


async def seed(tenant_db: AsyncIOMotorDatabase) -> None:
    await tenant_db.crm_accounts.create_index("status")
    await tenant_db.contacts.create_index("account_id")
    await tenant_db.contacts.create_index("email")
    await tenant_db.leads.create_index("status")
    await tenant_db.deals.create_index(
        [("stage", ASCENDING), ("expected_close_date", ASCENDING)]
    )
    await tenant_db.deals.create_index("account_id")
    await tenant_db.crm_activities.create_index("entity_ref.id")
    await tenant_db.crm_activities.create_index("due_at")

    # Default: one `default` pipeline definition doc with ordered stages.
    await tenant_db.pipelines.update_one(
        {"key": "default"},
        {"$setOnInsert": {
            "key": "default",
            "name": "Default",
            "stages": DEFAULT_PIPELINE_STAGES,
            "created_at": datetime.now(UTC),
        }},
        upsert=True,
    )
