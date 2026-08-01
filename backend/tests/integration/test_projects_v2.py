"""Project Management v2.0 state machine (docs/PROJECT_MANAGEMENT_V2_MIGRATION_PLAN.md
§4/§7): the nine-stage walk to handover, the approver-less survey stage that
auto-advances, and the severe-G1 deviation that returns the project to design.

Reuses the config-driven harness in test_projects.py — the machine is driven from
/config/stages + /config/gates, so it adapts to the 9-stage seed automatically."""

from __future__ import annotations

from tests.integration.test_projects import (
    BASE,
    _advance,
    _approve,
    _create_project,
    _employee,
    _gate_result,
    _iso,
    _machine_config,
    _passing_payload,
    _stage,
    _submit,
    _supply,
)


async def _deputy(client, client_client, slug, tag="deputy"):
    """A Member employee (holds projects WRITE but no approver position) — the
    natural delegate. Returns (auth headers, user_id)."""
    headers = await _employee(client, client_client, slug, "Member", tag)
    emps = (await client_client.get("/api/v1/settings/employees")).json()["data"]
    uid = next(e["id"] for e in emps if e["email"] == f"{tag}@{slug}.com")
    return headers, uid


async def _waive(client_client, pid, order, gate_key, reason="Director waiver on file"):
    return await client_client.post(
        f"{BASE}/{pid}/stages/{order}/gates/{gate_key}/waive",
        json={"reason": reason},
    )


async def _auto_advance(client_client, pid, order, gates):
    """Drive the approver-less survey stage: record its (non-blocking) findings,
    then submit — it advances with no approve step."""
    stages = (await client_client.get(f"{BASE}/config/stages")).json()["data"]
    definition = next(s for s in stages if s["order"] == order)
    for gate_key in definition.get("quality_gates") or []:
        await _gate_result(client_client, pid, order, gate_key, **_passing_payload(gates[gate_key]))
    res = await _submit(client_client, pid, order)
    assert res.status_code == 200, res.text
    body = res.json()["data"]
    assert body["auto_advanced"] is True, body
    return body


async def test_walk_the_nine_stage_machine_to_completion(client_client):
    project = await _create_project(client_client)
    pid = project["id"]
    stages, gates = await _machine_config(client_client)
    assert len(stages) == 9

    await _advance(client_client, pid, 1, stages, gates)     # Stage 1 · project_director
    await _auto_advance(client_client, pid, 2, gates)         # Stage 2 · auto-advances
    result: dict = {}
    for order in range(3, 10):                                # Stages 3–9, one approval each
        result = await _advance(client_client, pid, order, stages, gates)

    assert result["project_status"] == "completed"
    assert result["handover"] is not None
    # incl. the G1–G5 gate records (technical defence file)
    assert len(result["handover"]["documents"]) == 5

    detail = (await client_client.get(f"{BASE}/{pid}")).json()["data"]
    assert detail["status"] == "completed"


async def test_survey_stage_has_no_approver(client_client):
    project = await _create_project(client_client)
    pid = project["id"]
    stages, gates = await _machine_config(client_client)
    await _advance(client_client, pid, 1, stages, gates)  # into Stage 2

    # approving Stage 2 is refused — it has no approver position
    res = await client_client.post(f"{BASE}/{pid}/stages/2/approve", json={"comment": None})
    assert res.status_code == 403, res.text

    # …but submitting it advances the project to Stage 3
    await _auto_advance(client_client, pid, 2, gates)
    detail = (await client_client.get(f"{BASE}/{pid}")).json()["data"]
    assert detail["current_stage_order"] == 3


async def test_severe_deviation_returns_the_project_to_design(client_client):
    project = await _create_project(client_client)
    pid = project["id"]
    stages, gates = await _machine_config(client_client)
    await _advance(client_client, pid, 1, stages, gates)
    await _auto_advance(client_client, pid, 2, gates)
    await _advance(client_client, pid, 3, stages, gates)  # design approved → Stage 4

    # Stage 4 (G1): a severe deviation (> 6mm) auto-returns the project to design
    res = await _gate_result(
        client_client, pid, 4, "deviation_within_tolerance",
        readings=[{"location": "worst", "value": 8.0}],
    )
    assert res.status_code == 200, res.text
    body = res.json()["data"]
    assert body["result"]["severe"] is True
    assert body["rolled_back_to"] == "design_package"

    detail = (await client_client.get(f"{BASE}/{pid}")).json()["data"]
    assert detail["current_stage_order"] == 3
    assert detail["current_stage_key"] == "design_package"
    assert detail["status"] == "active"  # not left on hold
    assert (await _stage(client_client, pid, 3))["instance"]["status"] == "in_progress"


