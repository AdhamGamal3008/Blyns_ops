"""Settings business logic (docs/modules/SETTINGS.md).

Every write goes to the tenant activity_log (CLAUDE.md rule 4). Seat limits
are enforced against the CONTROL PLANE company doc — the client side can
never outgrow what the platform granted (§1.2). Blocked users still occupy a
seat (documented choice, docs/ADMIN_PORTAL.md §2).
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime

from bson import ObjectId

from app.auth.service import revoke_all_refresh
from app.control_plane.companies import repository as companies_repo
from app.core.audit import write_activity
from app.core.db import get_db_manager
from app.core.errors import (
    SEAT_LIMIT_REACHED,
    TENANT_NOT_FOUND,
    VALIDATION_ERROR,
    DomainError,
)
from app.core.security import hash_password
from app.modules.settings.models import (
    ApproverMapPatch,
    CalendarEventCreate,
    CalendarEventPatch,
    CompanyProfilePatch,
    EmployeeCreate,
    EmployeePatch,
    RoleCreate,
    RolePatch,
)
from app.modules.settings.seed import CLIENT_RESOURCES
from app.shared import csv_access
from app.shared.enums import Level
from app.tenant.deps import ClientPrincipal

_EMPLOYEE_PROJECTION = {"password_hash": 0, "refresh_jtis": 0}


async def _log(
    principal: ClientPrincipal, action: str, entity: dict,
    details: dict | None = None,
) -> None:
    await write_activity(
        principal.tenant_db,
        actor_id=str(principal.user["_id"]),
        action=action,
        entity=entity,
        details=details or {},
        actor_name=principal.user["name"],
        module="settings",
    )


def validate_client_permissions(permissions: dict) -> dict[str, int]:
    """Role editor contract: unknown resources rejected, levels 0..3."""
    unknown = set(permissions) - set(CLIENT_RESOURCES)
    if unknown:
        raise DomainError(
            VALIDATION_ERROR, f"Unknown client resources: {sorted(unknown)}", 422
        )
    clean: dict[str, int] = {}
    for res in CLIENT_RESOURCES:
        level = int(permissions.get(res, 0))
        if not 0 <= level <= 3:
            raise DomainError(VALIDATION_ERROR, f"Invalid level for '{res}'.", 422)
        clean[res] = level
    return clean


def _oid(value: str, what: str) -> ObjectId:
    try:
        return ObjectId(value)
    except Exception as exc:
        raise DomainError(TENANT_NOT_FOUND, f"{what} not found.", 404) from exc


# --- 1.1 company profile ------------------------------------------------------

async def get_company_profile(principal: ClientPrincipal) -> dict:
    doc = await principal.tenant_db.company_profile.find_one({"_id": "company_profile"})
    return doc or {}


async def patch_company_profile(
    principal: ClientPrincipal, patch: CompanyProfilePatch
) -> dict:
    fields = {k: v for k, v in patch.model_dump().items() if v is not None}
    if fields:
        fields["updated_at"] = datetime.now(UTC)
        await principal.tenant_db.company_profile.update_one(
            {"_id": "company_profile"}, {"$set": fields}, upsert=True
        )
        await _log(principal, "settings.company_updated",
                   {"type": "company_profile", "id": "company_profile"},
                   {"fields": [k for k in fields if k != "updated_at"]})
    return await get_company_profile(principal)


# --- 1.2 employees --------------------------------------------------------------

async def list_employees(principal: ClientPrincipal) -> list[dict]:
    return await principal.tenant_db.users.find(
        {}, _EMPLOYEE_PROJECTION
    ).to_list(length=1000)


async def _load_employee(principal: ClientPrincipal, uid: str) -> dict:
    user = await principal.tenant_db.users.find_one({"_id": _oid(uid, "Employee")})
    if user is None:
        raise DomainError(TENANT_NOT_FOUND, "Employee not found.", 404)
    return user


async def _load_role(principal: ClientPrincipal, role_id: str) -> dict:
    role = await principal.tenant_db.roles.find_one({"_id": _oid(role_id, "Role")})
    if role is None:
        raise DomainError(TENANT_NOT_FOUND, "Role not found.", 404)
    return role


async def create_employee(principal: ClientPrincipal, payload: EmployeeCreate) -> dict:
    tenant_db = principal.tenant_db
    role = await _load_role(principal, payload.role_id)
    if await tenant_db.users.find_one({"email": payload.email}):
        raise DomainError(VALIDATION_ERROR, "Email already in use.", 409)

    control = get_db_manager().control
    company_id = principal.tenant.company["_id"]
    if not await companies_repo.try_claim_seat(control, company_id):
        raise DomainError(
            SEAT_LIMIT_REACHED, "Seat limit reached — contact the platform "
            "operator to increase seats.", http_status=409,
            details={"seat_limit": principal.tenant.company["seat_limit"]},
        )

    temp_password = secrets.token_urlsafe(12)
    now = datetime.now(UTC)
    try:
        result = await tenant_db.users.insert_one({
            "email": payload.email,
            "password_hash": hash_password(temp_password),
            "name": payload.name,
            "role_id": role["_id"],
            "is_blocked": False,
            "failed_attempts": 0,
            "locked_until": None,
            "must_reset_password": True,
            "last_login_at": None,
            "refresh_jtis": [],
            "created_at": now,
            "updated_at": now,
        })
    except Exception:
        await companies_repo.inc_seats_used(control, company_id, -1)
        raise
    await _log(principal, "settings.employee.created",
               {"type": "employee", "id": str(result.inserted_id),
                "label": payload.name},
               {"email": payload.email, "role": role["name"]})
    return {
        "id": str(result.inserted_id),
        "name": payload.name,
        "email": payload.email,
        "role_id": str(role["_id"]),
        "temp_password": temp_password,  # shown once, never stored
        "must_reset_password": True,
    }


async def patch_employee(
    principal: ClientPrincipal, uid: str, patch: EmployeePatch
) -> dict:
    user = await _load_employee(principal, uid)
    updates: dict = {}
    if patch.name is not None:
        updates["name"] = patch.name
    if patch.role_id is not None:
        role = await _load_role(principal, patch.role_id)
        if int(role["permissions"].get("settings", 0)) < int(Level.WRITE):
            await _guard_not_last_settings_manager(principal, user, "demote")
        updates["role_id"] = role["_id"]
    if updates:
        updates["updated_at"] = datetime.now(UTC)
        await principal.tenant_db.users.update_one(
            {"_id": user["_id"]}, {"$set": updates}
        )
        await _log(principal, "settings.employee.updated",
                   {"type": "employee", "id": uid, "label": user["name"]},
                   {"fields": [k for k in updates if k != "updated_at"]})
    updated = await principal.tenant_db.users.find_one(
        {"_id": user["_id"]}, _EMPLOYEE_PROJECTION
    )
    assert updated is not None
    return updated


async def _guard_not_last_settings_manager(
    principal: ClientPrincipal, target_user: dict, action: str
) -> None:
    """Lockout prevention: the tenant must always keep at least one active,
    unblocked user whose role has settings WRITE (an Owner-equivalent)."""
    tenant_db = principal.tenant_db
    manager_role_ids = [
        r["_id"] async for r in tenant_db.roles.find(
            {"permissions.settings": {"$gte": int(Level.WRITE)}}, {"_id": 1}
        )
    ]
    others = await tenant_db.users.count_documents({
        "_id": {"$ne": target_user["_id"]},
        "is_blocked": {"$ne": True},
        "role_id": {"$in": manager_role_ids},
    })
    if others == 0:
        raise DomainError(
            VALIDATION_ERROR,
            f"Cannot {action} the last active user able to manage settings.",
            http_status=409,
        )


async def block_employee(
    principal: ClientPrincipal, uid: str, blocked: bool
) -> None:
    """Client Owners may block their OWN employees; a platform-level company
    block is out of client reach (docs/AUTH_RBAC.md §6)."""
    user = await _load_employee(principal, uid)
    if blocked:
        await _guard_not_last_settings_manager(principal, user, "block")
    await principal.tenant_db.users.update_one(
        {"_id": user["_id"]},
        {"$set": {"is_blocked": blocked, "updated_at": datetime.now(UTC)}},
    )
    if blocked:
        await revoke_all_refresh(principal.tenant_db.users, user["_id"])
    await _log(
        principal,
        "settings.employee.blocked" if blocked else "settings.employee.unblocked",
        {"type": "employee", "id": uid, "label": user["name"]},
        {"blocked": blocked},
    )


async def unlock_employee(principal: ClientPrincipal, uid: str) -> None:
    user = await _load_employee(principal, uid)
    await principal.tenant_db.users.update_one(
        {"_id": user["_id"]},
        {"$set": {"failed_attempts": 0, "locked_until": None,
                  "updated_at": datetime.now(UTC)}},
    )
    await _log(principal, "settings.employee.unlocked",
               {"type": "employee", "id": uid, "label": user["name"]})


async def reset_employee_password(principal: ClientPrincipal, uid: str) -> str:
    user = await _load_employee(principal, uid)
    temp_password = secrets.token_urlsafe(12)
    await principal.tenant_db.users.update_one(
        {"_id": user["_id"]},
        {"$set": {
            "password_hash": hash_password(temp_password),
            "must_reset_password": True,
            "failed_attempts": 0,
            "locked_until": None,
            "updated_at": datetime.now(UTC),
        }},
    )
    await revoke_all_refresh(principal.tenant_db.users, user["_id"])
    await _log(principal, "settings.employee.password_reset",
               {"type": "employee", "id": uid, "label": user["name"]})
    return temp_password


# --- 1.3 client roles -----------------------------------------------------------

async def list_roles(principal: ClientPrincipal) -> list[dict]:
    roles = await principal.tenant_db.roles.find({}).to_list(length=500)
    # Surface *effective* CSV grants so the editor shows what a role actually
    # has — including the Owner-equivalent rollout default for roles never edited.
    for role in roles:
        role["csv_access"] = csv_access.effective(role)
    return roles


def csv_catalog() -> list[dict]:
    """Every CSV tab, for the role editor's grant multi-selects."""
    return csv_access.catalog()


