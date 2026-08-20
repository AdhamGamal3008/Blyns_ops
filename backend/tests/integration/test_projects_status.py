"""Managed project status (docs/PROJECT_STATUS_PLAN.md).

Active / On hold / Completed / Archived behind one guarded endpoint:
- archive is available from ANY status at ANY stage (rule 1),
- archived leaves the portfolio for its own tab (rule 2),
- archived is recalled to any state EXCEPT completed (rule 3),
- `completed` is machine-only — reachable solely by approving the last stage,
- a MANUAL hold is never cleared by the engine.
"""

from __future__ import annotations

import pytest

from app.core.db import get_db_manager
from app.core.security import hash_password
from app.modules.settings.seed import CLIENT_RESOURCES

from .test_projects import (
    BASE,
    _advance,
    _create_project,
    _gate_result,
    _machine_config,
    _passing_payload,
    _reject,
    _submit,
    _supply,
)


async def _status(client_client, pid: str, status: str, reason: str | None = None):
    return await client_client.post(
        f"{BASE}/{pid}/status", json={"status": status, "reason": reason}
    )


async def _project_doc(client_client, pid: str) -> dict:
    res = await client_client.get(f"{BASE}/{pid}")
    assert res.status_code == 200, res.text
    return res.json()["data"]


async def _complete_project(client_client) -> str:
    """Drive a project all nine stages to a machine-set `completed`."""
    stages, gates = await _machine_config(client_client)
    pid = (await _create_project(client_client, name="Handover Run"))["id"]
    for order in range(1, 10):
        await _advance(client_client, pid, order, stages, gates)
    doc = await _project_doc(client_client, pid)
    assert doc["status"] == "completed", doc["status"]
    return pid


# --- the transition matrix ---------------------------------------------------


async def test_new_project_starts_active(client_client):
    pid = (await _create_project(client_client))["id"]
    assert (await _project_doc(client_client, pid))["status"] == "active"


@pytest.mark.parametrize("target,expected", [
    ("on_hold", 200),    # manual hold
    ("archived", 200),   # rule 1: archive any time
    ("active", 200),     # same-status no-op
])
async def test_transitions_from_active(client_client, target, expected):
    pid = (await _create_project(client_client, name=f"From active {target}"))["id"]
    res = await _status(client_client, pid, target)
    assert res.status_code == expected, res.text
    assert res.json()["data"]["status"] == target


async def test_completed_is_never_manually_settable(client_client):
    """D1: `completed` is not in the manual vocabulary at all — the payload
    itself rejects it, so no transition rule can be bypassed."""
    pid = (await _create_project(client_client, name="No hand completion"))["id"]
    res = await _status(client_client, pid, "completed")
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "VALIDATION_ERROR"
    assert (await _project_doc(client_client, pid))["status"] == "active"


async def test_hold_then_resume_and_archive(client_client):
    pid = (await _create_project(client_client, name="Hold cycle"))["id"]

    res = await _status(client_client, pid, "on_hold", reason="waiting on client")
    assert res.status_code == 200
    doc = res.json()["data"]
    assert doc["status"] == "on_hold"
    assert doc["hold"]["source"] == "manual"
    assert doc["hold"]["reason"] == "waiting on client"

    res = await _status(client_client, pid, "active")
    assert res.status_code == 200
    assert res.json()["data"]["status"] == "active"
    assert res.json()["data"]["hold"] is None

    # archiving straight out of a hold is allowed too
    await _status(client_client, pid, "on_hold")
    res = await _status(client_client, pid, "archived")
    assert res.status_code == 200
    assert res.json()["data"]["hold"] is None


@pytest.mark.parametrize("target", ["active", "on_hold"])
async def test_archived_recalled_to_any_state_but_completed(client_client, target):
    """Rule 3: restore offers active and on_hold; completed is never reachable."""
    pid = (await _create_project(client_client, name=f"Recall {target}"))["id"]
    await _status(client_client, pid, "archived")

    res = await _status(client_client, pid, target, reason="resuming work")
    assert res.status_code == 200, res.text
    assert res.json()["data"]["status"] == target

    # and never to completed, even coming out of the archive
    await _status(client_client, pid, "archived")
    assert (await _status(client_client, pid, "completed")).status_code == 422


