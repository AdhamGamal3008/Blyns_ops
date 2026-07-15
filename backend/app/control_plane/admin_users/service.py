"""Admin users & admin roles management (docs/ADMIN_PORTAL.md §3).

Lockout-prevention guard: you can never delete, deactivate, or demote the
LAST active admin holding admin_users WRITE — that is the generalized form of
"cannot delete the last Super Admin" (role names are editable data, so the
guard checks capability, not the name).
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime

from bson import ObjectId

from app.control_plane.admin_users import repository as repo
from app.control_plane.admin_users.models import ADMIN_RESOURCES
from app.core.audit import write_admin_audit
from app.core.errors import TENANT_NOT_FOUND, VALIDATION_ERROR, DomainError
from app.core.security import hash_password
from app.shared.enums import Level


def validate_permissions(permissions: dict) -> dict[str, int]:
    """Role editor contract: unknown resources rejected, levels 0..3."""
    unknown = set(permissions) - set(ADMIN_RESOURCES)
    if unknown:
        raise DomainError(
            VALIDATION_ERROR, f"Unknown admin resources: {sorted(unknown)}", 422
        )
    clean: dict[str, int] = {}
    for res in ADMIN_RESOURCES:
        level = int(permissions.get(res, 0))
        if not 0 <= level <= 3:
            raise DomainError(VALIDATION_ERROR, f"Invalid level for '{res}'.", 422)
        clean[res] = level
    return clean


async def _load_admin(control, admin_id: str) -> dict:
    try:
        user = await control.admin_users.find_one({"_id": ObjectId(admin_id)})
    except Exception as exc:
        raise DomainError(TENANT_NOT_FOUND, "Admin user not found.", 404) from exc
    if user is None:
        raise DomainError(TENANT_NOT_FOUND, "Admin user not found.", 404)
    return user


async def _load_role(control, role_id: str) -> dict:
    try:
        role = await control.admin_roles.find_one({"_id": ObjectId(role_id)})
    except Exception as exc:
        raise DomainError(TENANT_NOT_FOUND, "Admin role not found.", 404) from exc
    if role is None:
        raise DomainError(TENANT_NOT_FOUND, "Admin role not found.", 404)
    return role


async def _count_other_admin_managers(control, exclude_id: ObjectId) -> int:
    """Active admins (excluding one) whose role has admin_users WRITE."""
    role_ids = [
        r["_id"] async for r in control.admin_roles.find(
            {"permissions.admin_users": {"$gte": int(Level.WRITE)}}, {"_id": 1}
        )
    ]
    return await control.admin_users.count_documents({
        "_id": {"$ne": exclude_id},
        "is_active": True,
        "role_id": {"$in": role_ids},
    })


def _guard_not_last_manager(others: int, action: str) -> None:
    if others == 0:
        raise DomainError(
            VALIDATION_ERROR,
            f"Cannot {action} the last active admin able to manage admin users.",
            http_status=409,
        )


# --- admin users ------------------------------------------------------------

async def list_admin_users(control) -> list[dict]:
    return await control.admin_users.find(
        {}, {"password_hash": 0, "refresh_jtis": 0}
    ).to_list(length=1000)


async def create_admin_user(
    control, email: str, name: str, role_id: str, password: str | None, actor_id: str
) -> dict:
    role = await _load_role(control, role_id)
    generated = password is None
    password = password or secrets.token_urlsafe(12)
    created = await repo.create_admin_user(
        control, email, name, hash_password(password), role["_id"]
    )
    if created is None:
        raise DomainError(VALIDATION_ERROR, "Email already in use.", 409)
    await write_admin_audit(
        actor_id, "admin_user.created",
        target={"type": "admin_user", "id": str(created["_id"])},
        details={"email": email, "role": role["name"]},
    )
    out = {"id": str(created["_id"]), "email": email, "name": name,
           "role_id": str(role["_id"])}
    if generated:
        out["temp_password"] = password  # shown once, never stored
    return out


async def update_admin_user(
    control, admin_id: str, fields: dict, actor_id: str
) -> dict:
    user = await _load_admin(control, admin_id)
    updates: dict = {}
    if "name" in fields and fields["name"] is not None:
        updates["name"] = fields["name"]
    if "role_id" in fields and fields["role_id"] is not None:
        new_role = await _load_role(control, fields["role_id"])
        # demotion guard: would this drop the last admin-manager?
        if int(new_role["permissions"].get("admin_users", 0)) < int(Level.WRITE):
            _guard_not_last_manager(
                await _count_other_admin_managers(control, user["_id"]), "demote"
            )
        updates["role_id"] = new_role["_id"]
    if "is_active" in fields and fields["is_active"] is not None:
        if fields["is_active"] is False:
            _guard_not_last_manager(
                await _count_other_admin_managers(control, user["_id"]), "deactivate"
            )
        updates["is_active"] = fields["is_active"]
    if not updates:
        return user
    updates["updated_at"] = datetime.now(UTC)
    await control.admin_users.update_one({"_id": user["_id"]}, {"$set": updates})
    await write_admin_audit(
        actor_id, "admin_user.updated",
        target={"type": "admin_user", "id": admin_id},
        details={"fields": [k for k in updates if k != "updated_at"]},
    )
    updated = await control.admin_users.find_one(
        {"_id": user["_id"]}, {"password_hash": 0, "refresh_jtis": 0}
    )
    assert updated is not None
    return updated


async def delete_admin_user(control, admin_id: str, actor_id: str) -> None:
    user = await _load_admin(control, admin_id)
    _guard_not_last_manager(
        await _count_other_admin_managers(control, user["_id"]), "delete"
    )
    await control.admin_users.delete_one({"_id": user["_id"]})
    await write_admin_audit(
        actor_id, "admin_user.deleted",
        target={"type": "admin_user", "id": admin_id},
        details={"email": user["email"]},
    )


# --- admin roles ------------------------------------------------------------

async def list_admin_roles(control) -> list[dict]:
    return await control.admin_roles.find({}).to_list(length=1000)


async def create_admin_role(
    control, name: str, permissions: dict, actor_id: str
) -> dict:
    clean = validate_permissions(permissions)
    if await control.admin_roles.find_one({"name": name}):
        raise DomainError(VALIDATION_ERROR, "Role name already exists.", 409)
    now = datetime.now(UTC)
    result = await control.admin_roles.insert_one({
        "name": name, "permissions": clean, "is_system": False,
        "created_at": now, "updated_at": now,
    })
    await write_admin_audit(
        actor_id, "admin_role.created",
        target={"type": "admin_role", "id": str(result.inserted_id)},
        details={"name": name},
    )
    role = await control.admin_roles.find_one({"_id": result.inserted_id})
    assert role is not None
    return role


async def update_admin_role(
    control, role_id: str, name: str | None, permissions: dict | None, actor_id: str
) -> dict:
    """Editing a role re-evaluates access for all holders on their next
    request — roles are loaded per request, never cached (§3)."""
    role = await _load_role(control, role_id)
    updates: dict = {}
    if name is not None:
        updates["name"] = name
    if permissions is not None:
        clean = validate_permissions(permissions)
        # demotion guard: dropping admin_users WRITE from a role must not
        # orphan admin management
        if (
            int(role["permissions"].get("admin_users", 0)) >= int(Level.WRITE)
            and clean.get("admin_users", 0) < int(Level.WRITE)
        ):
            holders = await control.admin_users.count_documents(
                {"role_id": role["_id"], "is_active": True}
            )
            if holders:
                other_roles = [
                    r["_id"] async for r in control.admin_roles.find({
                        "_id": {"$ne": role["_id"]},
                        "permissions.admin_users": {"$gte": int(Level.WRITE)},
                    }, {"_id": 1})
                ]
                others = await control.admin_users.count_documents({
                    "is_active": True, "role_id": {"$in": other_roles},
                })
                _guard_not_last_manager(others, "demote (via role edit)")
        updates["permissions"] = clean
    if not updates:
        return role
    updates["updated_at"] = datetime.now(UTC)
    await control.admin_roles.update_one({"_id": role["_id"]}, {"$set": updates})
    await write_admin_audit(
        actor_id, "admin_role.updated",
        target={"type": "admin_role", "id": role_id},
        details={"fields": [k for k in updates if k != "updated_at"]},
    )
    updated = await control.admin_roles.find_one({"_id": role["_id"]})
    assert updated is not None
    return updated


async def delete_admin_role(control, role_id: str, actor_id: str) -> None:
    role = await _load_role(control, role_id)
    holders = await control.admin_users.count_documents({"role_id": role["_id"]})
    if holders:
        raise DomainError(
            VALIDATION_ERROR,
            f"Role is assigned to {holders} admin user(s); reassign them first.",
            http_status=409,
        )
    await control.admin_roles.delete_one({"_id": role["_id"]})
    await write_admin_audit(
        actor_id, "admin_role.deleted",
        target={"type": "admin_role", "id": role_id},
        details={"name": role["name"]},
    )
