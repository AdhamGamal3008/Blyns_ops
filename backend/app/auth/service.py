"""Shared auth logic for both realms (docs/AUTH_RBAC.md §4, §5, §7).

The two realms differ only in user pool, audience, and where the lockout
policy comes from (company override vs global default) — the mechanics here
are identical, so both routers reuse these functions.

Refresh rotation (§7): each user doc keeps a `refresh_jtis` allowlist. Every
refresh issues a new refresh token (new jti), pulls the old jti, pushes the
new one. Logout / block / password reset clear the list — revoking every
outstanding refresh token at once.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from motor.motor_asyncio import AsyncIOMotorCollection

from app.core.errors import (
    ACCOUNT_LOCKED,
    INVALID_CREDENTIALS,
    PERMISSION_DENIED,
    DomainError,
)
from app.core.security import (
    TokenPayload,
    create_access_token,
    create_refresh_token,
    decode_token,
    verify_password,
)

MAX_ACTIVE_REFRESH_JTIS = 10  # cap concurrent sessions per user


def raise_invalid_credentials() -> None:
    """Generic failure — never reveals whether email/password/lock was wrong."""
    raise DomainError(INVALID_CREDENTIALS, "Invalid credentials.", http_status=401)


def check_lockout(user: dict) -> None:
    locked_until = user.get("locked_until")
    if locked_until is not None and locked_until > datetime.now(UTC):
        retry_after = int((locked_until - datetime.now(UTC)).total_seconds()) + 1
        raise DomainError(
            ACCOUNT_LOCKED,
            "Account is locked due to failed login attempts.",
            http_status=423,
            details={"locked_until": locked_until.isoformat()},
            headers={"Retry-After": str(retry_after)},
        )


async def handle_password_check(
    users: AsyncIOMotorCollection,
    user: dict,
    password: str,
    threshold: int,
    lockout_minutes: int,
) -> None:
    """§4 step 6. Failure increments the counter; hitting the threshold sets
    locked_until and resets the counter to 0. Always fails generically."""
    if verify_password(password, user["password_hash"]):
        await users.update_one(
            {"_id": user["_id"]},
            {"$set": {
                "failed_attempts": 0,
                "locked_until": None,
                "last_login_at": datetime.now(UTC),
                "updated_at": datetime.now(UTC),
            }},
        )
        return

    failed = user.get("failed_attempts", 0) + 1
    if failed >= threshold:
        update: dict[str, Any] = {
            "$set": {
                "failed_attempts": 0,
                "locked_until": datetime.now(UTC) + timedelta(minutes=lockout_minutes),
                "updated_at": datetime.now(UTC),
            }
        }
    else:
        update = {
            "$set": {"failed_attempts": failed, "updated_at": datetime.now(UTC)},
        }
    await users.update_one({"_id": user["_id"]}, update)
    raise_invalid_credentials()


async def issue_token_pair(
    users: AsyncIOMotorCollection,
    user: dict,
    audience: str,
    extra_claims: dict[str, Any] | None = None,
) -> dict[str, str]:
    """Access + rotating refresh; the refresh jti joins the user's allowlist."""
    claims = dict(extra_claims or {})
    claims["role_id"] = str(user["role_id"])
    access = create_access_token(str(user["_id"]), audience, claims)
    jti = uuid.uuid4().hex
    refresh = create_refresh_token(str(user["_id"]), audience, {**claims, "jti": jti})
    await users.update_one(
        {"_id": user["_id"]},
        {"$push": {"refresh_jtis": {"$each": [jti], "$slice": -MAX_ACTIVE_REFRESH_JTIS}}},
    )
    return {"access_token": access, "refresh_token": refresh, "token_type": "bearer"}


def decode_refresh(token: str, audience: str) -> TokenPayload:
    payload = decode_token(token, audience)
    if payload.type != "refresh" or payload.jti is None:
        raise DomainError(PERMISSION_DENIED, "Not a refresh token.", http_status=401)
    return payload


async def rotate_refresh(
    users: AsyncIOMotorCollection,
    user: dict,
    payload: TokenPayload,
    audience: str,
    extra_claims: dict[str, Any] | None = None,
) -> dict[str, str]:
    """One-shot rotation: the presented jti must be on the allowlist; it is
    consumed atomically so a replayed refresh token is rejected."""
    result = await users.update_one(
        {"_id": user["_id"], "refresh_jtis": payload.jti},
        {"$pull": {"refresh_jtis": payload.jti}},
    )
    if result.modified_count != 1:  # revoked or already used
        raise DomainError(PERMISSION_DENIED, "Refresh token revoked.", http_status=401)
    return await issue_token_pair(users, user, audience, extra_claims)


async def revoke_all_refresh(users: AsyncIOMotorCollection, user_id: Any) -> None:
    await users.update_one({"_id": user_id}, {"$set": {"refresh_jtis": []}})
