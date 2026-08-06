"""One-off backfill: re-seed the default client roles across every live tenant so
a newly-added `CLIENT_RESOURCE` (e.g. `projects_analytics`) reaches roles that
were seeded before it existed.

Run from backend/ so .env is picked up:  python ../scripts/backfill_tenant_roles.py

`seed_default_roles` now `$set`-backfills any missing resource key to each system
role's default level, without clobbering a tenant's edited levels (mirrors the
admin-side fix in commit 494abb0). Safe + idempotent to re-run. Only `active`
companies are touched — suspended/deprovisioned tenants may have no live DB.
"""

from __future__ import annotations

import asyncio

from app.core.config import settings
from app.core.db import close_db_manager, get_db_manager, init_db_manager
from app.modules.settings.seed import seed_default_roles


async def main() -> None:
    init_db_manager(settings.mongo_uri)
    dbm = get_db_manager()
    count = 0
    async for company in dbm.control.companies.find({"status": "active"}):
        tenant_db = dbm.tenant(company["db_name"])
        await seed_default_roles(tenant_db)
        count += 1
        print(f"backfilled roles: {company['slug']} ({company['db_name']})")
    print(f"done: {count} active tenant(s)")
    close_db_manager()


if __name__ == "__main__":
    asyncio.run(main())
