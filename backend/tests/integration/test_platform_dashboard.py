"""Platform dashboard (docs/ADMIN_PORTAL.md §4, §6): panels from snapshots +
live host stats, no external service; VIEW gets headline counts only."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from app.core.db import get_db_manager
from app.core.security import hash_password

from ..conftest import ADMIN_PASSWORD


async def test_collect_then_dashboard_panels(admin_client, client_client, onboarded_company):
    # client_client already logged in → tenant activity + request buckets exist
    res = await admin_client.post("/api/v1/admin/metrics/collect")
    assert res.status_code == 200
    assert res.json()["data"]["tenants"] >= 1

    res = await admin_client.get("/api/v1/admin/dashboard")
    assert res.status_code == 200
    data = res.json()["data"]

    # 4.1 host (live psutil)
    assert data["host"]["cpu_pct"] >= 0
    assert data["host"]["memory"]["pct"] > 0
    assert data["host"]["disk"]["total"] > 0
    assert data["host"]["process"]["uptime_sec"] >= 0

    # 4.2 rates (from rate_limit_buckets)
    assert data["rates"]["requests_last_min"] >= 1

    # 4.3 storage (from platform_metrics snapshots)
    assert data["storage"]["control"]["data_size"] > 0
    tenant_ids = [t["tenant_id"] for t in data["storage"]["tenants"]]
    assert str(onboarded_company["company"]["_id"]) in tenant_ids
    assert data["storage"]["total_storage"] > 0
    assert data["storage"]["trend"]

    # 4.4 activity (registry + snapshots)
    act = data["activity"]
    assert act["companies_total"] >= 1
    mine = next(p for p in act["per_company"]
                if p["slug"] == onboarded_company["slug"])
    assert mine["seats_used"] == 1
    assert mine["logins_24h"] >= 1
    assert mine["module_usage"].get("auth", 0) >= 1


async def test_view_level_dashboard_headlines_only(client, admin_client, control_seeded):
    email = f"obs-{uuid.uuid4().hex[:6]}@test.local"
    now = datetime.now(UTC)
    control = get_db_manager().control
    await control.admin_users.insert_one({
        "email": email, "password_hash": hash_password(ADMIN_PASSWORD),
        "name": "Obs", "role_id": control_seeded["role_ids"]["Observer"],
        "is_active": True, "failed_attempts": 0, "locked_until": None,
        "refresh_jtis": [], "created_at": now, "updated_at": now,
    })
    res = await client.post("/api/v1/admin/auth/login",
                            json={"email": email, "password": ADMIN_PASSWORD})
    headers = {"Authorization": f"Bearer {res.json()['data']['access_token']}"}

    res = await client.get("/api/v1/admin/dashboard", headers=headers)
    assert res.status_code == 200
    data = res.json()["data"]
    assert set(data) == {"companies_total", "companies_active", "storage_total"}

    # Observer cannot trigger collection (dashboard WRITE required)
    res = await client.post("/api/v1/admin/metrics/collect", headers=headers)
    assert res.status_code == 403


async def test_audit_log_endpoint(admin_client, onboarded_company):
    res = await admin_client.get("/api/v1/admin/audit-log?page_size=10")
    assert res.status_code == 200
    body = res.json()
    assert body["meta"]["total"] >= 1
    actions = [e["action"] for e in body["data"]]
    assert "company.onboarded" in actions or "admin.auth.login" in actions

    res = await admin_client.get("/api/v1/admin/audit-log?action=company.onboarded")
    assert all(e["action"] == "company.onboarded" for e in res.json()["data"])
