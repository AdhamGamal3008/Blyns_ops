"""Company operations: onboarding, CRUD, seats, employees, and the security/
status actions from AUTH_RBAC §5–6 (docs/ADMIN_PORTAL.md §1–2).

Every function here is a state change → writes an admin audit entry
(CLAUDE.md rule 4). Blocking also revokes refresh tokens; access tokens die
via the per-request status re-checks in tenant/deps.py.
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.auth.service import revoke_all_refresh
from app.control_plane.companies import repository as companies_repo
from app.control_plane.companies.models import (
    AdminEmployeeCreate,
    UpdateCompanyPayload,
)
from app.control_plane.provisioning.registry import MODULE_SEEDS, SEED_ORDER
from app.core.audit import write_admin_audit
from app.core.db import get_db_manager
from app.core.errors import (
    SEAT_LIMIT_REACHED,
    TENANT_NOT_FOUND,
    VALIDATION_ERROR,
    DomainError,
)
from app.core.security import hash_password


async def _load_company(control: AsyncIOMotorDatabase, company_id: str) -> dict:
    try:
        company = await companies_repo.get_by_id(control, company_id)
    except Exception as exc:  # malformed ObjectId
        raise DomainError(TENANT_NOT_FOUND, "Company not found.", 404) from exc
    if company is None:
        raise DomainError(TENANT_NOT_FOUND, "Company not found.", 404)
    return company


async def _load_employee(tenant_db: AsyncIOMotorDatabase, uid: str) -> dict:
    try:
        user = await tenant_db.users.find_one({"_id": ObjectId(uid)})
    except Exception as exc:
        raise DomainError(TENANT_NOT_FOUND, "Employee not found.", 404) from exc
    if user is None:
        raise DomainError(TENANT_NOT_FOUND, "Employee not found.", 404)
    return user


async def get_company_detail(company_id: str) -> dict:
    """Detail incl. seats, status, and the latest storage snapshot
    (docs/ADMIN_PORTAL.md §1)."""
    control = get_db_manager().control
    company = await _load_company(control, company_id)
    snapshot = await control.platform_metrics.find_one(
        {"scope": "tenant", "tenant_id": str(company["_id"])},
        sort=[("captured_at", -1)],
    )
    company["storage_snapshot"] = (
        {"captured_at": snapshot["captured_at"], **snapshot["metrics"]}
        if snapshot else None
    )
    return company


async def update_company(
    company_id: str, payload: UpdateCompanyPayload, actor_id: str
) -> dict:
    """Edit name / enabled_modules; enabling a module runs its seed()
    (docs/ADMIN_PORTAL.md §1, MULTITENANCY.md §5)."""
    dbm = get_db_manager()
    company = await _load_company(dbm.control, company_id)

    fields: dict = {}
    newly_enabled: list[str] = []
    if payload.name is not None:
        fields["name"] = payload.name
    if payload.enabled_modules is not None:
        newly_enabled = [
            m for m in payload.enabled_modules
            if m not in company["enabled_modules"]
        ]
        fields["enabled_modules"] = payload.enabled_modules
    if not fields:
        return company

    tenant_db = dbm.tenant(company["db_name"])
    for name in SEED_ORDER:  # canonical order for newly enabled seeds
        if name in newly_enabled:
            await MODULE_SEEDS[name](tenant_db)

    await companies_repo.update_fields(dbm.control, company["_id"], fields)
    await write_admin_audit(
        actor_id, "company.updated",
        target={"type": "company", "id": str(company["_id"]), "slug": company["slug"]},
        details={"fields": list(fields), "modules_enabled": newly_enabled},
    )
    updated = await companies_repo.get_by_id(dbm.control, company["_id"])
    assert updated is not None
    return updated


async def set_seat_limit(
    company_id: str, seat_limit: int, force: bool, actor_id: str
) -> dict:
    """Increase: always allowed. Decrease below seats_used: SEAT_LIMIT_REACHED
    unless force — never silently orphan users (docs/ADMIN_PORTAL.md §2)."""
    control = get_db_manager().control
    company = await _load_company(control, company_id)
    if seat_limit < company["seats_used"] and not force:
        raise DomainError(
            SEAT_LIMIT_REACHED,
            "New seat limit is below seats in use; block/remove excess users "
            "first or pass force=true.",
            http_status=409,
            details={"seats_used": company["seats_used"], "seat_limit": seat_limit},
        )
    await companies_repo.update_fields(control, company["_id"], {"seat_limit": seat_limit})
    await write_admin_audit(
        actor_id, "company.seats_updated",
        target={"type": "company", "id": str(company["_id"]), "slug": company["slug"]},
        details={"from": company["seat_limit"], "to": seat_limit, "force": force},
    )
    return {"seat_limit": seat_limit, "seats_used": company["seats_used"]}


async def list_employees(company_id: str) -> list[dict]:
    dbm = get_db_manager()
    company = await _load_company(dbm.control, company_id)
    tenant_db = dbm.tenant(company["db_name"])
    users = await tenant_db.users.find(
        {}, {"password_hash": 0, "refresh_jtis": 0}
    ).to_list(length=1000)
    return users


async def create_employee(
    company_id: str, payload: AdminEmployeeCreate, actor_id: str
) -> dict:
    """Admin-side employee creation: atomic seat claim, temp password,
    must_reset_password (docs/ADMIN_PORTAL.md §2)."""
    dbm = get_db_manager()
    company = await _load_company(dbm.control, company_id)
    tenant_db = dbm.tenant(company["db_name"])

    role = await tenant_db.roles.find_one({"name": payload.role_name})
    if role is None:
        raise DomainError(
            VALIDATION_ERROR, f"Role '{payload.role_name}' not found.", 422
        )
    if await tenant_db.users.find_one({"email": payload.email}):
        raise DomainError(VALIDATION_ERROR, "Email already in use.", 409)

    if not await companies_repo.try_claim_seat(dbm.control, company["_id"]):
        raise DomainError(
            SEAT_LIMIT_REACHED, "Seat limit reached.", http_status=409,
            details={"seat_limit": company["seat_limit"]},
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
        await companies_repo.inc_seats_used(dbm.control, company["_id"], -1)
        raise
    await write_admin_audit(
        actor_id, "employee.created",
        target={"type": "employee", "id": str(result.inserted_id),
                "company": company["slug"]},
        details={"email": payload.email, "role": payload.role_name},
    )
    return {
        "id": str(result.inserted_id),
        "email": payload.email,
        "name": payload.name,
        "role_name": payload.role_name,
        "temp_password": temp_password,
        "must_reset_password": True,
    }


async def get_latest_provisioning_job(company_id: str) -> dict:
    control = get_db_manager().control
    company = await _load_company(control, company_id)
    job = await control.provisioning_jobs.find_one(
        {"company_id": company["_id"]}, sort=[("created_at", -1)]
    )
    if job is None:
        raise DomainError(TENANT_NOT_FOUND, "No provisioning job found.", 404)
    return job


async def set_company_security(
    company_id: str, threshold: int, lockout_minutes: int, actor_id: str
) -> dict:
    control = get_db_manager().control
    company = await _load_company(control, company_id)
    security = {
        "failed_login_threshold": threshold,
        "lockout_minutes": lockout_minutes,
    }
    await companies_repo.update_fields(control, company["_id"], {"security": security})
    await write_admin_audit(
        actor_id, "company.security_updated",
        target={"type": "company", "id": str(company["_id"]), "slug": company["slug"]},
        details=security,
    )
    return security


async def set_company_status(company_id: str, status: str, actor_id: str) -> dict:
    control = get_db_manager().control
    company = await _load_company(control, company_id)
    await companies_repo.update_fields(control, company["_id"], {"status": status})
    await write_admin_audit(
        actor_id, "company.status_changed",
        target={"type": "company", "id": str(company["_id"]), "slug": company["slug"]},
        details={"from": company["status"], "to": status},
    )
    return {"status": status}


async def unlock_employee(company_id: str, uid: str, actor_id: str) -> None:
    dbm = get_db_manager()
    company = await _load_company(dbm.control, company_id)
    tenant_db = dbm.tenant(company["db_name"])
    user = await _load_employee(tenant_db, uid)
    await tenant_db.users.update_one(
        {"_id": user["_id"]},
        {"$set": {
            "failed_attempts": 0,
            "locked_until": None,
            "updated_at": datetime.now(UTC),
        }},
    )
    await write_admin_audit(
        actor_id, "employee.unlocked",
        target={"type": "employee", "id": uid, "company": company["slug"]},
        details={},
    )


async def reset_employee_password(company_id: str, uid: str, actor_id: str) -> str:
    """Sets a generated temp password + must_reset_password=true; revokes all
    refresh tokens. Returns the temp password (shown once, never stored)."""
    dbm = get_db_manager()
    company = await _load_company(dbm.control, company_id)
    tenant_db = dbm.tenant(company["db_name"])
    user = await _load_employee(tenant_db, uid)
    temp_password = secrets.token_urlsafe(12)
    await tenant_db.users.update_one(
        {"_id": user["_id"]},
        {"$set": {
            "password_hash": hash_password(temp_password),
            "must_reset_password": True,
            "failed_attempts": 0,
            "locked_until": None,
            "updated_at": datetime.now(UTC),
        }},
    )
    await revoke_all_refresh(tenant_db.users, user["_id"])
    await write_admin_audit(
        actor_id, "employee.password_reset",
        target={"type": "employee", "id": uid, "company": company["slug"]},
        details={},
    )
    return temp_password


async def set_employee_blocked(
    company_id: str, uid: str, blocked: bool, actor_id: str
) -> None:
    dbm = get_db_manager()
    company = await _load_company(dbm.control, company_id)
    tenant_db = dbm.tenant(company["db_name"])
    user = await _load_employee(tenant_db, uid)
    await tenant_db.users.update_one(
        {"_id": user["_id"]},
        {"$set": {"is_blocked": blocked, "updated_at": datetime.now(UTC)}},
    )
    if blocked:
        await revoke_all_refresh(tenant_db.users, user["_id"])
    await write_admin_audit(
        actor_id, "employee.blocked" if blocked else "employee.unblocked",
        target={"type": "employee", "id": uid, "company": company["slug"]},
        details={"blocked": blocked},
    )