# --- gate waiver (SOP §3 — director-only) ------------------------------------

async def test_director_waiver_clears_a_hard_gate(client_client):
    """A director may waive a hard gate in writing: the waiver is a passing gate
    result, so the stage validates and advances with no measured reading."""
    project = await _create_project(client_client)
    pid = project["id"]
    stages, gates = await _machine_config(client_client)
    for order in (1, 2, 3):
        await _advance(client_client, pid, order, stages, gates)  # into Stage 4

    # a gate that does not attach to this stage, and an empty reason, are refused
    assert (await _waive(client_client, pid, 4, "timber_moisture_content")).status_code == 422
    assert (await _waive(client_client, pid, 4, "deviation_within_tolerance",
                         reason="")).status_code == 422

    # the Owner holds the project_director position (client_roles=["owner"]) →
    # the waiver is recorded as a passing, provenanced gate result
    res = await _waive(client_client, pid, 4, "deviation_within_tolerance",
                       reason="As-built within design intent per RFI-14")
    assert res.status_code == 200, res.text
    result = res.json()["data"]["result"]
    assert result["waived"] is True
    assert result["passed"] is True
    assert result["reason"] == "As-built within design intent per RFI-14"

    # Stage 4's entry documents are a separate gate from G1 — supply them, then
    # with G1 waived (no reading captured) the stage validates and approves
    await _supply(client_client, pid, 4, "shop_drawings_present", "raw_site_data_present")
    submit = await _submit(client_client, pid, 4)
    assert submit.json()["data"]["validation"]["passed"] is True
    res = await _approve(client_client, pid, 4)
    assert res.status_code == 200, res.text
    assert res.json()["data"]["next_stage"]["order"] == 5


async def test_only_the_director_may_waive_a_gate(client, client_client, onboarded_company):
    """§3: a hard gate is waivable ONLY by the project_director — plain projects
    WRITE is not enough."""
    slug = onboarded_company["slug"]
    project = await _create_project(client_client)
    pid = project["id"]
    stages, gates = await _machine_config(client_client)
    for order in (1, 2, 3):
        await _advance(client_client, pid, order, stages, gates)  # into Stage 4

    # a Manager holds projects WRITE but not the project_director position
    manager = await _employee(client, client_client, slug, "Manager", "waive-mgr")
    res = await client.post(
        f"{BASE}/{pid}/stages/4/gates/deviation_within_tolerance/waive",
        json={"reason": "please"}, headers=manager,
    )
    assert res.status_code == 403, res.text
    assert "project_director" in res.json()["error"]["message"]


async def test_waiver_surfaces_in_the_handover_defence_file(client_client):
    """A waived gate is never silent: it is recorded in the Stage-9 technical
    defence file (SOP §9), alongside the measured readings."""
    project = await _create_project(client_client)
    pid = project["id"]
    stages, gates = await _machine_config(client_client)
    for order in (1, 2, 3, 4, 5, 6):
        await _advance(client_client, pid, order, stages, gates)  # into Stage 7

    # Stage 7 (site_readiness): a non-blocking gate has nothing to waive
    assert (await _waive(client_client, pid, 7, "substrate_soundness")).status_code == 422

    # waive G3 (concrete RH), measure G4 (subfloor) normally → the stage passes
    res = await _waive(client_client, pid, 7, "concrete_rh_astm_f2170",
                       reason="Adhesive maker signed off 80% RH in writing")
    assert res.status_code == 200, res.text
    await _gate_result(client_client, pid, 7, "subfloor_flatness",
                       **_passing_payload(gates["subfloor_flatness"]))
    await _submit(client_client, pid, 7)
    assert (await _approve(client_client, pid, 7)).status_code == 200

    for order in (8, 9):
        result = await _advance(client_client, pid, order, stages, gates)

    assert result["project_status"] == "completed"
    handover = result["handover"]
    waived = {w["gate_key"] for w in handover["gate_waivers"]}
    assert "concrete_rh_astm_f2170" in waived
    # and it rides in the defence-file document, not just the top-level summary
    defence = next(d for d in handover["documents"] if "Defence File" in d["title"])
    assert any(w["gate_key"] == "concrete_rh_astm_f2170" for w in defence["gate_waivers"])


# --- Stage 6 factory-release checklist (§5-C) --------------------------------

