"""Admin IP access rules API (docs/IP_ACCESS_CONTROL_PLAN.md §2-F, P5).

CRUD round-trip, duplicate/validation guards, audit rows, the IP-test verdict
(the lockout-preventer), the `ip_rules` RBAC gate, and — the P4↔P5 seam — that a
write invalidates the shared ruleset cache the enforcement middleware reads.
"""

from __future__ import annotations

from datetime import UTC, datetime

import httpx

from app.control_plane.ip_access.matcher import decide
from app.control_plane.ip_access.repository import COLLECTION
from app.control_plane.ip_access.runtime import get_rule_cache, reset_runtime
from app.core.db import get_db_manager
from app.core.security import hash_password

from ..conftest import ADMIN_PASSWORD

BASE = "/api/v1/admin/ip-rules"


async def _clear(*values: str) -> None:
    control = get_db_manager().control
    await control[COLLECTION].delete_many({"value": {"$in": list(values)}})


async def _authed_admin(app, client, control_seeded, role_name: str) -> httpx.AsyncClient:
    """An authed client for an admin holding `role_name` (created idempotently and
    reset to a clean, unlocked state so it's order-independent)."""
    control = get_db_manager().control
    email = f"{role_name.lower()}@test.local"
    now = datetime.now(UTC)
    await control.admin_users.update_one(
        {"email": email},
        {"$setOnInsert": {
            "email": email, "password_hash": hash_password(ADMIN_PASSWORD),
            "name": role_name, "role_id": control_seeded["role_ids"][role_name],
            "refresh_jtis": [], "created_at": now,
        },
         "$set": {"is_active": True, "failed_attempts": 0,
                  "locked_until": None, "updated_at": now}},
        upsert=True,
    )
    res = await client.post("/api/v1/admin/auth/login",
                            json={"email": email, "password": ADMIN_PASSWORD})
    assert res.status_code == 200, res.text
    token = res.json()["data"]["access_token"]
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test",
        headers={"Authorization": f"Bearer {token}"},
    )


async def test_crud_round_trip(admin_client):
    await _clear("203.0.113.10")

    res = await admin_client.post(BASE, json={
        "kind": "deny", "match_type": "ip", "value": "203.0.113.10", "reason": "abuse",
    })
    assert res.status_code == 201, res.text
    rule = res.json()["data"]
    rid = rule["id"]
    assert rule["kind"] == "deny" and rule["value"] == "203.0.113.10"
    assert rule["source"] == "manual" and rule["enabled"] is True
    assert rule["family"] == 4

    res = await admin_client.get(f"{BASE}?kind=deny&match_type=ip&page_size=100")
    assert rid in [r["id"] for r in res.json()["data"]]

    res = await admin_client.patch(f"{BASE}/{rid}", json={"enabled": False})
    assert res.status_code == 200 and res.json()["data"]["enabled"] is False

    res = await admin_client.delete(f"{BASE}/{rid}")
    assert res.status_code == 200 and res.json()["data"]["deleted"] is True

    res = await admin_client.get(f"{BASE}?page_size=100")
    assert rid not in [r["id"] for r in res.json()["data"]]  # gone from live listing


async def test_duplicate_rule_is_rejected(admin_client):
    await _clear("203.0.113.11")
    body = {"kind": "deny", "match_type": "ip", "value": "203.0.113.11"}
    assert (await admin_client.post(BASE, json=body)).status_code == 201
    dup = await admin_client.post(BASE, json=body)
    assert dup.status_code == 409
    assert dup.json()["error"]["code"] == "IP_RULE_EXISTS"


async def test_malformed_values_are_422(admin_client):
    for body in (
        {"kind": "deny", "match_type": "ip", "value": "999.1.1.1"},
        {"kind": "deny", "match_type": "cidr", "value": "203.0.113.0/33"},
        {"kind": "deny", "match_type": "country", "value": "USA"},
    ):
        res = await admin_client.post(BASE, json=body)
        assert res.status_code == 422, f"{body} -> {res.status_code}"


async def test_writes_are_audited(admin_client):
    await _clear("198.51.100.20")
    control = get_db_manager().control
    rid = (await admin_client.post(BASE, json={
        "kind": "allow", "match_type": "ip", "value": "198.51.100.20"})).json()["data"]["id"]
    await admin_client.patch(f"{BASE}/{rid}", json={"reason": "office"})
    await admin_client.delete(f"{BASE}/{rid}")

    actions = [d["action"] async for d in
               control.admin_audit_log.find({"target.id": rid}).sort("occurred_at", 1)]
    assert actions == ["ip_rule.created", "ip_rule.updated", "ip_rule.deleted"]


async def test_ip_tester_verdicts(admin_client):
    await _clear("203.0.113.0/24", "203.0.113.50")
    # deny a /24, then allow one host inside it (allowlist must win)
    await admin_client.post(BASE, json={
        "kind": "deny", "match_type": "cidr", "value": "203.0.113.0/24"})
    await admin_client.post(BASE, json={
        "kind": "allow", "match_type": "ip", "value": "203.0.113.50"})

    denied = (await admin_client.post(f"{BASE}/test",
              json={"ip": "203.0.113.9"})).json()["data"]
    assert denied["allowed"] is False
    assert denied["matched_rule"]["match_type"] == "cidr"

    allowed = (await admin_client.post(f"{BASE}/test",
               json={"ip": "203.0.113.50"})).json()["data"]
    assert allowed["allowed"] is True and allowed["reason"] == "allowlisted"

    default = (await admin_client.post(f"{BASE}/test",
               json={"ip": "8.8.8.8"})).json()["data"]
    assert default["allowed"] is True and default["reason"] == "default_allow"
    assert default["matched_rule"] is None

    bad = await admin_client.post(f"{BASE}/test", json={"ip": "not-an-ip"})
    assert bad.status_code == 422


async def test_rbac_gate_blocks_non_privileged_admin(app, client, control_seeded):
    operator = await _authed_admin(app, client, control_seeded, "Operator")
    async with operator:
        assert (await operator.get(BASE)).status_code == 403
        created = await operator.post(BASE, json={
            "kind": "deny", "match_type": "ip", "value": "203.0.113.77"})
        assert created.status_code == 403
        assert created.json()["error"]["code"] == "PERMISSION_DENIED"
        assert (await operator.post(f"{BASE}/test",
                json={"ip": "1.2.3.4"})).status_code == 403


async def test_create_invalidates_the_shared_cache(admin_client):
    """The P4↔P5 seam: an admin write drops the cached ruleset the middleware
    reads, so the new rule is enforced without waiting for the TTL."""
    await _clear("198.51.100.200")
    reset_runtime()
    cache = get_rule_cache()
    before = await cache.get()
    assert decide("198.51.100.200", before).allowed is True  # not a rule yet

    res = await admin_client.post(BASE, json={
        "kind": "deny", "match_type": "ip", "value": "198.51.100.200"})
    assert res.status_code == 201

    after = await cache.get()  # the write invalidated the cache -> reload
    assert decide("198.51.100.200", after).allowed is False
    reset_runtime()