async def test_archive_is_available_mid_stage(client_client):
    """Rule 1: not only at completion — park a project in the middle of the
    machine and its stage progress is preserved on restore."""
    stages, gates = await _machine_config(client_client)
    pid = (await _create_project(client_client, name="Mid-stage park"))["id"]
    await _advance(client_client, pid, 1, stages, gates)
    before = await _project_doc(client_client, pid)
    assert before["current_stage_order"] > 1

    assert (await _status(client_client, pid, "archived")).status_code == 200
    await _status(client_client, pid, "active")

    after = await _project_doc(client_client, pid)
    assert after["current_stage_order"] == before["current_stage_order"]


# --- archived freezes the machine (§3.4) --------------------------------------


async def test_archived_project_refuses_mutations_but_allows_reads(client_client):
    stages, gates = await _machine_config(client_client)
    pid = (await _create_project(client_client, name="Frozen"))["id"]
    await _supply(client_client, pid, 1, "loi_or_po")
    await _status(client_client, pid, "archived")

    # reads stay open — you must be able to look at what you parked
    assert (await client_client.get(f"{BASE}/{pid}")).status_code == 200
    assert (await client_client.get(f"{BASE}/{pid}/timeline")).status_code == 200
    assert (await client_client.get(f"{BASE}/{pid}/board")).status_code == 200
    assert (await client_client.get(f"{BASE}/{pid}/stages/1")).status_code == 200
    assert (await client_client.get(f"{BASE}/{pid}/reports")).status_code == 200

    # every mutation is refused with the same typed error
    mutations = [
        await _submit(client_client, pid, 1),
        await _gate_result(client_client, pid, 1, "site_access_confirmed"),
        await client_client.patch(f"{BASE}/{pid}", json={"name": "Renamed"}),
        await client_client.post(f"{BASE}/{pid}/reports",
                                 json={"type": "issue", "title": "x"}),
        await client_client.post(f"{BASE}/{pid}/job-costs",
                                 json={"cost_type": "labor", "hours": 1,
                                       "unit_cost": 10, "stage_key": "x"}),
        await client_client.post(
            f"{BASE}/{pid}/stages/1/documents/loi_or_po/attach",
            json={"source_type": "url", "file_ref": "https://x/y.pdf"}),
    ]
    for res in mutations:
        assert res.status_code == 409, res.text
        assert res.json()["error"]["code"] == "PROJECT_ARCHIVED"

    # the name was not changed by the refused patch
    assert (await _project_doc(client_client, pid))["name"] == "Frozen"

    # restoring thaws it
    await _status(client_client, pid, "active")
    assert (await _submit(client_client, pid, 1)).status_code == 200


async def test_status_cannot_ride_on_the_generic_patch(client_client):
    """§3.1 — one door. PATCH ignores `status` entirely."""
    pid = (await _create_project(client_client, name="Patch guard"))["id"]
    res = await client_client.patch(
        f"{BASE}/{pid}", json={"name": "Renamed", "status": "completed"}
    )
    assert res.status_code == 200
    assert res.json()["data"]["name"] == "Renamed"
    assert res.json()["data"]["status"] == "active"  # untouched


# --- hold provenance — the sharp edge (§3.3) ----------------------------------


async def test_manual_hold_survives_report_resolution(client_client):
    """A hold a human placed is cleared only by an explicit resume. Without
    provenance, resolving any report would silently un-pause the project."""
    pid = (await _create_project(client_client, name="Manual hold"))["id"]
    res = await client_client.post(f"{BASE}/{pid}/reports", json={
        "type": "issue", "title": "Unrelated issue",
    })
    assert res.status_code == 201, res.text
    report_id = res.json()["data"]["id"]

    await _status(client_client, pid, "on_hold", reason="client paused the job")

    res = await client_client.patch(f"{BASE}/{pid}/reports/{report_id}",
                                    json={"status": "resolved"})
    assert res.status_code == 200, res.text

    doc = await _project_doc(client_client, pid)
    assert doc["status"] == "on_hold", "a manual hold must not auto-clear"
    assert doc["hold"]["source"] == "manual"

    # only an explicit resume lifts it
    await _status(client_client, pid, "active")
    assert (await _project_doc(client_client, pid))["status"] == "active"


