"""Settings module acceptance criteria (docs/modules/SETTINGS.md §4):
seat-limit block, live role re-evaluation, calendar-event visibility on the
dashboard calendar, client-side employee security actions."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.core.db import get_db_manager


async def _role_id(client_client, name: str) -> str:
    res = await client_client.get("/api/v1/settings/roles")
    return next(r["id"] for r in res.json()["data"] if r["name"] == name)


async def test_company_profile_get_and_patch(client_client):
    res = await client_client.get("/api/v1/settings/company")
    assert res.status_code == 200
    assert res.json()["data"]["currency"] == "USD"

    res = await client_client.patch("/api/v1/settings/company", json={
        "timezone": "Africa/Cairo", "currency": "EGP",
        "fiscal_year_start": "07-01",
    })
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["timezone"] == "Africa/Cairo"
    assert data["currency"] == "EGP"


async def test_employee_create_blocked_at_seat_limit(client_client, onboarded_company):
    """Acceptance #1: creating an employee is blocked once seat limit hit.
    The fixture company has seat_limit=10, owner uses 1."""
    member_id = await _role_id(client_client, "Member")
    created = 0
    last = None
    for i in range(12):  # more than the 9 remaining seats
        last = await client_client.post("/api/v1/settings/employees", json={
            "name": f"E{i}", "email": f"e{i}@{onboarded_company['slug']}.com",
            "role_id": member_id,
        })
        if last.status_code == 201:
            created += 1
            assert last.json()["data"]["temp_password"]
        else:
            break
    assert created == 9  # 10 seats − owner
    assert last.status_code == 409
    assert last.json()["error"]["code"] == "SEAT_LIMIT_REACHED"

    # registry reflects the claims exactly (control-plane enforcement)
    control = get_db_manager().control
    company = await control.companies.find_one(
        {"_id": onboarded_company["company"]["_id"]}
    )
    assert company["seats_used"] == 10


async def test_role_edit_takes_effect_immediately(client, client_client, onboarded_company):
    """Acceptance #2: editing a client role immediately changes holder access."""
    # role with settings NONE (dashboard READ so login/me works)
    res = await client_client.post("/api/v1/settings/roles", json={
        "name": "temp-limited", "permissions": {"dashboard": 2},
    })
    assert res.status_code == 201
    role_id = res.json()["data"]["id"]

    res = await client_client.post("/api/v1/settings/employees", json={
        "name": "Limited", "email": f"limited@{onboarded_company['slug']}.com",
        "role_id": role_id,
    })
    temp_pw = res.json()["data"]["temp_password"]

    # login (change temp password first — forced reset)
    login = {"company": onboarded_company["slug"],
             "email": f"limited@{onboarded_company['slug']}.com"}
    first = await client.post("/api/v1/auth/login",
                              json={**login, "password": temp_pw})
    headers = {"Authorization": f"Bearer {first.json()['data']['access_token']}"}
    await client.post("/api/v1/auth/change-password", headers=headers, json={
        "current_password": temp_pw, "new_password": "LimitedPass1!",
    })
    res = await client.post("/api/v1/auth/login",
                            json={**login, "password": "LimitedPass1!"})
    headers = {"Authorization": f"Bearer {res.json()['data']['access_token']}"}

    # settings denied at NONE
    assert (await client.get("/api/v1/settings/company", headers=headers)).status_code == 403

    # owner grants settings READ — same token, next request passes
    res = await client_client.patch(f"/api/v1/settings/roles/{role_id}", json={
        "permissions": {"dashboard": 2, "settings": 2},
    })
    assert res.status_code == 200
    assert (await client.get("/api/v1/settings/company", headers=headers)).status_code == 200


async def test_role_guards(client_client):
    # unknown resource rejected
    res = await client_client.post("/api/v1/settings/roles", json={
        "name": "bad", "permissions": {"warp": 3},
    })
    assert res.status_code == 422

    # role in use cannot be deleted (Owner holds it)
    owner_role_id = await _role_id(client_client, "Owner")
    res = await client_client.delete(f"/api/v1/settings/roles/{owner_role_id}")
    assert res.status_code == 409

    # unused role deletes fine
    res = await client_client.post("/api/v1/settings/roles", json={
        "name": "disposable", "permissions": {},
    })
    role_id = res.json()["data"]["id"]
    assert (await client_client.delete(f"/api/v1/settings/roles/{role_id}")).status_code == 200


async def test_cannot_delete_or_demote_last_owner_equivalent(client_client):
    """Owner is the only settings-WRITE role in use: demoting it via role edit
    or blocking its last holder is rejected."""
    owner_role_id = await _role_id(client_client, "Owner")
    res = await client_client.patch(f"/api/v1/settings/roles/{owner_role_id}", json={
        "permissions": {"dashboard": 2},  # drops settings WRITE
    })
    assert res.status_code == 409

    me = await client_client.get("/api/v1/auth/me")
    my_id = me.json()["data"]["id"]
    res = await client_client.patch(
        f"/api/v1/settings/employees/{my_id}/block", json={"blocked": True}
    )
    assert res.status_code == 409  # last settings manager cannot block self


