"""Versioned migration runner (docs/ENVIRONMENTS.md §4, DEPLOYMENT_PLAN.md Phase B).

The spec has always promised this; until now there were only ad-hoc scripts
(`migrate_projects_v3.py`, `migrate_projects_v4.py`, `backfill_tenant_roles.py`)
that someone had to remember to run, in an order only they knew. That is exactly
how a tenant ends up on a stale stage machine after a deploy.

How it works
------------
* Migrations are registered below **in order**, each with a stable `id`.
* Applied ids are recorded in the CONTROL database (`migrations`), so a migration
  runs once per deployment and re-running the command is a no-op.
* Every migration must be **idempotent anyway** — the record is an optimisation
  and an audit trail, not the safety mechanism. If the record is ever lost, a
  re-run must still be safe.
* Tenant-scoped migrations iterate `active` companies themselves; suspended or
  deprovisioned tenants may have no live database.

Usage (run from backend/ so .env is picked up):
    python ../scripts/migrate.py --dry-run     # what would run, changes nothing
    python ../scripts/migrate.py               # apply everything pending
    python ../scripts/migrate.py --list        # every known migration + state
    python ../scripts/migrate.py --force <id>  # re-apply one, already-applied or not

On deploy: start the new image, then run this before announcing the release.
"""

from __future__ import annotations

import argparse
import asyncio
import traceback
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.config import settings
from app.core.db import close_db_manager, get_db_manager, init_db_manager

MIGRATIONS_COLLECTION = "migrations"


@dataclass(frozen=True)
class Migration:
    """One ordered, idempotent step.

    `run` receives the DbManager so a migration can reach the control plane, the
    tenants, or both — the three existing scripts need all three shapes.
    """

    id: str
    description: str
    run: Callable[..., Awaitable[str]]


# --- individual migrations ----------------------------------------------------
# Each returns a one-line summary of what it did, for the log.


async def _projects_machine_v4(dbm) -> str:
    """Projects stage machine → machine_version 4: the two system project
    configurations, definitions scoped to (configuration_id, config_version), and
    every existing project pinned to the configuration matching its workflow_type
    (docs/PROJECT_CONFIGURATIONS_PLAN.md Phase 0).

    Wraps scripts/migrate_projects_v4.py so there is ONE way to run it.
    """
    from app.modules.projects import seed as projects_seed

    tenants = 0
    pinned_total = 0
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
            raise RuntimeError(
                f"{company['slug']}: expected 2 system configurations, found "
                f"{len(configs)} — refusing to pin projects against a bad seed"
            )

        for shape, config in configs.items():
            # Mongo's {field: null} matches both an explicit null and a missing
            # field, so this covers projects from before the field existed.
            shape_query = (
                {"$or": [{"workflow_type": "sequential"},
                         {"workflow_type": {"$exists": False}}]}
                if shape == "sequential"
                else {"workflow_type": shape}
            )
            result = await tenant_db.projects.update_many(
                {"configuration_id": None, **shape_query},
                {"$set": {"configuration_id": config["_id"], "config_version": 1,
                          "workflow_type": shape}},
            )
            pinned_total += result.modified_count
        tenants += 1
    return f"{tenants} projects-enabled tenant(s); {pinned_total} project(s) pinned"


async def _backfill_client_roles(dbm) -> str:
    """Re-seed default client roles so resources added after a tenant was created
    (e.g. `projects_analytics`) reach its system roles. `$set`-backfills only the
    missing keys, so a tenant's edited levels are preserved."""
    from app.modules.settings.seed import seed_default_roles

    tenants = 0
    async for company in dbm.control.companies.find({"status": "active"}):
        await seed_default_roles(dbm.tenant(company["db_name"]))
        tenants += 1
    return f"{tenants} active tenant(s) backfilled"


# --- the ordered registry -----------------------------------------------------
# APPEND ONLY. Never reorder, never rewrite an id: ids already recorded in a live
# control database are what tell the runner a step is done.
MIGRATIONS: list[Migration] = [
    Migration(
        id="0001_backfill_client_roles",
        description="Backfill newly-added client RBAC resources onto system roles",
        run=_backfill_client_roles,
    ),
    Migration(
        id="0002_projects_machine_v4",
        description="Projects machine v4: system configurations + pin every project",
        run=_projects_machine_v4,
    ),
]


# --- runner -------------------------------------------------------------------

async def _applied_ids(control: AsyncIOMotorDatabase) -> set[str]:
    return {
        doc["_id"] async for doc in control[MIGRATIONS_COLLECTION].find({}, {"_id": 1})
    }


async def _record(control: AsyncIOMotorDatabase, migration: Migration, summary: str) -> None:
    await control[MIGRATIONS_COLLECTION].update_one(
        {"_id": migration.id},
        {"$set": {
            "description": migration.description,
            "applied_at": datetime.now(UTC),
            "summary": summary,
        }},
        upsert=True,
    )


async def run(dry_run: bool, only: str | None, show_list: bool) -> int:
    init_db_manager(settings.mongo_uri)
    dbm = get_db_manager()
    try:
        applied = await _applied_ids(dbm.control)

        if show_list:
            print(f"{'STATE':<9} {'ID':<32} DESCRIPTION")
            for migration in MIGRATIONS:
                state = "applied" if migration.id in applied else "PENDING"
                print(f"{state:<9} {migration.id:<32} {migration.description}")
            return 0

        if only is not None:
            selected = [m for m in MIGRATIONS if m.id == only]
            if not selected:
                known = ", ".join(m.id for m in MIGRATIONS)
                print(f"unknown migration '{only}'. Known: {known}")
                return 2
        else:
            selected = [m for m in MIGRATIONS if m.id not in applied]

        if not selected:
            print("nothing pending — every migration is already applied")
            return 0

        verb = "would apply" if dry_run else "applying"
        print(f"{verb} {len(selected)} migration(s) against {settings.mongo_uri.split('@')[-1]}")

        for migration in selected:
            if dry_run:
                print(f"  [dry-run] {migration.id} — {migration.description}")
                continue
            print(f"  {migration.id} — {migration.description}")
            try:
                summary = await migration.run(dbm)
            except Exception:
                # Stop at the first failure: later migrations may assume this one
                # landed, and a half-migrated deployment is worse than a stopped
                # one. The step is not recorded, so a re-run retries it.
                print(f"  FAILED: {migration.id}")
                traceback.print_exc()
                return 1
            await _record(dbm.control, migration, summary)
            print(f"    ok — {summary}")

        print("done" if not dry_run else "dry run complete — nothing was changed")
        return 0
    finally:
        close_db_manager()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true",
                        help="report what would run; change nothing")
    parser.add_argument("--list", dest="show_list", action="store_true",
                        help="show every known migration and whether it is applied")
    parser.add_argument("--force", metavar="ID",
                        help="run one migration by id, applied or not")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(run(args.dry_run, args.force, args.show_list)))


if __name__ == "__main__":
    main()
