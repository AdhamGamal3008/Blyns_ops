"""Password hashing + JWT primitives (docs/ARCHITECTURE.md §3).

Audience separation is the critical property: one realm's token must never
decode under the other realm's expected audience.
"""

from __future__ import annotations

import datetime

import pytest
from freezegun import freeze_time

from app.core.config import settings
from app.core.errors import DomainError
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)


def test_password_hash_roundtrip():
    stored = hash_password("s3cret!")
    assert stored != "s3cret!"
    assert stored.startswith("$argon2id$")
    assert verify_password("s3cret!", stored) is True
    assert verify_password("wrong", stored) is False


def test_verify_password_handles_garbage_hash():
    assert verify_password("anything", "not-a-hash") is False


def test_access_token_roundtrip_with_claims():
    token = create_access_token(
        "user123",
        settings.client_token_audience,
        extra_claims={"tenant": "erp_tenant_acme", "role_id": "role9"},
    )
    payload = decode_token(token, settings.client_token_audience)
    assert payload.sub == "user123"
    assert payload.aud == settings.client_token_audience
    assert payload.tenant == "erp_tenant_acme"
    assert payload.role_id == "role9"
    assert payload.type == "access"
    assert payload.exp > payload.iat


def test_admin_token_has_no_tenant():
    token = create_access_token("admin1", settings.admin_token_audience)
    payload = decode_token(token, settings.admin_token_audience)
    assert payload.tenant is None


def test_wrong_audience_rejected():
    """A client token can never reach the admin API and vice-versa."""
    client_token = create_access_token("user123", settings.client_token_audience)
    with pytest.raises(DomainError) as exc:
        decode_token(client_token, settings.admin_token_audience)
    assert exc.value.code == "PERMISSION_DENIED"
    assert exc.value.http_status == 401

    admin_token = create_access_token("admin1", settings.admin_token_audience)
    with pytest.raises(DomainError):
        decode_token(admin_token, settings.client_token_audience)


def test_tampered_token_rejected():
    token = create_access_token("user123", settings.client_token_audience)
    tampered = token[:-2] + ("aa" if not token.endswith("aa") else "bb")
    with pytest.raises(DomainError):
        decode_token(tampered, settings.client_token_audience)


def test_expired_token_rejected():
    with freeze_time("2026-01-01 12:00:00") as clock:
        token = create_access_token("user123", settings.client_token_audience)
        decode_token(token, settings.client_token_audience)  # valid now
        clock.tick(datetime.timedelta(hours=2))  # far past any test TTL
        with pytest.raises(DomainError) as exc:
            decode_token(token, settings.client_token_audience)
        assert exc.value.code == "PERMISSION_DENIED"


def test_refresh_token_type_and_longer_ttl():
    access = create_access_token("u", settings.client_token_audience)
    refresh = create_refresh_token("u", settings.client_token_audience)
    a = decode_token(access, settings.client_token_audience)
    r = decode_token(refresh, settings.client_token_audience)
    assert r.type == "refresh"
    assert r.exp > a.exp