async def test_employee_block_reset_unlock_flow(client, client_client, onboarded_company):
    member_id = await _role_id(client_client, "Member")
    res = await client_client.post("/api/v1/settings/employees", json={
        "name": "Sec Target", "email": f"sec@{onboarded_company['slug']}.com",
        "role_id": member_id,
    })
    uid = res.json()["data"]["id"]
    temp_pw = res.json()["data"]["temp_password"]
    login = {"company": onboarded_company["slug"],
             "email": f"sec@{onboarded_company['slug']}.com"}

    # block → login rejected; unblock → temp password works again
    await client_client.patch(f"/api/v1/settings/employees/{uid}/block",
                              json={"blocked": True})
    res = await client.post("/api/v1/auth/login", json={**login, "password": temp_pw})
    assert res.status_code == 403 and res.json()["error"]["code"] == "USER_BLOCKED"
    await client_client.patch(f"/api/v1/settings/employees/{uid}/block",
                              json={"blocked": False})
    assert (await client.post("/api/v1/auth/login",
                              json={**login, "password": temp_pw})).status_code == 200

    # client-side reset-password forces a new temp password
    res = await client_client.post(f"/api/v1/settings/employees/{uid}/reset-password")
    new_temp = res.json()["data"]["temp_password"]
    assert (await client.post("/api/v1/auth/login",
                              json={**login, "password": temp_pw})).status_code == 401
    res = await client.post("/api/v1/auth/login", json={**login, "password": new_temp})
    assert res.status_code == 200
    assert res.json()["data"]["password_reset_required"] is True

    # lockout (threshold 3) → client-side unlock restores
    for _ in range(3):
        await client.post("/api/v1/auth/login", json={**login, "password": "bad"})
    res = await client.post("/api/v1/auth/login", json={**login, "password": new_temp})
    assert res.status_code == 423
    await client_client.post(f"/api/v1/settings/employees/{uid}/unlock")
    assert (await client.post("/api/v1/auth/login",
                              json={**login, "password": new_temp})).status_code == 200


async def test_calendar_events_visibility_on_dashboard(client, client_client, onboarded_company):
    """Acceptance #3: company events appear in the Dashboard calendar
    respecting visibility."""
    start = (datetime.now(UTC) + timedelta(days=2)).isoformat()

    company_ev = await client_client.post("/api/v1/settings/calendar-events", json={
        "title": "Company holiday", "start": start, "visibility": "company",
    })
    assert company_ev.status_code == 201
    owner_ev = await client_client.post("/api/v1/settings/calendar-events", json={
        "title": "Owner private", "start": start, "visibility": "owner",
    })
    assert owner_ev.status_code == 201

    frm = datetime.now(UTC).date().isoformat()
    to = (datetime.now(UTC) + timedelta(days=10)).date().isoformat()

    # Owner (creator) sees both
    res = await client_client.get(f"/api/v1/calendar?from={frm}&to={to}")
    titles = {e["title"] for e in res.json()["data"]}
    assert {"Company holiday", "Owner private"} <= titles

    # another settings-READ user sees the company event but NOT the private one
    manager_id = await _role_id(client_client, "Manager")
    res = await client_client.post("/api/v1/settings/employees", json={
        "name": "Cal Viewer", "email": f"cal@{onboarded_company['slug']}.com",
        "role_id": manager_id,
    })
    temp_pw = res.json()["data"]["temp_password"]
    res = await client.post("/api/v1/auth/login", json={
        "company": onboarded_company["slug"],
        "email": f"cal@{onboarded_company['slug']}.com", "password": temp_pw,
    })
    headers = {"Authorization": f"Bearer {res.json()['data']['access_token']}"}
    res = await client.get(f"/api/v1/calendar?from={frm}&to={to}", headers=headers)
    titles = {e["title"] for e in res.json()["data"]}
    assert "Company holiday" in titles
    assert "Owner private" not in titles

    # deleting removes it from the calendar (soft delete)
    event_id = company_ev.json()["data"]["id"]
    await client_client.delete(f"/api/v1/settings/calendar-events/{event_id}")
    res = await client_client.get(f"/api/v1/calendar?from={frm}&to={to}")
    assert "Company holiday" not in {e["title"] for e in res.json()["data"]}


async def test_security_modules_and_approver_map(client_client):
    res = await client_client.get("/api/v1/settings/security")
    data = res.json()["data"]
    assert data["failed_login_threshold"] == 3  # fixture company policy
    assert data["editable"] is False

    res = await client_client.get("/api/v1/settings/modules")
    mods = {m["module"]: m["enabled"] for m in res.json()["data"]}
    assert mods["projects"] is True and len(mods) == 6

    # approver map seeded by the projects seed; client_contact role exists
    res = await client_client.get("/api/v1/settings/approver-roles")
    entries = {e["approver_role"]: e for e in res.json()["data"]}
    assert len(entries) == 16
    assert entries["client"]["client_roles"] == ["client_contact"]
    roles = await client_client.get("/api/v1/settings/roles")
    assert "client_contact" in {r["name"] for r in roles.json()["data"]}

    # PATCH one mapping; unknown role rejected
    res = await client_client.patch("/api/v1/settings/approver-roles/qc_manager",
                                    json={"client_roles": ["Manager"]})
    assert res.status_code == 200
    assert res.json()["data"]["client_roles"] == ["Manager"]
    res = await client_client.patch("/api/v1/settings/approver-roles/qc_manager",
                                    json={"client_roles": ["ghost-role"]})
    assert res.status_code == 422


async def test_settings_rbac_gate(client, client_client, onboarded_company):
    """settings NONE → every settings route denied; writes need WRITE."""
    member_id = await _role_id(client_client, "Member")  # Member: settings NONE
    res = await client_client.post("/api/v1/settings/employees", json={
        "name": "No Settings", "email": f"nos@{onboarded_company['slug']}.com",
        "role_id": member_id,
    })
    temp_pw = res.json()["data"]["temp_password"]
    res = await client.post("/api/v1/auth/login", json={
        "company": onboarded_company["slug"],
        "email": f"nos@{onboarded_company['slug']}.com", "password": temp_pw,
    })
    headers = {"Authorization": f"Bearer {res.json()['data']['access_token']}"}
    assert (await client.get("/api/v1/settings/company", headers=headers)).status_code == 403
    assert (await client.get("/api/v1/settings/roles", headers=headers)).status_code == 403