async def test_stage6_release_blocked_until_checklist_complete(client_client):
    """The four v1.0 factory approvals became one release decision: all four
    checklist sections must be complete before Stage 6 can be released."""
    project = await _create_project(client_client)
    pid = project["id"]
    stages, gates = await _machine_config(client_client)
    for order in (1, 2, 3, 4, 5):
        await _advance(client_client, pid, order, stages, gates)  # into Stage 6

    sections = ["production", "quality_control", "packing_protection", "delivery_planning"]

    # nothing marked → the checklist blocks the release at validation
    res = await _submit(client_client, pid, 6)
    body = res.json()["data"]
    assert body["validation"]["passed"] is False
    failed = {c["key"] for c in body["validation"]["checks"] if not c["passed"]}
    assert "release_checklist_complete" in failed

    # an unknown section is refused
    bad = await client_client.post(f"{BASE}/{pid}/stages/6/checklist/not_a_section", json={})
    assert bad.status_code == 422

    # completing three of four is still short → still blocked
    for section in sections[:3]:
        r = await client_client.post(
            f"{BASE}/{pid}/stages/6/checklist/{section}", json={"complete": True})
        assert r.status_code == 200, r.text
    res = await _submit(client_client, pid, 6)
    failed = {c["key"] for c in res.json()["data"]["validation"]["checks"] if not c["passed"]}
    assert "release_checklist_complete" in failed

    # the fourth section completes it → release validates and approves
    r = await client_client.post(
        f"{BASE}/{pid}/stages/6/checklist/{sections[3]}", json={"complete": True})
    assert r.status_code == 200
    res = await _submit(client_client, pid, 6)
    assert res.json()["data"]["validation"]["passed"] is True
    res = await _approve(client_client, pid, 6)
    assert res.status_code == 200, res.text
    assert res.json()["data"]["next_stage"]["order"] == 7


# --- Stage 9 snag closure (SOP §9) -------------------------------------------

async def _walk_to_stage9(client_client, pid, stages, gates):
    for order in range(1, 9):  # approve Stages 1–8 → the project enters Stage 9
        await _advance(client_client, pid, order, stages, gates)


async def test_stage9_open_snag_blocks_handover_until_resolved(client_client):
    project = await _create_project(client_client)
    pid = project["id"]
    stages, gates = await _machine_config(client_client)
    await _walk_to_stage9(client_client, pid, stages, gates)

    # an open snag (a `na` report) blocks the handover
    snag = await client_client.post(f"{BASE}/{pid}/reports", json={
        "type": "na", "title": "Chip on panel B3"})
    assert snag.status_code == 201, snag.text
    rid = snag.json()["data"]["id"]

    res = await _submit(client_client, pid, 9)
    failed = {c["key"] for c in res.json()["data"]["validation"]["checks"] if not c["passed"]}
    assert "snags_closed" in failed

    # resolving the snag clears the handover
    r = await client_client.patch(f"{BASE}/{pid}/reports/{rid}", json={"status": "resolved"})
    assert r.status_code == 200
    res = await _submit(client_client, pid, 9)
    assert res.json()["data"]["validation"]["passed"] is True
    res = await _approve(client_client, pid, 9)
    assert res.status_code == 200, res.text
    assert res.json()["data"]["project_status"] == "completed"


async def test_stage9_written_client_acceptance_overrides_open_snag(client_client):
    project = await _create_project(client_client)
    pid = project["id"]
    stages, gates = await _machine_config(client_client)
    await _walk_to_stage9(client_client, pid, stages, gates)

    snag = await client_client.post(f"{BASE}/{pid}/reports", json={
        "type": "na", "title": "Reveal 4mm at door head"})
    rid = snag.json()["data"]["id"]

    # the snag is still open → handover blocked
    res = await _submit(client_client, pid, 9)
    failed = {c["key"] for c in res.json()["data"]["validation"]["checks"] if not c["passed"]}
    assert "snags_closed" in failed

    # a written client acceptance lets the handover proceed with the snag open
    acc = await client_client.post(f"{BASE}/{pid}/client-acceptance", json={
        "note": "Client accepts the 4mm reveal at the door head in writing."})
    assert acc.status_code == 200, acc.text

    res = await _submit(client_client, pid, 9)
    assert res.json()["data"]["validation"]["passed"] is True
    result = (await _approve(client_client, pid, 9)).json()["data"]
    assert result["project_status"] == "completed"

    # the snag remains open on record — accepted in writing, not silently closed
    reports = (await client_client.get(
        f"{BASE}/{pid}/reports", params={"type": "na"})).json()["data"]
    assert any(r["id"] == rid and r["status"] == "open" for r in reports)


# --- approver delegation (SOP §2) --------------------------------------------

