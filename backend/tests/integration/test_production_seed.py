"""Production module Phase 0 wiring (docs/PRODUCTION_MODULE_PLAN.md §7).

Proves the new module is a known, seedable module, that it seeds its work centres
idempotently, and that the `production` + `production_analytics` RBAC resources
reach the seeded roles at their intended levels.
"""

from __future__ import annotations

import pytest

from app.control_plane.companies.models import (
    KNOWN_MODULES,
    OnboardCompanyPayload,
    OwnerPayload,
)
from app.control_plane.provisioning.engine import onboard_company
from app.core.db import close_db_manager, init_db_manager
from app.modules.production import seed as production_seed
from app.modules.production.seed import DEFAULT_STATIONS
from app.shared.enums import Level


@pytest.fixture
async def engine_db(mongo_uri):
    """The engine uses the process-global DBManager (mirrors test_provisioning)."""
    manager = init_db_manager(mongo_uri)
    yield manager
    close_db_manager()


def _payload(slug: str) -> OnboardCompanyPayload:
    # enabled_modules defaults to KNOWN_MODULES, which now includes production.
    return OnboardCompanyPayload(
        name=f"{slug.title()} Corp",
        slug=slug,
        seat_limit=10,
        owner=OwnerPayload(name="Jane Doe", email=f"jane@{slug}.com"),
    )


def test_production_is_a_known_module():
    assert "production" in KNOWN_MODULES


async def test_onboarding_seeds_production_stations(engine_db):
    await onboard_company(_payload("prod1"), actor_id="admin-test")
    t = engine_db.tenant("test_tenant_prod1")

    assert await t.production_stations.count_documents({}) == len(DEFAULT_STATIONS)
    codes = {s["code"] async for s in t.production_stations.find({})}
    assert {"CUT", "QC", "PACK"} <= codes

    # idempotent: re-running the seed adds nothing
    await production_seed.seed(t)
    assert await t.production_stations.count_documents({}) == len(DEFAULT_STATIONS)


async def test_only_enabled_production_is_seeded(engine_db):
    await onboard_company(
        _payload_without_production("prod-off"), actor_id="admin-test"
    )
    t = engine_db.tenant("test_tenant_prod-off")
    assert await t.production_stations.count_documents({}) == 0


def _payload_without_production(slug: str) -> OnboardCompanyPayload:
    return OnboardCompanyPayload(
        name=f"{slug.title()} Corp",
        slug=slug,
        seat_limit=10,
        enabled_modules=["dashboard", "settings", "projects"],
        owner=OwnerPayload(name="Jane Doe", email=f"jane@{slug}.com"),
    )


async def test_seeded_roles_carry_production_resources(engine_db):
    await onboard_company(_payload("prod2"), actor_id="admin-test")
    t = engine_db.tenant("test_tenant_prod2")
    roles = {r["name"]: r["permissions"] async for r in t.roles.find({})}

    assert roles["Owner"]["production"] == int(Level.WRITE)
    assert roles["Owner"]["production_analytics"] == int(Level.WRITE)
    assert roles["Manager"]["production"] == int(Level.WRITE)
    assert roles["Manager"]["production_analytics"] == int(Level.READ)
    assert roles["Member"]["production"] == int(Level.WRITE)
    # Viewer gets neither the module nor its analytics by default.
    assert roles["Viewer"]["production"] == int(Level.NONE)
    assert roles["Viewer"]["production_analytics"] == int(Level.NONE)
