"""Company security/status/employee-security operations (docs/AUTH_RBAC.md §5–6).

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
from app.core.audit import write_admin_audit
from app.core.db import get_db_manager
from app.core.errors import TENANT_NOT_FOUND, DomainError
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
