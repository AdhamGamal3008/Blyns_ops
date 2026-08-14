"""One-off migration: bring every live tenant's Projects stage machine up to
machine_version 3 (docs/CONCURRENT_WORKFLOW_PLAN.md).

A tenant seeded before v3 carries only the old sequential stages — no
`workflow_type`, no concurrent template, and a stage-4 that relied on the (now
removed) hard-coded linear loop. That leaves two latent bugs: a concurrent
project cannot advance (its template is missing), and a sequential project's
stage 4 would open early. Re-running the projects seed reseeds the DEFINITION
collections to v3 (both templates + the explicit stage-4 dependency); runtime
collections — projects, stage_instances, gate_results, approvals — are never
touched, so in-flight projects keep their state and their stage keys/orders are
unchanged.

Run from backend/ so .env is picked up:  python ../scripts/migrate_projects_v3.py
Idempotent and safe to re-run. Only `active` companies with projects enabled.
"""

from __future__ import annotations

import asyncio

from app.core.config import settings
from app.core.db import close_db_manager, get_db_manager, init_db_manager
from app.modules.projects import seed as projects_seed


async def main() -> None:
    init_db_manager(settings.mongo_uri)
    dbm = get_db_manager()
    count = 0
    async for company in dbm.control.companies.find({"status": "active"}):
        if "projects" not in (company.get("enabled_modules") or []):
            continue
        tenant_db = dbm.tenant(company["db_name"])
        await projects_seed.seed(tenant_db)
        seq = await tenant_db.stage_definitions.count_documents(
            {"workflow_type": "sequential"}
        )
        con = await tenant_db.stage_definitions.count_documents(
            {"workflow_type": "concurrent"}
        )
        count += 1
        print(
            f"migrated: {company['slug']} ({company['db_name']}) — "
            f"{seq} sequential + {con} concurrent stages"
        )
    print(f"done: {count} projects-enabled tenant(s)")
    close_db_manager()


if __name__ == "__main__":
    asyncio.run(main())