async def _reach_stage3_pending(client_client, pid, stages, gates):
    """Drive a project to Stage 3 (Design Package) and submit it for approval."""
    for order in (1, 2):  # Stage 1, then the auto-advancing Stage 2
        await _advance(client_client, pid, order, stages, gates)
    await _submit(client_client, pid, 3)  # → pending_approval, approver design_manager


async def test_delegated_deputy_may_approve_a_stage(client, client_client, onboarded_company):
    """SOP §2: a named deputy holding an active written delegation of a position
    may approve for it, though they do not natively hold it."""
    slug = onboarded_company["slug"]
    deputy_headers, deputy_id = await _deputy(client, client_client, slug)

    # the Owner (holds every position) delegates design_manager to the deputy
    res = await client_client.post(f"{BASE}/config/delegations", json={
        "approver_role": "design_manager", "delegate_user_id": deputy_id,
        "reason": "Design manager on leave this week", "ends_at": _iso(7)})
    assert res.status_code == 201, res.text
    assert res.json()["data"]["revoked"] is False

    # the delegation is listed
    listed = (await client_client.get(f"{BASE}/config/delegations")).json()["data"]
    assert any(d["delegate_user_id"] == deputy_id for d in listed)

    project = await _create_project(client_client)
    pid = project["id"]
    stages, gates = await _machine_config(client_client)
    await _reach_stage3_pending(client_client, pid, stages, gates)

    # the deputy — a Member with no native design_manager position — approves it
    res = await client.post(f"{BASE}/{pid}/stages/3/approve",
                            json={"comment": "reviewed"}, headers=deputy_headers)
    assert res.status_code == 200, res.text
    assert res.json()["data"]["next_stage"]["order"] == 4


async def test_delegation_guardrails(client, client_client, onboarded_company):
    slug = onboarded_company["slug"]
    deputy_headers, deputy_id = await _deputy(client, client_client, slug, "dep2")

    # a Member holding no position (and not the director) cannot delegate
    res = await client.post(f"{BASE}/config/delegations", json={
        "approver_role": "design_manager", "delegate_user_id": deputy_id,
        "reason": "nope", "ends_at": _iso(3)}, headers=deputy_headers)
    assert res.status_code == 403, res.text

    # an unknown position is a 404
    res = await client_client.post(f"{BASE}/config/delegations", json={
        "approver_role": "nobody", "delegate_user_id": deputy_id,
        "reason": "x", "ends_at": _iso(3)})
    assert res.status_code == 404

    # no self-delegation
    owner_id = (await client_client.get("/api/v1/auth/me")).json()["data"]["id"]
    res = await client_client.post(f"{BASE}/config/delegations", json={
        "approver_role": "design_manager", "delegate_user_id": owner_id,
        "reason": "x", "ends_at": _iso(3)})
    assert res.status_code == 422


async def test_revoked_delegation_no_longer_grants_approval(
    client, client_client, onboarded_company
):
    slug = onboarded_company["slug"]
    deputy_headers, deputy_id = await _deputy(client, client_client, slug, "dep3")

    res = await client_client.post(f"{BASE}/config/delegations", json={
        "approver_role": "design_manager", "delegate_user_id": deputy_id,
        "reason": "cover", "ends_at": _iso(7)})
    did = res.json()["data"]["id"]

    r = await client_client.delete(f"{BASE}/config/delegations/{did}")
    assert r.status_code == 200, r.text
    assert r.json()["data"]["revoked"] is True

    project = await _create_project(client_client)
    pid = project["id"]
    stages, gates = await _machine_config(client_client)
    await _reach_stage3_pending(client_client, pid, stages, gates)

    # the revoked delegation grants nothing — the deputy is refused
    res = await client.post(f"{BASE}/{pid}/stages/3/approve", json={},
                            headers=deputy_headers)
    assert res.status_code == 403, res.text


async def test_elapsed_delegation_window_grants_nothing(
    client, client_client, onboarded_company
):
    """A delegation whose window has already closed does not grant approval."""
    slug = onboarded_company["slug"]
    deputy_headers, deputy_id = await _deputy(client, client_client, slug, "dep4")

    # a historical window: it starts and ends in the past
    res = await client_client.post(f"{BASE}/config/delegations", json={
        "approver_role": "design_manager", "delegate_user_id": deputy_id,
        "reason": "last week", "starts_at": _iso(-7), "ends_at": _iso(-1)})
    assert res.status_code == 201, res.text

    project = await _create_project(client_client)
    pid = project["id"]
    stages, gates = await _machine_config(client_client)
    await _reach_stage3_pending(client_client, pid, stages, gates)

    res = await client.post(f"{BASE}/{pid}/stages/3/approve", json={},
                            headers=deputy_headers)
    assert res.status_code == 403, res.text