async def create_role(principal: ClientPrincipal, payload: RoleCreate) -> dict:
    clean = validate_client_permissions(payload.permissions)
    tenant_db = principal.tenant_db
    if await tenant_db.roles.find_one({"name": payload.name}):
        raise DomainError(VALIDATION_ERROR, "Role name already exists.", 409)
    now = datetime.now(UTC)
    result = await tenant_db.roles.insert_one({
        "name": payload.name, "permissions": clean, "is_system": False,
        "csv_access": csv_access.validate(payload.csv_access),
        "created_at": now, "updated_at": now,
    })
    await _log(principal, "settings.role.created",
               {"type": "role", "id": str(result.inserted_id), "label": payload.name})
    role = await tenant_db.roles.find_one({"_id": result.inserted_id})
    assert role is not None
    return role


async def patch_role(
    principal: ClientPrincipal, role_id: str, patch: RolePatch
) -> dict:
    """Takes effect on holders' NEXT request — roles load per request (§1.3)."""
    tenant_db = principal.tenant_db
    role = await _load_role(principal, role_id)
    updates: dict = {}
    if patch.name is not None:
        updates["name"] = patch.name
    if patch.permissions is not None:
        clean = validate_client_permissions(patch.permissions)
        # demotion via role edit must not orphan settings management
        if (
            int(role["permissions"].get("settings", 0)) >= int(Level.WRITE)
            and clean.get("settings", 0) < int(Level.WRITE)
        ):
            holders = await tenant_db.users.count_documents(
                {"role_id": role["_id"], "is_blocked": {"$ne": True}}
            )
            if holders:
                other_manager_roles = [
                    r["_id"] async for r in tenant_db.roles.find({
                        "_id": {"$ne": role["_id"]},
                        "permissions.settings": {"$gte": int(Level.WRITE)},
                    }, {"_id": 1})
                ]
                others = await tenant_db.users.count_documents({
                    "is_blocked": {"$ne": True},
                    "role_id": {"$in": other_manager_roles},
                })
                if others == 0:
                    raise DomainError(
                        VALIDATION_ERROR,
                        "Cannot remove settings WRITE from the last "
                        "Owner-equivalent role in use.",
                        http_status=409,
                    )
        updates["permissions"] = clean
    if patch.csv_access is not None:
        updates["csv_access"] = csv_access.validate(patch.csv_access)
    if updates:
        updates["updated_at"] = datetime.now(UTC)
        await tenant_db.roles.update_one({"_id": role["_id"]}, {"$set": updates})
        await _log(principal, "settings.role.updated",
                   {"type": "role", "id": role_id, "label": role["name"]},
                   {"fields": [k for k in updates if k != "updated_at"]})
    updated = await tenant_db.roles.find_one({"_id": role["_id"]})
    assert updated is not None
    return updated


