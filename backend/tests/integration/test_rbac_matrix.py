"""Permission matrix (docs/TESTING.md §3): for a client resource ×
{NONE, VIEW, READ, WRITE}, assert GET/POST allow/deny correctly. Plus the
admin-role matrix over real admin endpoints."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi import APIRouter, Depends

from app.core.db import get_db_manager
from app.core.security import hash_password
from app.modules.settings.seed import CLIENT_RESOURCES
from app.shared.enums import Level
from app.shared.schemas import envelope
from app.tenant.deps import require

from ..conftest import ADMIN_PASSWORD

# Probe routes guarded exactly like real module routes will be:
# READ for GET, WRITE for mutations (docs/modules/*.md).
probe = APIRouter(prefix="/api/v1/crm-probe")


@probe.get("/records")
async def list_records(principal=Depends(require("crm", Level.READ))):
    return envelope([])


@probe.post("/records")
async def create_record(principal=Depends(require("crm", Level.WRITE))):
    return envelope({"created": True})


@pytest.fixture
async def probe_app(app):
    app.include_router(probe)
    return app


async def _make_user_with_level(tenant_db, slug: str, level: Level) -> dict:
    """Custom role with crm=<level>, plus a user holding it."""
    now = datetime.now(UTC)
    role = {
        "name": f"probe-{level.name.lower()}",
        "permissions": {res: 0 for res in CLIENT_RESOURCES} | {"crm": int(level)},
        "created_at": now, "updated_at": now,
    }
    role_id = (await tenant_db.roles.insert_one(role)).inserted_id
    email = f"{level.name.lower()}@{slug}.com"
    await tenant_db.users.insert_one({
        "email": email, "password_hash": hash_password("ProbePass123!"),
        "name": f"Probe {level.name}", "role_id": role_id,
        "is_blocked": False, "failed_attempts": 0, "locked_until": None,
        "must_reset_password": False, "last_login_at": None,
        "refresh_jtis": [], "created_at": now, "updated_at": now,
    })
    return {"email": email, "password": "ProbePass123!"}


MATRIX = [
    # level        GET /records  POST /records
    (Level.NONE,   403,          403),
    (Level.VIEW,   403,          403),  # VIEW: sees it exists, cannot open details
    (Level.READ,   200,          403),
    (Level.WRITE,  200,          200),
]


@pytest.mark.parametrize("level,get_status,post_status", MATRIX)
async def test_client_permission_matrix(
    probe_app, client, onboarded_company, level, get_status, post_status
):
    tenant_db = get_db_manager().tenant(onboarded_company["company"]["db_name"])
    creds = await _make_user_with_level(tenant_db, onboarded_company["slug"], level)

    res = await client.post("/api/v1/auth/login", json={
        "company": onboarded_company["slug"], **creds,
    })
    assert res.status_code == 200
    headers = {"Authorization": f"Bearer {res.json()['data']['access_token']}"}

    got = await client.get("/api/v1/crm-probe/records", headers=headers)
    posted = await client.post("/api/v1/crm-probe/records", headers=headers)
    assert got.status_code == get_status
    assert posted.status_code == post_status
    if get_status == 403:
        res = await client.get("/api/v1/crm-probe/records", headers=headers)
        assert res.json()["error"]["code"] == "PERMISSION_DENIED"


ADMIN_MATRIX = [
    # role          PATCH status  POST unlock (security_policy WRITE)
    ("Operator",    200,          200),
    ("Auditor",     403,          403),
    ("Observer",    403,          403),
]


@pytest.mark.parametrize("role_name,status_code,unlock_code", ADMIN_MATRIX)
async def test_admin_permission_matrix(
    client, control_seeded, onboarded_company, role_name, status_code, unlock_code
):
    control = get_db_manager().control
    email = f"{role_name.lower()}@test.local"
    now = datetime.now(UTC)
    await control.admin_users.update_one(
        {"email": email},
        {"$setOnInsert": {
            "email": email, "password_hash": hash_password(ADMIN_PASSWORD),
            "name": role_name, "role_id": control_seeded["role_ids"][role_name],
            "is_active": True, "failed_attempts": 0, "locked_until": None,
            "refresh_jtis": [], "created_at": now, "updated_at": now,
        }},
        upsert=True,
    )
    res = await client.post("/api/v1/admin/auth/login",
                            json={"email": email, "password": ADMIN_PASSWORD})
    headers = {"Authorization": f"Bearer {res.json()['data']['access_token']}"}

    company_id = str(onboarded_company["company"]["_id"])
    res = await client.patch(
        f"/api/v1/admin/companies/{company_id}/status",
        json={"status": "active"}, headers=headers,
    )
    assert res.status_code == status_code

    tenant_db = get_db_manager().tenant(onboarded_company["company"]["db_name"])
    owner = await tenant_db.users.find_one({"email": onboarded_company["owner_email"]})
    res = await client.post(
        f"/api/v1/admin/companies/{company_id}/employees/{owner['_id']}/unlock",
        headers=headers,
    )
    assert res.status_code == unlock_code
