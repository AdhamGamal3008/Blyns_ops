"""Security primitives (docs/ARCHITECTURE.md §3).

Passwords: argon2id — never bcrypt-only, never plaintext.
JWT: both realms share the payload shape; `aud` separates them
(erp-admin vs erp-client). Realm-specific dependencies live in app/auth/
(Phase 3); these primitives are pure and independently testable.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, Literal

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from pydantic import BaseModel

from app.core.config import settings
from app.core.errors import PERMISSION_DENIED, DomainError

_hasher = PasswordHasher()  # argon2id by default


def hash_password(raw: str) -> str:
    return _hasher.hash(raw)


def verify_password(raw: str, stored_hash: str) -> bool:
    try:
        return _hasher.verify(stored_hash, raw)
    except (VerifyMismatchError, InvalidHashError):
        return False


class TokenPayload(BaseModel):
    sub: str
    aud: str
    tenant: str | None = None  # client only; null for admin
    role_id: str | None = None
    type: Literal["access", "refresh"] = "access"
    jti: str | None = None  # refresh tokens only — rotation allowlist key
    iat: int
    exp: int


def create_access_token(
    sub: str,
    audience: str,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    return _create_token(
        sub, audience, "access",
        timedelta(minutes=settings.access_token_ttl_min),
        extra_claims,
    )


def create_refresh_token(
    sub: str,
    audience: str,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    return _create_token(
        sub, audience, "refresh",
        timedelta(days=settings.refresh_token_ttl_days),
        extra_claims,
    )


def _create_token(
    sub: str,
    audience: str,
    token_type: Literal["access", "refresh"],
    ttl: timedelta,
    extra_claims: dict[str, Any] | None,
) -> str:
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": sub,
        "aud": audience,
        "tenant": None,
        "role_id": None,
        "type": token_type,
        "iat": int(now.timestamp()),
        "exp": int((now + ttl).timestamp()),
    }
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str, expected_audience: str) -> TokenPayload:
    """Decode + verify. A wrong/missing audience → PERMISSION_DENIED (401):
    one realm's token must never reach the other's API."""
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            audience=expected_audience,
        )
    except jwt.ExpiredSignatureError as exc:
        raise DomainError(
            PERMISSION_DENIED, "Token has expired.", http_status=401
        ) from exc
    except jwt.InvalidTokenError as exc:  # bad signature, wrong aud, malformed…
        raise DomainError(
            PERMISSION_DENIED, "Invalid token.", http_status=401
        ) from exc
    return TokenPayload(**payload)