async def delete_role(principal: ClientPrincipal, role_id: str) -> None:
    tenant_db = principal.tenant_db
    role = await _load_role(principal, role_id)
    holders = await tenant_db.users.count_documents({"role_id": role["_id"]})
    if holders:
        raise DomainError(
            VALIDATION_ERROR,
            f"Role is assigned to {holders} employee(s); reassign them first.",
            http_status=409,
        )
    # cannot delete the last Owner-equivalent role (settings WRITE)
    if int(role["permissions"].get("settings", 0)) >= int(Level.WRITE):
        others = await tenant_db.roles.count_documents({
            "_id": {"$ne": role["_id"]},
            "permissions.settings": {"$gte": int(Level.WRITE)},
        })
        if others == 0:
            raise DomainError(
                VALIDATION_ERROR,
                "Cannot delete the last Owner-equivalent role.",
                http_status=409,
            )
    await tenant_db.roles.delete_one({"_id": role["_id"]})
    await _log(principal, "settings.role.deleted",
               {"type": "role", "id": role_id, "label": role["name"]})


# --- 1.4 calendar events ---------------------------------------------------------

async def list_calendar_events(principal: ClientPrincipal) -> list[dict]:
    return await principal.tenant_db.calendar_events.find(
        {"is_deleted": {"$ne": True}}
    ).sort("start", 1).to_list(length=1000)


