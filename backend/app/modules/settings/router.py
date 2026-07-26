"""Settings API (docs/modules/SETTINGS.md §2) + the approver-role map editor
(PROJECT_MANAGEMENT.md §9 lives in Settings).

GET → settings READ; every mutation → settings WRITE (§1.2: the client-side
security actions are gated by settings WRITE — the client realm's
security_policy concept folds into it).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.modules.settings import service
from app.modules.settings.models import (
    ApproverMapPatch,
    CalendarEventCreate,
    CalendarEventPatch,
    CompanyProfilePatch,
    EmployeeBlockBody,
    EmployeeCreate,
    EmployeePatch,
    RoleCreate,
    RolePatch,
)
from app.shared.enums import Level
from app.shared.schemas import envelope, to_api
from app.tenant.deps import ClientPrincipal, require

router = APIRouter(prefix="/api/v1/settings", tags=["client-settings"])

_read = require("settings", Level.READ)
_write = require("settings", Level.WRITE)


# --- company profile ---------------------------------------------------------

@router.get("/company")
async def get_company(principal: ClientPrincipal = Depends(_read)):
    return envelope(to_api(await service.get_company_profile(principal)))


@router.patch("/company")
async def patch_company(
    body: CompanyProfilePatch, principal: ClientPrincipal = Depends(_write)
):
    return envelope(to_api(await service.patch_company_profile(principal, body)))


# --- employees -----------------------------------------------------------------

@router.get("/employees")
async def list_employees(principal: ClientPrincipal = Depends(_read)):
    return envelope(to_api(await service.list_employees(principal)))


@router.post("/employees", status_code=201)
async def create_employee(
    body: EmployeeCreate, principal: ClientPrincipal = Depends(_write)
):
    return envelope(await service.create_employee(principal, body))


@router.patch("/employees/{uid}")
async def patch_employee(
    uid: str, body: EmployeePatch, principal: ClientPrincipal = Depends(_write)
):
    return envelope(to_api(await service.patch_employee(principal, uid, body)))


@router.post("/employees/{uid}/reset-password")
async def reset_employee_password(
    uid: str, principal: ClientPrincipal = Depends(_write)
):
    temp = await service.reset_employee_password(principal, uid)
    return envelope({"temp_password": temp, "must_reset_password": True})


@router.post("/employees/{uid}/unlock")
async def unlock_employee(uid: str, principal: ClientPrincipal = Depends(_write)):
    await service.unlock_employee(principal, uid)
    return envelope({"unlocked": True})


@router.patch("/employees/{uid}/block")
async def block_employee(
    uid: str, body: EmployeeBlockBody, principal: ClientPrincipal = Depends(_write)
):
    await service.block_employee(principal, uid, body.blocked)
    return envelope({"blocked": body.blocked})


# --- client roles ----------------------------------------------------------------

@router.get("/csv-catalog")
async def csv_catalog(principal: ClientPrincipal = Depends(_read)):
    """Every import/export tab, for the role editor's CSV-grant multi-selects."""
    return envelope(service.csv_catalog())


@router.get("/roles")
async def list_roles(principal: ClientPrincipal = Depends(_read)):
    return envelope(to_api(await service.list_roles(principal)))


@router.post("/roles", status_code=201)
async def create_role(
    body: RoleCreate, principal: ClientPrincipal = Depends(_write)
):
    return envelope(to_api(await service.create_role(principal, body)))


@router.patch("/roles/{role_id}")
async def patch_role(
    role_id: str, body: RolePatch, principal: ClientPrincipal = Depends(_write)
):
    return envelope(to_api(await service.patch_role(principal, role_id, body)))


@router.delete("/roles/{role_id}")
async def delete_role(role_id: str, principal: ClientPrincipal = Depends(_write)):
    await service.delete_role(principal, role_id)
    return envelope({"deleted": True})


# --- calendar events ---------------------------------------------------------------

@router.get("/calendar-events")
async def list_events(principal: ClientPrincipal = Depends(_read)):
    return envelope(to_api(await service.list_calendar_events(principal)))


@router.post("/calendar-events", status_code=201)
async def create_event(
    body: CalendarEventCreate, principal: ClientPrincipal = Depends(_write)
):
    return envelope(to_api(await service.create_calendar_event(principal, body)))


@router.patch("/calendar-events/{event_id}")
async def patch_event(
    event_id: str, body: CalendarEventPatch,
    principal: ClientPrincipal = Depends(_write),
):
    return envelope(to_api(await service.patch_calendar_event(principal, event_id, body)))


@router.delete("/calendar-events/{event_id}")
async def delete_event(event_id: str, principal: ClientPrincipal = Depends(_write)):
    await service.delete_calendar_event(principal, event_id)
    return envelope({"deleted": True})


# --- security & modules (read views) --------------------------------------------

@router.get("/security")
async def get_security(principal: ClientPrincipal = Depends(_read)):
    return envelope(service.get_security_view(principal))


@router.get("/modules")
async def get_modules(principal: ClientPrincipal = Depends(_read)):
    return envelope(service.get_modules_view(principal))


# --- approver map ----------------------------------------------------------------

@router.get("/approver-roles")
async def list_approver_roles(principal: ClientPrincipal = Depends(_read)):
    return envelope(to_api(await service.list_approver_map(principal)))


@router.patch("/approver-roles/{approver_role}")
async def patch_approver_role(
    approver_role: str, body: ApproverMapPatch,
    principal: ClientPrincipal = Depends(_write),
):
    return envelope(
        to_api(await service.patch_approver_map(principal, approver_role, body))
    )
