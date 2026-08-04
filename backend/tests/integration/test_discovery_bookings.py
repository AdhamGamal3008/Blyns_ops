"""Discovery-booking APIs (docs/LANDING_PAGE.md §4).

The public unauthenticated submit (persist, validation, honeypot drop), the admin
list/detail/patch round-trip, the audit row, the `leads` RBAC ladder (VIEW masks
PII, READ can read, WRITE can write), and 404 on an unknown id.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import httpx
import pytest

from app.control_plane.discovery_bookings.repository import COLLECTION
from app.core.db import get_db_manager
from app.core.security import hash_password

from ..conftest import ADMIN_PASSWORD

ADMIN = "/api/v1/admin/discovery-bookings"
PUBLIC = "/api/v1/public/discovery-bookings"


@pytest.fixture(autouse=True)
async def _clean(app):
    """Deterministic listing/counts: start each test with an empty collection."""
    await get_db_manager().control[COLLECTION].delete_many({})
    yield


def _payload(**over: object) -> dict:
    body: dict = {
        "full_name": "Dana Cole",
        "work_email": f"dana-{uuid4().hex[:8]}@acme.com",
        "company": "Acme Interiors",
        "industry": "interior_fit_out",
    }
    body.update(over)
    return body


async def _authed_admin(app, client, control_seeded, role_name: str) -> httpx.AsyncClient:
    """Authed client for an admin holding `role_name` (idempotent + reset clean)."""
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


# --- public submit ---------------------------------------------------------

async def test_public_submit_persists_and_reaches_admin(client, admin_client):
    body = _payload(phone="+1 555 0100", company_size="11-50",
                    message="We fit out clinics.")
    res = await client.post(PUBLIC, json=body)
    assert res.status_code == 201, res.text
    assert res.json()["data"] == {"received": True}

    # Persisted as a control-plane lead with server-side defaults.
    doc = await get_db_manager().control[COLLECTION].find_one(
        {"work_email": body["work_email"]})
    assert doc is not None
    assert doc["status"] == "new"
    assert doc["source"] == "landing"
    assert doc["source_ip"] == "127.0.0.1"      # ASGITransport peer
    assert doc["notes"] == []

    # Reflected in the admin portal listing (Super Admin sees full fields).
    listing = (await admin_client.get(f"{ADMIN}?page_size=100")).json()["data"]
    mine = [b for b in listing if b["id"] == str(doc["_id"])]
    assert mine and mine[0]["full_name"] == "Dana Cole"


async def test_public_validation_rejected(client):
    for body in (
        _payload(industry="aerospace"),        # bad enum
        _payload(work_email="not-an-email"),   # bad email
        _payload(full_name="   "),             # blank required
        {"full_name": "X", "company": "C", "industry": "other"},  # missing email
    ):
        res = await client.post(PUBLIC, json=body)
        assert res.status_code == 422, f"{body} -> {res.status_code}"


async def test_honeypot_is_silently_dropped(client):
    body = _payload(website="http://spam.example")
    res = await client.post(PUBLIC, json=body)
    assert res.status_code == 201
    assert res.json()["data"] == {"received": True}   # bot sees success…
    # …but nothing is stored.
    count = await get_db_manager().control[COLLECTION].count_documents(
        {"work_email": body["work_email"]})
    assert count == 0


# --- admin round-trip + audit ---------------------------------------------

async def test_admin_list_detail_patch_roundtrip(client, admin_client):
    body = _payload(message="Need drawings tracked.")
    await client.post(PUBLIC, json=body)
    bid = str(await _id_for(body["work_email"]))

    detail = (await admin_client.get(f"{ADMIN}/{bid}")).json()["data"]
    assert detail["work_email"] == body["work_email"]
    assert detail["status"] == "new"

    patch = await admin_client.patch(
        f"{ADMIN}/{bid}", json={"status": "contacted", "note": "Emailed to schedule."})
    assert patch.status_code == 200, patch.text
    updated = patch.json()["data"]
    assert updated["status"] == "contacted"
    assert len(updated["notes"]) == 1
    assert updated["notes"][0]["text"] == "Emailed to schedule."

    # status filter narrows the listing
    contacted = (await admin_client.get(f"{ADMIN}?status=contacted&page_size=100")).json()["data"]
    assert bid in [b["id"] for b in contacted]
    assert (await admin_client.get(f"{ADMIN}?status=new&page_size=100")).json()["data"] == []


async def test_patch_is_audited(client, admin_client):
    await client.post(PUBLIC, json=_payload(work_email="audit-me@acme.com"))
    bid = str(await _id_for("audit-me@acme.com"))
    await admin_client.patch(f"{ADMIN}/{bid}", json={"status": "scheduled"})

    control = get_db_manager().control
    rows = [d async for d in
            control.admin_audit_log.find({"target.id": bid}).sort("occurred_at", 1)]
    assert [r["action"] for r in rows] == ["discovery_booking.updated"]
    assert rows[0]["target"]["type"] == "discovery_booking"


async def test_detail_404_for_unknown_or_malformed_id(admin_client):
    missing = await admin_client.get(f"{ADMIN}/{'0' * 24}")   # valid ObjectId shape
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "NOT_FOUND"
    assert (await admin_client.get(f"{ADMIN}/not-an-id")).status_code == 404


# --- RBAC ladder -----------------------------------------------------------

async def test_view_masks_pii_and_blocks_detail_and_write(app, client, control_seeded):
    await client.post(PUBLIC, json=_payload(work_email="observed@acme.com"))
    bid = str(await _id_for("observed@acme.com"))

    observer = await _authed_admin(app, client, control_seeded, "Observer")  # leads VIEW
    async with observer:
        rows = (await observer.get(f"{ADMIN}?page_size=100")).json()["data"]
        mine = next(b for b in rows if b["id"] == bid)
        assert mine["company"] == "Acme Interiors" and mine["status"] == "new"
        assert "full_name" not in mine and "work_email" not in mine  # PII masked

        assert (await observer.get(f"{ADMIN}/{bid}")).status_code == 403       # needs READ
        assert (await observer.patch(f"{ADMIN}/{bid}",
                json={"status": "closed"})).status_code == 403                 # needs WRITE


async def test_auditor_can_read_but_not_write(app, client, control_seeded):
    await client.post(PUBLIC, json=_payload(work_email="readonly@acme.com"))
    bid = str(await _id_for("readonly@acme.com"))

    auditor = await _authed_admin(app, client, control_seeded, "Auditor")  # leads READ
    async with auditor:
        detail = await auditor.get(f"{ADMIN}/{bid}")
        assert detail.status_code == 200
        assert detail.json()["data"]["work_email"] == "readonly@acme.com"  # full at READ
        blocked = await auditor.patch(f"{ADMIN}/{bid}", json={"status": "closed"})
        assert blocked.status_code == 403
        assert blocked.json()["error"]["code"] == "PERMISSION_DENIED"


async def _id_for(email: str):
    doc = await get_db_manager().control[COLLECTION].find_one({"work_email": email})
    assert doc is not None, f"no booking for {email}"
    return doc["_id"]
