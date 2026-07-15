"""Admin realm auth (docs/AUTH_RBAC.md §1, §4).

Identical to client login minus tenant resolution and the company-block step;
lockout uses the global default threshold.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.auth import service as auth
from app.control_plane.admin_users import repository as admins_repo
from app.core.audit import write_admin_audit
from app.core.config import settings
from app.core.errors import USER_BLOCKED, DomainError
from app.shared.schemas import envelope
from app.tenant.deps import AdminPrincipal, current_admin, get_control_db

router = APIRouter(prefix="/api/v1/admin/auth", tags=["admin-auth"])


class AdminLoginRequest(BaseModel):
    email: str
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


@router.post("/login")
async def admin_login(body: AdminLoginRequest):
    control = get_control_db()
    user = await admins_repo.get_admin_by_email(control, body.email)
    if user is None:
        auth.raise_invalid_credentials()
    assert user is not None
    if not user.get("is_active", False):
        raise DomainError(USER_BLOCKED, "Admin account is deactivated.", http_status=403)
    auth.check_lockout(user)
    await auth.handle_password_check(
        control.admin_users, user, body.password,
        threshold=settings.default_failed_login_threshold,
        lockout_minutes=settings.default_lockout_minutes,
    )
    tokens = await auth.issue_token_pair(
        control.admin_users, user, settings.admin_token_audience
    )
    await write_admin_audit(
        actor_id=str(user["_id"]),
        action="admin.auth.login",
        target={"type": "admin_user", "id": str(user["_id"])},
        details={},
    )
    return envelope({
        **tokens,
        "expires_in": settings.access_token_ttl_min * 60,
        "user": {"id": str(user["_id"]), "name": user["name"], "email": user["email"]},
    })


@router.post("/refresh")
async def admin_refresh(body: RefreshRequest):
    control = get_control_db()
    payload = auth.decode_refresh(body.refresh_token, settings.admin_token_audience)
    user = await admins_repo.get_admin_by_id(control, payload.sub)
    if user is None or not user.get("is_active", False):
        raise DomainError("PERMISSION_DENIED", "Admin unavailable.", http_status=401)
    auth.check_lockout(user)
    tokens = await auth.rotate_refresh(
        control.admin_users, user, payload, settings.admin_token_audience
    )
    return envelope({**tokens, "expires_in": settings.access_token_ttl_min * 60})


@router.post("/logout")
async def admin_logout(principal: AdminPrincipal = Depends(current_admin)):
    control = get_control_db()
    await auth.revoke_all_refresh(control.admin_users, principal.user["_id"])
    await write_admin_audit(
        actor_id=str(principal.user["_id"]),
        action="admin.auth.logout",
        target={"type": "admin_user", "id": str(principal.user["_id"])},
        details={},
    )
    return envelope({"logged_out": True})


@router.get("/me")
async def admin_me(principal: AdminPrincipal = Depends(current_admin)):
    return envelope({
        "id": str(principal.user["_id"]),
        "email": principal.user["email"],
        "name": principal.user["name"],
        "role": {
            "id": str(principal.role["_id"]),
            "name": principal.role["name"],
            "permissions": principal.role["permissions"],
        },
    })
