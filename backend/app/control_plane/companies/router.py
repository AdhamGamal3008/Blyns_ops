"""Admin company security/status/employee endpoints (docs/AUTH_RBAC.md §5–6).

Phase 3 mounts the auth-domain routes; companies CRUD/onboarding/seats join
this router in Phase 4 (docs/ADMIN_PORTAL.md).
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.control_plane.companies import service
from app.shared.enums import Level
from app.shared.schemas import envelope
from app.tenant.deps import AdminPrincipal, require_admin

router = APIRouter(prefix="/api/v1/admin/companies", tags=["admin-companies"])


class SecurityBody(BaseModel):
    failed_login_threshold: int = Field(ge=1, le=100)
    lockout_minutes: int = Field(ge=1, le=24 * 60)


class StatusBody(BaseModel):
    status: Literal["active", "blocked", "suspended"]


class BlockBody(BaseModel):
    blocked: bool


@router.patch("/{company_id}/security")
async def patch_security(
    company_id: str,
    body: SecurityBody,
    admin: AdminPrincipal = Depends(require_admin("security_policy", Level.WRITE)),
):
    security = await service.set_company_security(
        company_id, body.failed_login_threshold, body.lockout_minutes,
        actor_id=str(admin.user["_id"]),
    )
    return envelope(security)


@router.patch("/{company_id}/status")
async def patch_status(
    company_id: str,
    body: StatusBody,
    admin: AdminPrincipal = Depends(require_admin("companies", Level.WRITE)),
):
    result = await service.set_company_status(
        company_id, body.status, actor_id=str(admin.user["_id"])
    )
    return envelope(result)


@router.post("/{company_id}/employees/{uid}/unlock")
async def unlock_employee(
    company_id: str,
    uid: str,
    admin: AdminPrincipal = Depends(require_admin("security_policy", Level.WRITE)),
):
    await service.unlock_employee(company_id, uid, actor_id=str(admin.user["_id"]))
    return envelope({"unlocked": True})


@router.post("/{company_id}/employees/{uid}/reset-password")
async def reset_employee_password(
    company_id: str,
    uid: str,
    admin: AdminPrincipal = Depends(require_admin("security_policy", Level.WRITE)),
):
    temp_password = await service.reset_employee_password(
        company_id, uid, actor_id=str(admin.user["_id"])
    )
    return envelope({"temp_password": temp_password, "must_reset_password": True})


@router.patch("/{company_id}/employees/{uid}/block")
async def block_employee(
    company_id: str,
    uid: str,
    body: BlockBody,
    admin: AdminPrincipal = Depends(require_admin("security_policy", Level.WRITE)),
):
    await service.set_employee_blocked(
        company_id, uid, body.blocked, actor_id=str(admin.user["_id"])
    )
    return envelope({"blocked": body.blocked})
