"""Tenant resolution (docs/MULTITENANCY.md §4)."""

from __future__ import annotations

import pytest

from app.control_plane.companies.models import OnboardCompanyPayload, OwnerPayload
from app.control_plane.provisioning.engine import onboard_company
from app.core.db import close_db_manager, init_db_manager
from app.core.errors import DomainError
from app.tenant.context import resolve_tenant


@pytest.fixture
async def engine_db(mongo_uri):
    manager = init_db_manager(mongo_uri)
    yield manager
    close_db_manager()


async def _onboard(slug: str):
    return await onboard_company(OnboardCompanyPayload(
        name=slug, slug=slug, seat_limit=5,
        enabled_modules=["dashboard", "settings"],
        owner=OwnerPayload(name="O", email=f"o@{slug}.com"),
    ))


async def test_active_company_resolves(engine_db):
    await _onboard("ctx-active")
    ctx = await resolve_tenant("test_tenant_ctx-active")
    assert ctx.company["slug"] == "ctx-active"
    assert ctx.db.name == "test_tenant_ctx-active"


async def test_unknown_db_name_is_tenant_not_found(engine_db):
    with pytest.raises(DomainError) as exc:
        await resolve_tenant("test_tenant_nope")
    assert exc.value.code == "TENANT_NOT_FOUND"
    assert exc.value.http_status == 404


async def test_non_active_statuses_are_tenant_blocked(engine_db):
    result = await _onboard("ctx-blocked")
    for status in ("blocked", "suspended", "provisioning", "failed"):
        await engine_db.control.companies.update_one(
            {"_id": result.company["_id"]}, {"$set": {"status": status}}
        )
        with pytest.raises(DomainError) as exc:
            await resolve_tenant("test_tenant_ctx-blocked")
        assert exc.value.code == "TENANT_BLOCKED"
        assert exc.value.http_status == 403
        assert exc.value.details["status"] == status
