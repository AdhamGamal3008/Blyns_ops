"""Admin users & roles CRUD (docs/ADMIN_PORTAL.md §3): lockout-prevention
guards, unknown-resource rejection, live permission re-evaluation."""

from __future__ import annotations

import uuid

from ..conftest import ADMIN_PASSWORD


async def _login(client, email: str) -> dict:
    res = await client.post("/api/v1/admin/auth/login",
                            json={"email": email, "password": ADMIN_PASSWORD})
    assert res.status_code == 200, res.text
    return {"Authorization": f"Bearer {res.json()['data']['access_token']}"}


async def test_admin_user_crud_and_last_manager_guard(client, admin_client, control_seeded):
    # create a second super admin
    email = f"sa-{uuid.uuid4().hex[:6]}@test.local"
    res = await admin_client.post("/api/v1/admin/admin-users", json={
        "email": email, "name": "Second SA",
        "role_id": str(control_seeded["role_ids"]["Super Admin"]),
        "password": ADMIN_PASSWORD,
    })
    assert res.status_code == 201
    second_id = res.json()["data"]["id"]

    # demote them to Observer — allowed (root still manages admins)
    res = await admin_client.patch(f"/api/v1/admin/admin-users/{second_id}", json={
        "role_id": str(control_seeded["role_ids"]["Observer"]),
    })
    assert res.status_code == 200

    # root is now the last admin-manager: deleting/deactivating root is blocked
    root = await admin_client.get("/api/v1/admin/auth/me")
    root_id = root.json()["data"]["id"]
    res = await admin_client.delete(f"/api/v1/admin/admin-users/{root_id}")
    assert res.status_code == 409
    res = await admin_client.patch(f"/api/v1/admin/admin-users/{root_id}",
                                   json={"is_active": False})
    assert res.status_code == 409

    # deleting the demoted admin is fine
    res = await admin_client.delete(f"/api/v1/admin/admin-users/{second_id}")
    assert res.status_code == 200


async def test_role_crud_validation_and_in_use_guard(client, admin_client, control_seeded):
    # unknown resource rejected (role editor contract)
    res = await admin_client.post("/api/v1/admin/admin-roles", json={
        "name": f"bad-{uuid.uuid4().hex[:6]}", "permissions": {"warp_drive": 3},
    })
    assert res.status_code == 422

    # create a role, assign it, then deletion is blocked while in use
    role_name = f"custom-{uuid.uuid4().hex[:6]}"
    res = await admin_client.post("/api/v1/admin/admin-roles", json={
        "name": role_name, "permissions": {"dashboard": 2},
    })
    assert res.status_code == 201
    role_id = res.json()["data"]["id"]

    email = f"holder-{uuid.uuid4().hex[:6]}@test.local"
    res = await admin_client.post("/api/v1/admin/admin-users", json={
        "email": email, "name": "Holder", "role_id": role_id,
        "password": ADMIN_PASSWORD,
    })
    holder_id = res.json()["data"]["id"]

    res = await admin_client.delete(f"/api/v1/admin/admin-roles/{role_id}")
    assert res.status_code == 409

    await admin_client.delete(f"/api/v1/admin/admin-users/{holder_id}")
    res = await admin_client.delete(f"/api/v1/admin/admin-roles/{role_id}")
    assert res.status_code == 200


async def test_role_edit_reevaluates_on_next_request(client, admin_client, control_seeded):
    """Editing a role changes what holders can access immediately (§3)."""
    role_name = f"dyn-{uuid.uuid4().hex[:6]}"
    res = await admin_client.post("/api/v1/admin/admin-roles", json={
        "name": role_name, "permissions": {},  # NONE on everything
    })
    role_id = res.json()["data"]["id"]

    email = f"dyn-{uuid.uuid4().hex[:6]}@test.local"
    await admin_client.post("/api/v1/admin/admin-users", json={
        "email": email, "name": "Dyn", "role_id": role_id,
        "password": ADMIN_PASSWORD,
    })
    headers = await _login(client, email)

    res = await client.get("/api/v1/admin/companies", headers=headers)
    assert res.status_code == 403  # companies NONE

    await admin_client.patch(f"/api/v1/admin/admin-roles/{role_id}", json={
        "permissions": {"companies": 2},  # READ
    })
    res = await client.get("/api/v1/admin/companies", headers=headers)
    assert res.status_code == 200  # same token, new permissions