async def create_calendar_event(
    principal: ClientPrincipal, payload: CalendarEventCreate
) -> dict:
    if payload.visibility == "role" and payload.role_id is None:
        # default the target to the creator's own role
        payload.role_id = str(principal.user["role_id"])
    now = datetime.now(UTC)
    doc = {
        "title": payload.title,
        "start": payload.start,
        "end": payload.end,
        "all_day": payload.all_day,
        "visibility": payload.visibility,
        "role_id": _oid(payload.role_id, "Role") if payload.role_id else None,
        "created_by": str(principal.user["_id"]),
        "created_at": now,
        "updated_at": now,
        "is_deleted": False,
    }
    result = await principal.tenant_db.calendar_events.insert_one(doc)
    await _log(principal, "settings.calendar_event.created",
               {"type": "calendar_event", "id": str(result.inserted_id),
                "label": payload.title})
    doc["_id"] = result.inserted_id
    return doc


async def patch_calendar_event(
    principal: ClientPrincipal, event_id: str, patch: CalendarEventPatch
) -> dict:
    tenant_db = principal.tenant_db
    event = await tenant_db.calendar_events.find_one(
        {"_id": _oid(event_id, "Event"), "is_deleted": {"$ne": True}}
    )
    if event is None:
        raise DomainError(TENANT_NOT_FOUND, "Event not found.", 404)
    updates = {k: v for k, v in patch.model_dump().items() if v is not None}
    if "role_id" in updates:
        updates["role_id"] = _oid(updates["role_id"], "Role")
    if updates:
        updates["updated_at"] = datetime.now(UTC)
        await tenant_db.calendar_events.update_one(
            {"_id": event["_id"]}, {"$set": updates}
        )
        await _log(principal, "settings.calendar_event.updated",
                   {"type": "calendar_event", "id": event_id,
                    "label": event["title"]})
    updated = await tenant_db.calendar_events.find_one({"_id": event["_id"]})
    assert updated is not None
    return updated


