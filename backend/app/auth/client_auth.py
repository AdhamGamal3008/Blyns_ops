"""Client realm auth (docs/AUTH_RBAC.md §1, §4, §7).

Login accepts a company slug to FIND the tenant before a token exists — the
one place that happens (docs/MULTITENANCY.md §4). After login the tenant is
bound into the signed token and never taken from client input again.
"""

from __future__ import annotations

from datetime import UTC, datetime

from bson import ObjectId
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.auth import service as auth
from app.control_plane.companies import repository as companies_repo
from app.core.audit import write_activity
from app.core.config import settings
from app.core.db import get_db_manager
from app.core.errors import (
    TENANT_BLOCKED,
    TENANT_NOT_FOUND,
    USER_BLOCKED,
    DomainError,
)
from app.core.security import hash_password, verify_password
from app.shared import csv_access
from app.shared.schemas import envelope
from app.tenant.context import resolve_tenant
from app.tenant.deps import ClientPrincipal, current_client_user

router = APIRouter(prefix="/api/v1/auth", tags=["client-auth"])


class ClientLoginRequest(BaseModel):
    company: str  # slug (email-domain mapping may come later)
    email: str
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8)


@router.post("/login")
async def client_login(body: ClientLoginRequest):
    dbm = get_db_manager()
    # 1. Resolve company by slug → db_name, status, security policy.
    company = await companies_repo.get_by_slug(dbm.control, body.company)
    if company is None:
        raise DomainError(TENANT_NOT_FOUND, "Company not found.", http_status=404)
    # 2. Blocked/non-active company → TENANT_BLOCKED (never reveal user existence).
    if company["status"] != "active":
        raise DomainError(TENANT_BLOCKED, "This company is not active.", http_status=403)

    tenant_db = dbm.tenant(company["db_name"])
    # 3. Load user by email.
    user = await tenant_db.users.find_one({"email": body.email.lower()})
    if user is None:
        auth.raise_invalid_credentials()
    assert user is not None
    # 4. Block check.
    if user.get("is_blocked", False):
        raise DomainError(USER_BLOCKED, "User is blocked.", http_status=403)
    # 5. Lockout check (423 + Retry-After).
    auth.check_lockout(user)
    # 6. Verify password — company security policy drives the lockout math.
    security = company.get("security", {})
    await auth.handle_password_check(
        tenant_db.users, user, body.password,
        threshold=security.get(
            "failed_login_threshold", settings.default_failed_login_threshold
        ),
        lockout_minutes=security.get(
            "lockout_minutes", settings.default_lockout_minutes
        ),
    )
    # Success → tenant-bound token pair.
    tokens = await auth.issue_token_pair(
        tenant_db.users, user, settings.client_token_audience,
        extra_claims={"tenant": company["db_name"]},
    )
    # 7. Activity entry.
    await write_activity(
        tenant_db,
        actor_id=str(user["_id"]),
        action="auth.login",
        entity={"type": "user", "id": str(user["_id"]), "label": user["name"]},
        details={},
        actor_name=user["name"],
        module="auth",
    )
    return envelope({
        **tokens,
        "expires_in": settings.access_token_ttl_min * 60,
        "password_reset_required": bool(user.get("must_reset_password", False)),
        "user": {"id": str(user["_id"]), "name": user["name"], "email": user["email"]},
    })


@router.post("/refresh")
async def client_refresh(body: RefreshRequest):
    payload = auth.decode_refresh(body.refresh_token, settings.client_token_audience)
    if not payload.tenant:
        raise DomainError("PERMISSION_DENIED", "Token has no tenant.", http_status=401)
    ctx = await resolve_tenant(payload.tenant)  # company re-checked here
    user = await ctx.db.users.find_one({"_id": ObjectId(payload.sub)})
    if user is None or user.get("is_blocked", False):
        raise DomainError("PERMISSION_DENIED", "User unavailable.", http_status=401)
    auth.check_lockout(user)
    tokens = await auth.rotate_refresh(
        ctx.db.users, user, payload, settings.client_token_audience,
        extra_claims={"tenant": payload.tenant},
    )
    return envelope({**tokens, "expires_in": settings.access_token_ttl_min * 60})


@router.post("/logout")
async def client_logout(principal: ClientPrincipal = Depends(current_client_user)):
    await auth.revoke_all_refresh(principal.tenant_db.users, principal.user["_id"])
    await write_activity(
        principal.tenant_db,
        actor_id=str(principal.user["_id"]),
        action="auth.logout",
        entity={"type": "user", "id": str(principal.user["_id"]),
                "label": principal.user["name"]},
        details={},
        actor_name=principal.user["name"],
        module="auth",
    )
    return envelope({"logged_out": True})


@router.post("/change-password")
async def change_password(
    body: ChangePasswordRequest,
    principal: ClientPrincipal = Depends(current_client_user),
):
    """Completes the forced-reset flow (§4: `password_reset_required`)."""
    user = principal.user
    if not verify_password(body.current_password, user["password_hash"]):
        auth.raise_invalid_credentials()
    await principal.tenant_db.users.update_one(
        {"_id": user["_id"]},
        {"$set": {
            "password_hash": hash_password(body.new_password),
            "must_reset_password": False,
            "updated_at": datetime.now(UTC),
        }},
    )
    # Password reset revokes every outstanding refresh token (§7).
    await auth.revoke_all_refresh(principal.tenant_db.users, user["_id"])
    await write_activity(
        principal.tenant_db,
        actor_id=str(user["_id"]),
        action="auth.password_changed",
        entity={"type": "user", "id": str(user["_id"]), "label": user["name"]},
        details={},
        actor_name=user["name"],
        module="auth",
    )
    return envelope({"password_changed": True})


@router.get("/me")
async def client_me(principal: ClientPrincipal = Depends(current_client_user)):
    # The company logo lives on the tenant's company_profile; surface it here so
    # every authenticated user (not just those with Settings access) can render
    # it in the shell.
    profile = await principal.tenant_db.company_profile.find_one(
        {"_id": "company_profile"}, {"logo_ref": 1}
    )
    return envelope({
        "id": str(principal.user["_id"]),
        "email": principal.user["email"],
        "name": principal.user["name"],
        "must_reset_password": bool(principal.user.get("must_reset_password", False)),
        "company": {
            "slug": principal.tenant.company["slug"],
            "name": principal.tenant.company["name"],
            "enabled_modules": principal.tenant.company["enabled_modules"],
            "logo_ref": (profile or {}).get("logo_ref"),
        },
        "role": {
            "id": str(principal.role["_id"]),
            "name": principal.role["name"],
            "permissions": principal.role["permissions"],
            # effective per-tab CSV grants (SETTINGS.md §1.3) so the SPA can show
            # the right import/export controls and the approval state per tab
            "csv_access": csv_access.effective(principal.role),
        },
    })
