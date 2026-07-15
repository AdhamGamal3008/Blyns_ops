"""Admin users & admin roles endpoints (docs/ADMIN_PORTAL.md §3, §5)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, field_validator

from app.control_plane.admin_users import service
from app.shared.enums import Level
from app.shared.schemas import envelope, to_api
from app.shared.validation import EMAIL_PATTERN
from app.tenant.deps import AdminPrincipal, get_control_db, require_admin

router = APIRouter(prefix="/api/v1/admin", tags=["admin-users"])


class AdminUserCreate(BaseModel):
    email: str
    name: str = Field(min_length=1)
    role_id: str
    password: str | None = Field(default=None, min_length=8)

    @field_validator("email")
    @classmethod
    def _valid_email(cls, v: str) -> str:
        if not EMAIL_PATTERN.match(v):
            raise ValueError("invalid email address")
        return v.lower()


class AdminUserUpdate(BaseModel):
    name: str | None = None
    role_id: str | None = None
    is_active: bool | None = None


class AdminRoleCreate(BaseModel):
    name: str = Field(min_length=1)
    permissions: dict[str, int]


class AdminRoleUpdate(BaseModel):
    name: str | None = None
    permissions: dict[str, int] | None = None


# --- admin users ------------------------------------------------------------

@router.get("/admin-users")
async def list_admin_users(
    admin: AdminPrincipal = Depends(require_admin("admin_users", Level.READ)),
):
    return envelope(to_api(await service.list_admin_users(get_control_db())))


@router.post("/admin-users", status_code=201)
async def create_admin_user(
    body: AdminUserCreate,
    admin: AdminPrincipal = Depends(require_admin("admin_users", Level.WRITE)),
):
    return envelope(await service.create_admin_user(
        get_control_db(), body.email, body.name, body.role_id, body.password,
        actor_id=str(admin.user["_id"]),
    ))


@router.patch("/admin-users/{admin_id}")
async def update_admin_user(
    admin_id: str,
    body: AdminUserUpdate,
    admin: AdminPrincipal = Depends(require_admin("admin_users", Level.WRITE)),
):
    updated = await service.update_admin_user(
        get_control_db(), admin_id, body.model_dump(), actor_id=str(admin.user["_id"])
    )
    return envelope(to_api(updated))


@router.delete("/admin-users/{admin_id}")
async def delete_admin_user(
    admin_id: str,
    admin: AdminPrincipal = Depends(require_admin("admin_users", Level.WRITE)),
):
    await service.delete_admin_user(
        get_control_db(), admin_id, actor_id=str(admin.user["_id"])
    )
    return envelope({"deleted": True})


# --- admin roles ------------------------------------------------------------

@router.get("/admin-roles")
async def list_admin_roles(
    admin: AdminPrincipal = Depends(require_admin("admin_roles", Level.READ)),
):
    return envelope(to_api(await service.list_admin_roles(get_control_db())))


@router.post("/admin-roles", status_code=201)
async def create_admin_role(
    body: AdminRoleCreate,
    admin: AdminPrincipal = Depends(require_admin("admin_roles", Level.WRITE)),
):
    role = await service.create_admin_role(
        get_control_db(), body.name, body.permissions, actor_id=str(admin.user["_id"])
    )
    return envelope(to_api(role))


@router.patch("/admin-roles/{role_id}")
async def update_admin_role(
    role_id: str,
    body: AdminRoleUpdate,
    admin: AdminPrincipal = Depends(require_admin("admin_roles", Level.WRITE)),
):
    role = await service.update_admin_role(
        get_control_db(), role_id, body.name, body.permissions,
        actor_id=str(admin.user["_id"]),
    )
    return envelope(to_api(role))


@router.delete("/admin-roles/{role_id}")
async def delete_admin_role(
    role_id: str,
    admin: AdminPrincipal = Depends(require_admin("admin_roles", Level.WRITE)),
):
    await service.delete_admin_role(
        get_control_db(), role_id, actor_id=str(admin.user["_id"])
    )
    return envelope({"deleted": True})