async def _hold_at_site_readiness(client_client, name: str) -> str:
    """Drive to Stage 7 (Site Readiness) and get it rejected — the canonical
    engine hold (§4, mirrors test_projects.py)."""
    stages, gates = await _machine_config(client_client)
    pid = (await _create_project(client_client, name=name))["id"]
    for order in range(1, 7):
        await _advance(client_client, pid, order, stages, gates)
    for gate_key in ("concrete_rh_astm_f2170", "subfloor_flatness", "substrate_soundness"):
        res = await _gate_result(client_client, pid, 7, gate_key,
                                 **_passing_payload(gates[gate_key]))
        assert res.json()["data"]["result"]["passed"] is True, gate_key
    await _submit(client_client, pid, 7)
    res = await _reject(client_client, pid, 7, comment="Slab still wet in zone C")
    assert res.status_code == 200, res.text
    return pid


async def test_engine_hold_still_auto_clears(client_client):
    """The v1.0 behaviour must survive provenance: an engine hold is released
    when the recovery report is resolved."""
    pid = await _hold_at_site_readiness(client_client, "Engine hold")

    doc = await _project_doc(client_client, pid)
    assert doc["status"] == "on_hold"
    assert doc["hold"]["source"] == "engine"

    for report in (await client_client.get(f"{BASE}/{pid}/reports?status=open")
                   ).json()["data"]:
        await client_client.patch(f"{BASE}/{pid}/reports/{report['id']}",
                                  json={"status": "resolved"})

    doc = await _project_doc(client_client, pid)
    assert doc["status"] == "active", "an engine hold must auto-clear"
    assert doc["hold"] is None


async def test_manual_hold_placed_over_an_engine_hold_does_not_auto_clear(client_client):
    """The regression that matters: a human re-holds a project that the engine
    had parked, then the recovery report resolves. The human's hold wins."""
    pid = await _hold_at_site_readiness(client_client, "Human overrides engine")
    assert (await _project_doc(client_client, pid))["hold"]["source"] == "engine"

    # the PM decides the job stays parked regardless of the report
    res = await _status(client_client, pid, "on_hold", reason="client on holiday")
    assert res.status_code == 200, res.text
    assert res.json()["data"]["hold"]["source"] == "manual"

    for report in (await client_client.get(f"{BASE}/{pid}/reports?status=open")
                   ).json()["data"]:
        await client_client.patch(f"{BASE}/{pid}/reports/{report['id']}",
                                  json={"status": "resolved"})

    doc = await _project_doc(client_client, pid)
    assert doc["status"] == "on_hold"
    assert doc["hold"]["reason"] == "client on holiday"


# --- completion interplay (D2) ------------------------------------------------


async def test_completed_reopens_to_active_and_clears_the_stamp(client_client):
    """D2: a finished project can be re-opened in one step for rework."""
    pid = await _complete_project(client_client)
    assert (await _project_doc(client_client, pid))["completed_at"] is not None

    res = await _status(client_client, pid, "active", reason="snag found on site")
    assert res.status_code == 200, res.text
    doc = res.json()["data"]
    assert doc["status"] == "active"
    assert doc["completed_at"] is None, "nothing is both active and complete"

    # completed → on_hold is deliberately not offered: re-open first, then hold
    pid2 = await _complete_project(client_client)
    res = await _status(client_client, pid2, "on_hold")
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "INVALID_STATUS_TRANSITION"
    assert res.json()["error"]["details"]["allowed"] == ["active", "archived"]


async def test_completed_archived_then_restored_lands_active(client_client):
    pid = await _complete_project(client_client)
    await _status(client_client, pid, "archived")
    res = await _status(client_client, pid, "active")
    assert res.status_code == 200
    doc = res.json()["data"]
    assert doc["status"] == "active"
    assert doc["completed_at"] is None


# --- history, listing, activity ------------------------------------------------


