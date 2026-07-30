"""Admin portal must-haves (docs/TESTING.md §3, docs/ADMIN_PORTAL.md §6):
onboarding via API, companies CRUD, seat enforcement, module enabling,
teardown confirmation."""

from __future__ import annotations

import uuid

from app.core.db import get_db_manager


def onboard_body(slug: str, **overrides) -> dict:
    body = {
        "name": f"{slug} Inc", "slug": slug, "seat_limit": 3,
        "enabled_modules": ["dashboard", "settings", "crm"],
        "owner": {"name": "Owner One", "email": f"owner@{slug}.com"},
        "security": {"failed_login_threshold": 3, "lockout_minutes": 15},
    }
    body.update(overrides)
    return body


def uslug() -> str:
    return f"co-{uuid.uuid4().hex[:8]}"


async def test_onboarding_endpoint_end_to_end(client, admin_client):
    slug = uslug()
    res = await admin_client.post("/api/v1/admin/companies", json=onboard_body(slug))
    assert res.status_code == 201, res.text
    data = res.json()["data"]
    assert data["company"]["status"] == "active"
    assert data["owner_temp_password"]
    job_id = data["provisioning_job_id"]
    company_id = data["company"]["id"]

    # provisioning progress endpoint shows the finished job
    res = await admin_client.get(f"/api/v1/admin/companies/{company_id}/provisioning")
    assert res.status_code == 200
    job = res.json()["data"]
    assert job["id"] == job_id and job["state"] == "done"

    # the owner can actually log in with the returned temp password
    res = await client.post("/api/v1/auth/login", json={
        "company": slug, "email": f"owner@{slug}.com",
        "password": data["owner_temp_password"],
    })
    assert res.status_code == 200
    assert res.json()["data"]["password_reset_required"] is True


async def test_list_filter_and_pagination(admin_client):
    slug = uslug()
    await admin_client.post("/api/v1/admin/companies", json=onboard_body(slug))
    res = await admin_client.get(f"/api/v1/admin/companies?q={slug}&page_size=5")
    assert res.status_code == 200
    body = res.json()
    assert body["meta"]["total"] == 1
    assert body["data"][0]["slug"] == slug
    res = await admin_client.get("/api/v1/admin/companies?status=provisioning")
    assert all(c["status"] == "provisioning" for c in res.json()["data"])


async def test_patch_enabled_modules_runs_seed(admin_client):
    slug = uslug()
    res = await admin_client.post("/api/v1/admin/companies", json=onboard_body(slug))
    company_id = res.json()["data"]["company"]["id"]
    db_name = res.json()["data"]["company"]["db_name"]

    t = get_db_manager().tenant(db_name)
    assert await t.stage_definitions.count_documents({}) == 0  # projects disabled

    res = await admin_client.patch(f"/api/v1/admin/companies/{company_id}", json={
        "enabled_modules": ["dashboard", "settings", "crm", "projects"],
    })
    assert res.status_code == 200
    assert "projects" in res.json()["data"]["enabled_modules"]
    assert await t.stage_definitions.count_documents({}) == 9  # seed ran


async def test_seat_limit_enforced_on_admin_employee_create(admin_client):
    slug = uslug()
    res = await admin_client.post(
        "/api/v1/admin/companies", json=onboard_body(slug, seat_limit=2)
    )
    company_id = res.json()["data"]["company"]["id"]

    # owner used 1 of 2 seats; one more fits
    res = await admin_client.post(
        f"/api/v1/admin/companies/{company_id}/employees",
        json={"name": "Emp Two", "email": f"two@{slug}.com"},
    )
    assert res.status_code == 201
    assert res.json()["data"]["temp_password"]

    # third employee exceeds the limit
    res = await admin_client.post(
        f"/api/v1/admin/companies/{company_id}/employees",
        json={"name": "Emp Three", "email": f"three@{slug}.com"},
    )
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "SEAT_LIMIT_REACHED"

    res = await admin_client.get(f"/api/v1/admin/companies/{company_id}/employees")
    employees = res.json()["data"]
    assert len(employees) == 2
    assert all("password_hash" not in e for e in employees)


async def test_lowering_seats_below_used_needs_force(admin_client):
    slug = uslug()
    res = await admin_client.post(
        "/api/v1/admin/companies", json=onboard_body(slug, seat_limit=5)
    )
    company_id = res.json()["data"]["company"]["id"]
    await admin_client.post(
        f"/api/v1/admin/companies/{company_id}/employees",
        json={"name": "E2", "email": f"e2@{slug}.com"},
    )  # seats_used = 2

    res = await admin_client.patch(
        f"/api/v1/admin/companies/{company_id}/seats", json={"seat_limit": 1}
    )
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "SEAT_LIMIT_REACHED"

    res = await admin_client.patch(
        f"/api/v1/admin/companies/{company_id}/seats",
        json={"seat_limit": 1, "force": True},
    )
    assert res.status_code == 200

    # increasing is always allowed
    res = await admin_client.patch(
        f"/api/v1/admin/companies/{company_id}/seats", json={"seat_limit": 50}
    )
    assert res.status_code == 200


async def test_teardown_requires_slug_confirmation(admin_client):
    slug = uslug()
    res = await admin_client.post("/api/v1/admin/companies", json=onboard_body(slug))
    company_id = res.json()["data"]["company"]["id"]
    db_name = res.json()["data"]["company"]["db_name"]

    res = await admin_client.delete(
        f"/api/v1/admin/companies/{company_id}?confirm=wrong-slug"
    )
    assert res.status_code == 409

    res = await admin_client.delete(
        f"/api/v1/admin/companies/{company_id}?confirm={slug}"
    )
    assert res.status_code == 200
    dbs = await get_db_manager().raw_client().list_database_names()
    assert db_name not in dbs
    detail = await admin_client.get(f"/api/v1/admin/companies/{company_id}")
    assert detail.json()["data"]["status"] == "suspended"
