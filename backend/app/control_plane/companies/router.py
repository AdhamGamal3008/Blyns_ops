"""Admin companies API (docs/ADMIN_PORTAL.md §1–2 + AUTH_RBAC.md §5–6):
onboarding, list/detail, edit, seats, employees, provisioning progress,
teardown, and the security/status/employee-security actions.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from app.control_plane.companies import service
from app.control_plane.companies.models import (
    AdminEmployeeCreate,
    OnboardCompanyPayload,
    SeatLimitBody,
    UpdateCompanyPayload,
)
from app.control_plane.companies.repository import list_companies
from app.control_plane.provisioning.engine import onboard_company, teardown_company
from app.core.db import get_db_manager
from app.core.errors import VALIDATION_ERROR, DomainError
from app.shared.enums import Level
from app.shared.schemas import PaginationParams, envelope, page_meta, to_api
from app.tenant.deps import AdminPrincipal, require_admin

router = APIRouter(prefix="/api/v1/admin/companies", tags=["admin-companies"])

_SENSITIVE_COMPANY_FIELDS = ("security",)


def _company_view(company: dict, level: Level) -> dict:
    """VIEW sees it exists (labels); READ+ gets the full document
    (docs/AUTH_RBAC.md §2)."""
    if level == Level.VIEW:
        return {k: company.get(k) for k in ("_id", "name", "slug", "status")}
    return company


@router.get("")
async def list_all(
    params: PaginationParams = Depends(),
    status: str | None = Query(default=None),
    q: str | None = Query(default=None, description="search name/slug"),
    admin: AdminPrincipal = Depends(require_admin("companies", Level.VIEW)),
):
    docs, total = await list_companies(
        get_db_manager().control, status, q, params.skip, params.page_size
    )
    level = admin.level_for("companies")
    return envelope(
        [to_api(_company_view(d, level)) for d in docs],
        meta=page_meta(params.page, params.page_size, total),
    )


@router.post("", status_code=201)
async def onboard(
    payload: OnboardCompanyPayload,
    admin: AdminPrincipal = Depends(require_admin("companies", Level.WRITE)),
):
    """Onboard a company: reserve → provision+seed tenant DB → Owner user.
    The temp password is returned ONCE and never stored."""
    result = await onboard_company(payload, actor_id=str(admin.user["_id"]))
    return envelope({
        "company": to_api(result.company),
        "provisioning_job_id": str(result.job["_id"]),
        "owner_temp_password": result.owner_temp_password,
    })


@router.get("/{company_id}")
async def detail(
    company_id: str,
    admin: AdminPrincipal = Depends(require_admin("companies", Level.READ)),
):
    return envelope(to_api(await service.get_company_detail(company_id)))


@router.patch("/{company_id}")
async def update(
    company_id: str,
    payload: UpdateCompanyPayload,
    admin: AdminPrincipal = Depends(require_admin("companies", Level.WRITE)),
):
    company = await service.update_company(
        company_id, payload, actor_id=str(admin.user["_id"])
    )
    return envelope(to_api(company))


@router.delete("/{company_id}")
async def teardown(
    company_id: str,
    confirm: str = Query(description="must equal the company slug"),
    hard: bool = Query(default=False),
    admin: AdminPrincipal = Depends(require_admin("companies", Level.WRITE)),
):
    """Teardown (docs/ADMIN_PORTAL.md §1): requires the slug as a confirmation
    token. hard=true removes the registry doc too."""
    from app.control_plane.companies.service import _load_company

    company = await _load_company(get_db_manager().control, company_id)
    if confirm != company["slug"]:
        raise DomainError(
            VALIDATION_ERROR, "Confirmation token does not match the company slug.",
            http_status=409,
        )
    job = await teardown_company(company_id, hard=hard, actor_id=str(admin.user["_id"]))
    return envelope(to_api(job))


@router.patch("/{company_id}/seats")
async def patch_seats(
    company_id: str,
    body: SeatLimitBody,
    admin: AdminPrincipal = Depends(require_admin("seats", Level.WRITE)),
):
    result = await service.set_seat_limit(
        company_id, body.seat_limit, body.force, actor_id=str(admin.user["_id"])
    )
    return envelope(result)


@router.get("/{company_id}/provisioning")
async def provisioning_progress(
    company_id: str,
    admin: AdminPrincipal = Depends(require_admin("provisioning", Level.READ)),
):
    return envelope(to_api(await service.get_latest_provisioning_job(company_id)))


@router.get("/{company_id}/employees")
async def get_employees(
    company_id: str,
    admin: AdminPrincipal = Depends(require_admin("companies", Level.READ)),
):
    return envelope(to_api(await service.list_employees(company_id)))


@router.post("/{company_id}/employees", status_code=201)
async def post_employee(
    company_id: str,
    payload: AdminEmployeeCreate,
    admin: AdminPrincipal = Depends(require_admin("seats", Level.WRITE)),
):
    return envelope(
        await service.create_employee(company_id, payload, str(admin.user["_id"]))
    )


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
