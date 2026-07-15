"""Tenant resolution (docs/MULTITENANCY.md §4).

The tenant is NEVER taken from a header/query the client controls — it is
bound to the signed token (`tenant` claim = db_name). Login is the only place
a slug is accepted, to find the tenant before a token exists (Phase 3).

Resolution order at request time:
1. token supplies db_name → 2. load company by db_name (missing →
TENANT_NOT_FOUND) → 3. status != active → TENANT_BLOCKED → 4. hand the tenant
DB handle downstream.
"""

from __future__ import annotations

from dataclasses import dataclass

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.control_plane.companies import repository as companies_repo
from app.core.db import get_db_manager
from app.core.errors import TENANT_BLOCKED, TENANT_NOT_FOUND, DomainError


@dataclass
class TenantContext:
    company: dict
    db: AsyncIOMotorDatabase


async def resolve_tenant(db_name: str) -> TenantContext:
    dbm = get_db_manager()
    company = await companies_repo.get_by_db_name(dbm.control, db_name)
    if company is None:
        raise DomainError(TENANT_NOT_FOUND, "Tenant not found.", http_status=404)
    if company["status"] != "active":
        # Covers blocked / suspended / provisioning / failed: existing tokens
        # are rejected here on every request, not only at login.
        raise DomainError(
            TENANT_BLOCKED,
            "This company is not active.",
            http_status=403,
            details={"status": company["status"]},
        )
    return TenantContext(company=company, db=dbm.tenant(db_name))
