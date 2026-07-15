"""Module seeding registry (docs/MULTITENANCY.md §5).

Each client module exposes `async def seed(tenant_db)` — idempotent, creates
its collections, indexes, and default docs. Provisioning calls them in this
order, filtered by the company's enabled_modules. Enabling a module later runs
its seed() on demand through this same registry.

NOTE: `projects` wires in the PRE-EXISTING seed asset at
app/modules/projects/seed.py (+ stage_definitions.json) — do not regenerate it.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.modules.crm import seed as crm_seed
from app.modules.dashboard import seed as dashboard_seed
from app.modules.finance import seed as finance_seed
from app.modules.inventory import seed as inventory_seed
from app.modules.projects import seed as projects_seed  # existing asset — wired, not recreated
from app.modules.settings import seed as settings_seed

SeedFn = Callable[[AsyncIOMotorDatabase], Awaitable[None]]

# Canonical seeding order (docs/MULTITENANCY.md §5).
SEED_ORDER: list[str] = ["dashboard", "settings", "projects", "crm", "inventory", "finance"]

MODULE_SEEDS: dict[str, SeedFn] = {
    "dashboard": dashboard_seed.seed,
    "settings": settings_seed.seed,
    "projects": projects_seed.seed,
    "crm": crm_seed.seed,
    "inventory": inventory_seed.seed,
    "finance": finance_seed.seed,
}


async def seed_enabled_modules(
    tenant_db: AsyncIOMotorDatabase, enabled_modules: list[str]
) -> list[str]:
    """Run every enabled module's seed() in canonical order; returns what ran."""
    ran: list[str] = []
    for name in SEED_ORDER:
        if name in enabled_modules:
            await MODULE_SEEDS[name](tenant_db)
            ran.append(name)
    return ran
