"""One-off migration: bring every live tenant's Projects stage machine up to
machine_version 4 (docs/PROJECT_CONFIGURATIONS_PLAN.md, Phase 0).

v4 makes the two fixed workflow templates the seeded **Standard** and
**Concurrent** system configurations, and scopes every stage definition and gate
rule to a `(configuration_id, config_version)`. The stage skeleton is unchanged —
same nine keys, same orders — so this migration is non-destructive:

  * re-running the projects seed creates the two system configs and ADOPTS the
    tenant's existing definitions (including any edits it made to stage names,
    approvers or gate thresholds) into them at version 1;
  * existing projects are then PINNED to the system config matching the
    `workflow_type` they already carry, at version 1, so a future published
    version cannot move them (D1/G-5);
  * runtime collections — stage_instances, gate_results, approvals — are never
    touched, so in-flight projects keep their state.

Run from backend/ so .env is picked up:  python ../scripts/migrate_projects_v4.py
Idempotent and safe to re-run. Only `active` companies with projects enabled.
"""

from __future__ import annotations

import asyncio

from app.core.config import settings
from app.core.db import close_db_manager, get_db_manager, init_db_manager
from app.modules.projects import seed as projects_seed

# Mongo's `{field: null}` matches BOTH an explicit null and a missing field, so a
# single query covers projects created before `configuration_id` existed and those
# created on an un-migrated tenant (which persist it as None).
_UNPINNED = {"configuration_id": None}


def _shape_query(workflow_shape: str) -> dict:
    """Projects belonging to a workflow shape. 'sequential' also claims projects
    with no workflow_type at all — those predate the concurrent feature."""
    if workflow_shape == "sequential":
        return {"$or": [{"workflow_type": "sequential"},
                        {"workflow_type": {"$exists": False}}]}
    return {"workflow_type": workflow_shape}


async def _pin_projects(tenant_db, configs: dict[str, dict]) -> int:
    """Give every unpinned project the configuration matching its workflow_type, at
    version 1 — the version the seed just stamped this tenant's definitions with."""
    pinned = 0
    for workflow_shape, config in configs.items():
        result = await tenant_db.projects.update_many(
            {**_UNPINNED, **_shape_query(workflow_shape)},
            {"$set": {
                "configuration_id": config["_id"],
                "config_version": 1,
                "workflow_type": workflow_shape,
            }},
        )
        pinned += result.modified_count
    return pinned


async def main() -> None:
    init_db_manager(settings.mongo_uri)
    dbm = get_db_manager()
    count = 0
    async for company in dbm.control.companies.find({"status": "active"}):
        if "projects" not in (company.get("enabled_modules") or []):
            continue
        tenant_db = dbm.tenant(company["db_name"])
        await projects_seed.seed(tenant_db)

        configs = {
            c["workflow_shape"]: c
            async for c in tenant_db.project_configurations.find({"is_system": True})
        }
        if len(configs) != 2:
            print(f"SKIPPED {company['slug']}: expected 2 system configs, "
                  f"found {len(configs)}")
            continue

        pinned = await _pin_projects(tenant_db, configs)
        stages = await tenant_db.stage_definitions.count_documents(
            {"configuration_id": {"$ne": None}}
        )
        gates = await tenant_db.gate_rules.count_documents(
            {"configuration_id": {"$ne": None}}
        )
        unpinned = await tenant_db.projects.count_documents(
            {**_UNPINNED, "is_deleted": {"$ne": True}}
        )
        count += 1
        print(
            f"migrated: {company['slug']} ({company['db_name']}) — "
            f"2 system configs, {stages} scoped stages, {gates} scoped gate rules, "
            f"{pinned} project(s) pinned, {unpinned} still unpinned"
        )
    print(f"done: {count} projects-enabled tenant(s)")
    close_db_manager()


if __name__ == "__main__":
    asyncio.run(main())