async def test_status_history_records_every_transition(client_client):
    pid = (await _create_project(client_client, name="History"))["id"]
    await _status(client_client, pid, "on_hold", reason="paused")
    await _status(client_client, pid, "archived", reason="parked")
    await _status(client_client, pid, "active", reason="resumed")

    history = (await _project_doc(client_client, pid))["status_history"]
    assert [(h["from"], h["to"]) for h in history] == [
        ("active", "on_hold"), ("on_hold", "archived"), ("archived", "active"),
    ]
    assert history[0]["reason"] == "paused"
    assert all(h["by"] and h["at"] for h in history)


async def test_archived_projects_are_listed_separately(client_client):
    """Rule 2: the archived tab is `?status=archived`; the portfolio excludes it."""
    live = (await _create_project(client_client, name="Still live"))["id"]
    parked = (await _create_project(client_client, name="Parked away"))["id"]
    await _status(client_client, parked, "archived")

    res = await client_client.get(f"{BASE}?page_size=100")
    ids = {p["id"] for p in res.json()["data"]}
    assert live in ids
    assert parked not in ids, "archived must leave the portfolio"

    res = await client_client.get(f"{BASE}?status=archived&page_size=100")
    ids = {p["id"] for p in res.json()["data"]}
    assert parked in ids
    assert live not in ids


async def test_status_changes_are_logged_to_activity(client_client, onboarded_company):
    pid = (await _create_project(client_client, name="Audited"))["id"]
    await _status(client_client, pid, "archived", reason="end of season")
    await _status(client_client, pid, "on_hold")

    res = await client_client.get("/api/v1/activity?module=projects&page_size=50")
    actions = [e["action"] for e in res.json()["data"]]
    assert "project.archived" in actions
    assert "project.restored" in actions


async def test_archived_project_leaves_the_calendar(client_client):
    """§3.6 — a parked project stops pushing dates at people."""
    from datetime import UTC, datetime, timedelta

    due = (datetime.now(UTC) + timedelta(days=5)).isoformat()
    res = await client_client.post(BASE, json={
        "name": "Calendar project",
        "milestone_schedule": [{"key": "m1", "name": "Kickoff", "due_date": due}],
    })
    assert res.status_code == 201, res.text
    pid = res.json()["data"]["id"]

    frm = datetime.now(UTC).date().isoformat()
    to = (datetime.now(UTC) + timedelta(days=20)).date().isoformat()

    titles = {e["title"] for e in
              (await client_client.get(f"/api/v1/calendar?from={frm}&to={to}")
               ).json()["data"]}
    assert any("Kickoff" in t for t in titles)

    await _status(client_client, pid, "archived")
    titles = {e["title"] for e in
              (await client_client.get(f"/api/v1/calendar?from={frm}&to={to}")
               ).json()["data"]}
    assert not any("Kickoff" in t for t in titles)


# --- RBAC ----------------------------------------------------------------------


async def test_status_change_requires_projects_write(client, client_client, onboarded_company):
    """D3: `projects` WRITE governs it — a READ user cannot move a project."""
    from datetime import UTC, datetime

    pid = (await _create_project(client_client, name="RBAC target"))["id"]

    tenant_db = get_db_manager().tenant(onboarded_company["company"]["db_name"])
    now = datetime.now(UTC)
    role_id = (await tenant_db.roles.insert_one({
        "name": "projects-reader",
        "permissions": {r: 0 for r in CLIENT_RESOURCES} | {"dashboard": 2, "projects": 2},
        "created_at": now, "updated_at": now,
    })).inserted_id
    email = f"reader@{onboarded_company['slug']}.com"
    await tenant_db.users.insert_one({
        "email": email, "password_hash": hash_password("ReaderPass1!"),
        "name": "Reader", "role_id": role_id, "is_blocked": False,
        "failed_attempts": 0, "locked_until": None, "must_reset_password": False,
        "last_login_at": None, "refresh_jtis": [], "created_at": now, "updated_at": now,
    })
    res = await client.post("/api/v1/auth/login", json={
        "company": onboarded_company["slug"], "email": email,
        "password": "ReaderPass1!",
    })
    headers = {"Authorization": f"Bearer {res.json()['data']['access_token']}"}

    # can look…
    assert (await client.get(f"{BASE}/{pid}", headers=headers)).status_code == 200
    # …but not move it
    res = await client.post(f"{BASE}/{pid}/status",
                            json={"status": "archived"}, headers=headers)
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "PERMISSION_DENIED"
