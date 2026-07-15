"""Client realm auth: §4 login flow, forced reset, blocking, lockout,
audience separation (docs/AUTH_RBAC.md acceptance criteria)."""

from __future__ import annotations

from app.core.db import get_db_manager

from ..conftest import OWNER_PASSWORD


async def test_owner_first_login_forced_reset_flow(client, onboarded_company):
    login = {"company": onboarded_company["slug"],
             "email": onboarded_company["owner_email"]}

    res = await client.post("/api/v1/auth/login", json={
        **login, "password": onboarded_company["temp_password"],
    })
    assert res.status_code == 200
    first = res.json()["data"]
    assert first["password_reset_required"] is True

    res = await client.post(
        "/api/v1/auth/change-password",
        json={"current_password": onboarded_company["temp_password"],
              "new_password": "NewSecret123!"},
        headers={"Authorization": f"Bearer {first['access_token']}"},
    )
    assert res.status_code == 200

    # temp password no longer works; new one does, flag cleared
    res = await client.post("/api/v1/auth/login", json={
        **login, "password": onboarded_company["temp_password"],
    })
    assert res.status_code == 401
    res = await client.post("/api/v1/auth/login",
                            json={**login, "password": "NewSecret123!"})
    assert res.status_code == 200
    assert res.json()["data"]["password_reset_required"] is False

    # activity log recorded the logins
    tenant_db = get_db_manager().tenant(onboarded_company["company"]["db_name"])
    assert await tenant_db.activity_log.count_documents({"action": "auth.login"}) >= 2


async def test_unknown_company_and_blocked_company(client, admin_client, onboarded_company):
    res = await client.post("/api/v1/auth/login", json={
        "company": "ghost-co", "email": "x@y.z", "password": "p",
    })
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "TENANT_NOT_FOUND"

    company_id = str(onboarded_company["company"]["_id"])
    res = await admin_client.patch(
        f"/api/v1/admin/companies/{company_id}/status", json={"status": "blocked"}
    )
    assert res.status_code == 200

    res = await client.post("/api/v1/auth/login", json={
        "company": onboarded_company["slug"],
        "email": onboarded_company["owner_email"],
        "password": onboarded_company["temp_password"],
    })
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "TENANT_BLOCKED"


async def test_company_block_kills_existing_tokens(
    client, admin_client, client_client, onboarded_company
):
    assert (await client_client.get("/api/v1/auth/me")).status_code == 200

    company_id = str(onboarded_company["company"]["_id"])
    await admin_client.patch(f"/api/v1/admin/companies/{company_id}/status",
                             json={"status": "blocked"})

    res = await client_client.get("/api/v1/auth/me")  # same live token
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "TENANT_BLOCKED"

    # refresh dies too
    res = await client.post("/api/v1/auth/refresh", json={
        "refresh_token": client_client.tokens["refresh_token"],
    })
    assert res.status_code == 403


async def test_employee_block_and_unblock(client, admin_client, client_client, onboarded_company):
    company_id = str(onboarded_company["company"]["_id"])
    tenant_db = get_db_manager().tenant(onboarded_company["company"]["db_name"])
    owner = await tenant_db.users.find_one({"email": onboarded_company["owner_email"]})
    uid = str(owner["_id"])

    res = await admin_client.patch(
        f"/api/v1/admin/companies/{company_id}/employees/{uid}/block",
        json={"blocked": True},
    )
    assert res.status_code == 200

    # login rejected AND existing token invalidated
    res = await client.post("/api/v1/auth/login", json={
        "company": onboarded_company["slug"],
        "email": onboarded_company["owner_email"],
        "password": OWNER_PASSWORD,
    })
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "USER_BLOCKED"
    assert (await client_client.get("/api/v1/auth/me")).status_code == 403

    # unblock restores login
    await admin_client.patch(
        f"/api/v1/admin/companies/{company_id}/employees/{uid}/block",
        json={"blocked": False},
    )
    res = await client.post("/api/v1/auth/login", json={
        "company": onboarded_company["slug"],
        "email": onboarded_company["owner_email"],
        "password": OWNER_PASSWORD,
    })
    assert res.status_code == 200


async def test_client_lockout_uses_company_threshold_and_admin_unlock(
    client, admin_client, client_client, onboarded_company
):
    """Company threshold is 3 (fixture). N bad → locked; correct password
    still fails; admin unlock endpoint restores access (acceptance #1)."""
    login = {"company": onboarded_company["slug"],
             "email": onboarded_company["owner_email"]}
    for _ in range(3):
        res = await client.post("/api/v1/auth/login",
                                json={**login, "password": "wrong"})
        assert res.status_code == 401

    res = await client.post("/api/v1/auth/login",
                            json={**login, "password": OWNER_PASSWORD})
    assert res.status_code == 423
    assert res.json()["error"]["code"] == "ACCOUNT_LOCKED"
    assert int(res.headers["Retry-After"]) > 0

    company_id = str(onboarded_company["company"]["_id"])
    tenant_db = get_db_manager().tenant(onboarded_company["company"]["db_name"])
    owner = await tenant_db.users.find_one({"email": onboarded_company["owner_email"]})
    res = await admin_client.post(
        f"/api/v1/admin/companies/{company_id}/employees/{owner['_id']}/unlock"
    )
    assert res.status_code == 200

    res = await client.post("/api/v1/auth/login",
                            json={**login, "password": OWNER_PASSWORD})
    assert res.status_code == 200


async def test_admin_password_reset_forces_change(client, admin_client, onboarded_company):
    company_id = str(onboarded_company["company"]["_id"])
    tenant_db = get_db_manager().tenant(onboarded_company["company"]["db_name"])
    owner = await tenant_db.users.find_one({"email": onboarded_company["owner_email"]})

    res = await admin_client.post(
        f"/api/v1/admin/companies/{company_id}/employees/{owner['_id']}/reset-password"
    )
    assert res.status_code == 200
    temp = res.json()["data"]["temp_password"]

    res = await client.post("/api/v1/auth/login", json={
        "company": onboarded_company["slug"],
        "email": onboarded_company["owner_email"],
        "password": temp,
    })
    assert res.status_code == 200
    assert res.json()["data"]["password_reset_required"] is True


async def test_audience_separation_both_directions(admin_client, client_client):
    """An admin token cannot call any client endpoint and vice-versa."""
    res = await admin_client.get("/api/v1/auth/me")  # admin token → client route
    assert res.status_code == 401
    assert res.json()["error"]["code"] == "PERMISSION_DENIED"

    res = await client_client.get("/api/v1/admin/auth/me")  # client token → admin route
    assert res.status_code == 401
    assert res.json()["error"]["code"] == "PERMISSION_DENIED"

    # and a client token can't hit admin company endpoints
    res = await client_client.patch(
        "/api/v1/admin/companies/000000000000000000000000/status",
        json={"status": "blocked"},
    )
    assert res.status_code == 401