async def delete_calendar_event(principal: ClientPrincipal, event_id: str) -> None:
    tenant_db = principal.tenant_db
    event = await tenant_db.calendar_events.find_one({"_id": _oid(event_id, "Event")})
    if event is None:
        raise DomainError(TENANT_NOT_FOUND, "Event not found.", 404)
    await tenant_db.calendar_events.update_one(
        {"_id": event["_id"]},
        {"$set": {"is_deleted": True, "deleted_at": datetime.now(UTC)}},
    )
    await _log(principal, "settings.calendar_event.deleted",
               {"type": "calendar_event", "id": event_id, "label": event["title"]})


# --- 1.5 security (read-only client view) ---------------------------------------

def get_security_view(principal: ClientPrincipal) -> dict:
    security = principal.tenant.company.get("security", {})
    return {
        "failed_login_threshold": security.get("failed_login_threshold"),
        "lockout_minutes": security.get("lockout_minutes"),
        "editable": False,  # platform decision: read-only unless granted
        "note": "Blocked users still occupy a seat until removed by the "
                "platform operator.",
    }


# --- 1.6 module visibility -------------------------------------------------------

def get_modules_view(principal: ClientPrincipal) -> list[dict]:
    from app.control_plane.companies.models import KNOWN_MODULES

    enabled = set(principal.tenant.company["enabled_modules"])
    return [
        {"module": m, "enabled": m in enabled, "self_service": False}
        for m in KNOWN_MODULES
    ]


# --- approver map (PROJECT_MANAGEMENT.md §9, edited here in Settings) ------------

async def list_approver_map(principal: ClientPrincipal) -> list[dict]:
    return await principal.tenant_db.approver_role_map.find({}).to_list(length=100)


async def patch_approver_map(
    principal: ClientPrincipal, approver_role: str, patch: ApproverMapPatch
) -> dict:
    tenant_db = principal.tenant_db
    entry = await tenant_db.approver_role_map.find_one(
        {"approver_role": approver_role}
    )
    if entry is None:
        raise DomainError(TENANT_NOT_FOUND, "Approver role not found.", 404)
    updates: dict = {}
    if patch.client_roles is not None:
        known = {
            r["name"].lower()
            async for r in tenant_db.roles.find({}, {"name": 1})
        }
        unknown = {r for r in patch.client_roles if r.lower() not in known}
        if unknown:
            raise DomainError(
                VALIDATION_ERROR, f"Unknown client roles: {sorted(unknown)}", 422
            )
        updates["client_roles"] = patch.client_roles
    if patch.assigned_user_ids is not None:
        for uid in patch.assigned_user_ids:
            await _load_employee(principal, uid)  # 404s on unknown
        updates["assigned_user_ids"] = patch.assigned_user_ids
    if updates:
        await tenant_db.approver_role_map.update_one(
            {"_id": entry["_id"]}, {"$set": updates}
        )
        await _log(principal, "settings.approver_map.updated",
                   {"type": "approver_role", "id": approver_role,
                    "label": approver_role})
    updated = await tenant_db.approver_role_map.find_one({"_id": entry["_id"]})
    assert updated is not None
    return updated
