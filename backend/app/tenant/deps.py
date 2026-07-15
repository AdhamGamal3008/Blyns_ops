"""Reusable FastAPI dependencies (docs/ARCHITECTURE.md §7).

Ordering matters: tenant/block checks happen BEFORE any business logic.
Company status and user blocked/locked state are re-checked on EVERY request
(not only at login), so blocking invalidates existing sessions immediately
(docs/AUTH_RBAC.md §6). A short-TTL status cache is a Phase 11 optimization.
"""

from __future__ import annotations

from dataclasses import dataclass

from bson import ObjectId
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.auth.service import check_lockout
from app.control_plane.admin_users import repository as admins_repo
from app.core.config import settings
from app.core.db import get_db_manager
from app.core.errors import PERMISSION_DENIED, USER_BLOCKED, DomainError
from app.core.security import TokenPayload, decode_token
from app.shared.enums import Level
from app.tenant.context import TenantContext, resolve_tenant

_bearer = HTTPBearer(auto_error=False)


def get_control_db() -> AsyncIOMotorDatabase:
    return get_db_manager().control


def _require_access_token(
    creds: HTTPAuthorizationCredentials | None, audience: str
) -> TokenPayload:
    if creds is None:
        raise DomainError(PERMISSION_DENIED, "Missing bearer token.", http_status=401)
    payload = decode_token(creds.credentials, audience)
    if payload.type != "access":
        raise DomainError(PERMISSION_DENIED, "Access token required.", http_status=401)
    return payload


@dataclass
class AdminPrincipal:
    user: dict
    role: dict

    def level_for(self, resource: str) -> Level:
        return Level(int(self.role.get("permissions", {}).get(resource, 0)))


@dataclass
class ClientPrincipal:
    user: dict
    role: dict
    tenant: TenantContext

    @property
    def tenant_db(self) -> AsyncIOMotorDatabase:
        return self.tenant.db

    def level_for(self, resource: str) -> Level:
        return Level(int(self.role.get("permissions", {}).get(resource, 0)))


async def current_admin(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> AdminPrincipal:
    payload = _require_access_token(creds, settings.admin_token_audience)
    control = get_control_db()
    user = await admins_repo.get_admin_by_id(control, payload.sub)
    if user is None:
        raise DomainError(PERMISSION_DENIED, "Unknown admin.", http_status=401)
    if not user.get("is_active", False):
        raise DomainError(USER_BLOCKED, "Admin account is deactivated.", http_status=403)
    check_lockout(user)
    role = await admins_repo.get_admin_role(control, user["role_id"])
    if role is None:
        raise DomainError(PERMISSION_DENIED, "Admin role not found.", http_status=403)
    return AdminPrincipal(user=user, role=role)


async def current_client_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> ClientPrincipal:
    payload = _require_access_token(creds, settings.client_token_audience)
    if not payload.tenant:
        raise DomainError(PERMISSION_DENIED, "Token has no tenant.", http_status=401)
    # Re-checks company status on every request (TENANT_BLOCKED, §6).
    ctx = await resolve_tenant(payload.tenant)
    user = await ctx.db.users.find_one({"_id": ObjectId(payload.sub)})
    if user is None:
        raise DomainError(PERMISSION_DENIED, "Unknown user.", http_status=401)
    if user.get("is_blocked", False):
        raise DomainError(USER_BLOCKED, "User is blocked.", http_status=403)
    check_lockout(user)
    role = await ctx.db.roles.find_one({"_id": user["role_id"]})
    if role is None:
        raise DomainError(PERMISSION_DENIED, "Role not found.", http_status=403)
    return ClientPrincipal(user=user, role=role, tenant=ctx)


async def get_tenant_db(
    principal: ClientPrincipal = Depends(current_client_user),
) -> AsyncIOMotorDatabase:
    return principal.tenant_db


def require(resource: str, needed: Level):
    """Client-realm RBAC guard: a simple `>=` check over the role map."""

    async def _dep(
        principal: ClientPrincipal = Depends(current_client_user),
    ) -> ClientPrincipal:
        if principal.level_for(resource) < needed:
            raise DomainError(
                PERMISSION_DENIED,
                f"Requires {needed.name} on '{resource}'.",
                http_status=403,
            )
        return principal

    return _dep


def require_admin(resource: str, needed: Level):
    """Admin-realm RBAC guard."""

    async def _dep(
        principal: AdminPrincipal = Depends(current_admin),
    ) -> AdminPrincipal:
        if principal.level_for(resource) < needed:
            raise DomainError(
                PERMISSION_DENIED,
                f"Requires {needed.name} on '{resource}'.",
                http_status=403,
            )
        return principal

    return _dep
