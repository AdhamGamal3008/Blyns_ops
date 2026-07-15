"""Admin realm auth: login, lockout, refresh rotation, logout, deactivation."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.core.db import get_db_manager

from ..conftest import ADMIN_EMAIL, ADMIN_PASSWORD


async def test_login_and_me(client, control_seeded):
    res = await client.post("/api/v1/admin/auth/login", json={
        "email": ADMIN_EMAIL, "password": ADMIN_PASSWORD,
    })
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["token_type"] == "bearer"
    assert data["user"]["email"] == ADMIN_EMAIL

    me = await client.get("/api/v1/admin/auth/me", headers={
        "Authorization": f"Bearer {data['access_token']}",
    })
    assert me.status_code == 200
    assert me.json()["data"]["role"]["name"] == "Super Admin"


async def test_wrong_password_is_generic(client, control_seeded):
    res = await client.post("/api/v1/admin/auth/login", json={
        "email": ADMIN_EMAIL, "password": "nope",
    })
    assert res.status_code == 401
    assert res.json()["error"]["code"] == "INVALID_CREDENTIALS"

    res = await client.post("/api/v1/admin/auth/login", json={
        "email": "ghost@test.local", "password": "nope",
    })
    assert res.status_code == 401
    assert res.json()["error"]["code"] == "INVALID_CREDENTIALS"  # same shape


async def test_lockout_after_threshold_then_unlock(client, control_seeded):
    """3 bad attempts (test threshold) lock the account; the correct password
    still fails during the window; clearing the lock restores access."""
    login = {"email": ADMIN_EMAIL, "password": "wrong"}
    for _ in range(2):
        assert (await client.post("/api/v1/admin/auth/login", json=login)).status_code == 401
    res = await client.post("/api/v1/admin/auth/login", json=login)  # 3rd → locks
    assert res.status_code == 401

    # correct password during lockout → ACCOUNT_LOCKED with Retry-After
    res = await client.post("/api/v1/admin/auth/login", json={
        "email": ADMIN_EMAIL, "password": ADMIN_PASSWORD,
    })
    assert res.status_code == 423
    assert res.json()["error"]["code"] == "ACCOUNT_LOCKED"
    assert int(res.headers["Retry-After"]) > 0

    # window elapsed (simulated) → login succeeds again
    control = get_db_manager().control
    await control.admin_users.update_one(
        {"email": ADMIN_EMAIL},
        {"$set": {"locked_until": datetime.now(UTC) - timedelta(seconds=1)}},
    )
    res = await client.post("/api/v1/admin/auth/login", json={
        "email": ADMIN_EMAIL, "password": ADMIN_PASSWORD,
    })
    assert res.status_code == 200


async def test_refresh_rotation_and_replay_rejected(client, control_seeded):
    res = await client.post("/api/v1/admin/auth/login", json={
        "email": ADMIN_EMAIL, "password": ADMIN_PASSWORD,
    })
    old_refresh = res.json()["data"]["refresh_token"]

    res = await client.post("/api/v1/admin/auth/refresh",
                            json={"refresh_token": old_refresh})
    assert res.status_code == 200
    new_refresh = res.json()["data"]["refresh_token"]
    assert new_refresh != old_refresh

    # replaying the consumed token is rejected; the new one still works
    res = await client.post("/api/v1/admin/auth/refresh",
                            json={"refresh_token": old_refresh})
    assert res.status_code == 401
    res = await client.post("/api/v1/admin/auth/refresh",
                            json={"refresh_token": new_refresh})
    assert res.status_code == 200


async def test_logout_revokes_refresh(client, control_seeded):
    res = await client.post("/api/v1/admin/auth/login", json={
        "email": ADMIN_EMAIL, "password": ADMIN_PASSWORD,
    })
    data = res.json()["data"]
    res = await client.post("/api/v1/admin/auth/logout", headers={
        "Authorization": f"Bearer {data['access_token']}",
    })
    assert res.status_code == 200
    res = await client.post("/api/v1/admin/auth/refresh",
                            json={"refresh_token": data["refresh_token"]})
    assert res.status_code == 401


async def test_deactivated_admin_rejected_including_live_token(client, control_seeded):
    res = await client.post("/api/v1/admin/auth/login", json={
        "email": ADMIN_EMAIL, "password": ADMIN_PASSWORD,
    })
    token = res.json()["data"]["access_token"]

    control = get_db_manager().control
    await control.admin_users.update_one(
        {"email": ADMIN_EMAIL}, {"$set": {"is_active": False}}
    )
    # login rejected
    res = await client.post("/api/v1/admin/auth/login", json={
        "email": ADMIN_EMAIL, "password": ADMIN_PASSWORD,
    })
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "USER_BLOCKED"
    # existing access token rejected too (re-checked per request)
    res = await client.get("/api/v1/admin/auth/me",
                           headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 403
