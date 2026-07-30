"""Project Management acceptance criteria (docs/PROJECT_MANAGEMENT_V2_MIGRATION_PLAN
§8, docs/modules/PROJECT_WORKFLOW_V2_SOP.md): the v2.0 nine-stage stage-gate
machine — gates, engines, approvals, recovery loops, physical thresholds, and the
CRM/Inventory/Finance integrations.

The machine is driven from /config/stages + /config/gates, so the helpers here
adapt to the seed automatically; test_projects_v2.py reuses them for the
auto-advance and severe-rollback behaviours specific to v2.0."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

BASE = "/api/v1/projects"

# Stage 1 · Project Initiation — the three required entry documents (v2.0).
STAGE1_DOCS = ("loi_or_po", "scope_boq_approved", "site_access_confirmed")


def _iso(days: int) -> str:
    return (datetime.now(UTC) + timedelta(days=days)).isoformat()


# --- helpers -----------------------------------------------------------------

async def _create_project(client_client, name="Tower A Lobby Cladding", **extra) -> dict:
    res = await client_client.post(BASE, json={"name": name, **extra})
    assert res.status_code == 201, res.text
    return res.json()["data"]


async def _stage(client_client, pid: str, order: int) -> dict:
    res = await client_client.get(f"{BASE}/{pid}/stages/{order}")
    assert res.status_code == 200, res.text
    return res.json()["data"]


async def _supply(client_client, pid: str, order: int, *gate_keys: str) -> dict:
    """Satisfy document gates by attaching a URL reference — a document gate
    cannot be marked supplied without evidence (§4)."""
    last: dict = {}
    for key in gate_keys:
        res = await client_client.post(
            f"{BASE}/{pid}/stages/{order}/documents/{key}/attach",
            json={"source_type": "url",
                  "file_ref": f"https://docs.example.com/{key}.pdf"},
        )
        assert res.status_code == 201, res.text
        last = res.json()["data"]["instance"]
    return last


async def _submit(client_client, pid: str, order: int):
    return await client_client.post(f"{BASE}/{pid}/stages/{order}/submit", json={})


async def _approve(client_client, pid: str, order: int, comment=None):
    return await client_client.post(
        f"{BASE}/{pid}/stages/{order}/approve", json={"comment": comment}
    )


async def _reject(client_client, pid: str, order: int, comment: str, **extra):
    return await client_client.post(
        f"{BASE}/{pid}/stages/{order}/reject", json={"comment": comment, **extra}
    )


async def _gate_result(client_client, pid, order, gate_key, readings=None, checklist=None):
    return await client_client.post(
        f"{BASE}/{pid}/stages/{order}/gates/{gate_key}/result",
        json={"readings": readings or [], "checklist_results": checklist or []},
    )


def _passing_payload(rule: dict) -> dict:
    """Build a payload that satisfies a seeded gate rule — same threshold
    shapes engines.evaluate_measurement understands."""
    if rule.get("type") == "inspection":
        return {"checklist": [
            {"item": item, "passed": True} for item in rule.get("checklist", [])
        ]}
    threshold = rule.get("threshold") or {}
    if threshold.get("site_defined"):
        return {"readings": [{"location": "site", "value": 50}]}
    if "min" in threshold or "max" in threshold:
        value = (float(threshold.get("min", 0)) + float(threshold.get("max", 0))) / 2
        return {"readings": [{"location": "mid", "value": value}]}
    for field in ("max_deviation_mm", "max_rh_pct", "max_deviation_in"):
        if field in threshold:
            return {"readings": [{"location": "worst", "value": float(threshold[field]) / 2}]}
    if "target_mm" in threshold:
        return {"readings": [{"location": "joint", "value": float(threshold["target_mm"])}]}
    return {"readings": [{"location": "any", "value": 1}]}


async def _machine_config(client_client) -> tuple[list[dict], dict[str, dict]]:
    stages = (await client_client.get(f"{BASE}/config/stages")).json()["data"]
    gates = {
        g["key"]: g
        for g in (await client_client.get(f"{BASE}/config/gates")).json()["data"]
    }
    return stages, gates


async def _advance(client_client, pid: str, order: int, stages=None, gates=None):
    """Drive one stage start→approved: supply documents, log passing gate
    results, submit, then approve (as the Owner, whom every seeded position maps
    to). An approver-less auto-advance stage (v2.0 Stage 2) advances on submit
    with no approval step, so this returns the submit body for it."""
    if stages is None or gates is None:
        stages, gates = await _machine_config(client_client)
    definition = next(s for s in stages if s["order"] == order)

    for gate in definition.get("entry_gates") or []:
        if gate["type"] == "document":
            await _supply(client_client, pid, order, gate["key"])

    for gate_key in definition.get("quality_gates") or []:
        res = await _gate_result(
            client_client, pid, order, gate_key, **_passing_payload(gates[gate_key])
        )
        assert res.status_code == 200, res.text
        assert res.json()["data"]["result"]["passed"] is True, gate_key

    # v2.0 Stage 6: all four release-checklist sections must be complete
    for section in definition.get("release_checklist") or []:
        res = await client_client.post(
            f"{BASE}/{pid}/stages/{order}/checklist/{section}", json={"complete": True}
        )
        assert res.status_code == 200, res.text

    res = await _submit(client_client, pid, order)
    assert res.status_code == 200, res.text
    body = res.json()["data"]
    assert body["validation"]["passed"] is True, res.text
    if body.get("auto_advanced"):
        return body

    res = await _approve(client_client, pid, order)
    assert res.status_code == 200, res.text
    return res.json()["data"]


async def _reports(client_client, pid: str, **params) -> list[dict]:
    res = await client_client.get(f"{BASE}/{pid}/reports", params=params)
    return res.json()["data"]


async def _employee(client, client_client, slug: str, role_name: str, tag: str):
    """Create an employee holding `role_name` and return an auth header."""
    roles = (await client_client.get("/api/v1/settings/roles")).json()["data"]
    role_id = next(r["id"] for r in roles if r["name"] == role_name)
    email = f"{tag}@{slug}.com"
    res = await client_client.post("/api/v1/settings/employees", json={
        "name": f"{role_name} {tag}", "email": email, "role_id": role_id,
    })
    assert res.status_code == 201, res.text
    temp_pw = res.json()["data"]["temp_password"]
    res = await client.post("/api/v1/auth/login", json={
        "company": slug, "email": email, "password": temp_pw,
    })
    assert res.status_code == 200, res.text
    return {"Authorization": f"Bearer {res.json()['data']['access_token']}"}


async def _product_with_stock(client_client, sku: str, qty: float, cost_price: float) -> dict:
    res = await client_client.post("/api/v1/inventory/products", json={
        "sku": sku, "name": f"Panel {sku}", "unit": "pcs", "cost_price": cost_price,
    })
    assert res.status_code == 201, res.text
    product = res.json()["data"]
    warehouses = (await client_client.get("/api/v1/inventory/warehouses")).json()["data"]
    wh = next(w for w in warehouses if w["code"] == "WH1")
    if qty:
        res = await client_client.post("/api/v1/inventory/movements", json={
            "product_id": product["id"], "warehouse_id": wh["id"],
            "type": "receipt", "qty": qty,
        })
        assert res.status_code == 201, res.text
    product["warehouse"] = wh
    return product


async def _on_hand(client_client, product) -> float:
    res = await client_client.get("/api/v1/inventory/stock-levels", params={
        "product_id": product["id"]})
    rows = res.json()["data"]
    return sum(r["on_hand"] for r in rows)


# --- creation & stage 1 entry ------------------------------------------------

async def test_create_project_enters_the_machine_waiting_on_documents(client_client):
    project = await _create_project(client_client)
    assert project["code"] == "PRJ-0001"
    assert project["current_stage_order"] == 1
    assert project["current_stage_key"] == "project_initiation"
    assert project["status"] == "active"
    # stage 1's three blocking documents are missing → `waiting` (§4, acceptance #2)
    assert project["stage_instance"]["status"] == "waiting"

    detail = await _stage(client_client, project["id"], 1)
    waiting = set(detail["evaluation"]["waiting_on"])
    assert waiting == {
        "doc:loi_or_po", "doc:scope_boq_approved", "doc:site_access_confirmed",
    }

    # sequential per-tenant codes
    second = await _create_project(client_client, name="Villa Flooring")
    assert second["code"] == "PRJ-0002"

    # the timeline exposes all 9 stages, only stage 1 entered
    res = await client_client.get(f"{BASE}/{project['id']}/timeline")
    stages = res.json()["data"]["stages"]
    assert [s["order"] for s in stages] == list(range(1, 10))
    assert stages[0]["status"] == "waiting"
    assert all(s["status"] == "pending" for s in stages[1:])

    # board mirrors the current stage picture
    res = await client_client.get(f"{BASE}/{project['id']}/board")
    board = res.json()["data"]
    assert board["stage"]["key"] == "project_initiation"
    assert "doc:site_access_confirmed" in board["waiting_on"]

    # activity feed carries the machine events (§14)
    res = await client_client.get("/api/v1/activity", params={"module": "projects"})
    actions = [a["action"] for a in res.json()["data"]]
    assert "project.created" in actions
    assert "stage.entered" in actions


async def test_unreached_stage_is_404_and_bogus_ids_are_404(client_client):
    project = await _create_project(client_client)
    res = await client_client.get(f"{BASE}/{project['id']}/stages/2")
    assert res.status_code == 404
    res = await client_client.get(f"{BASE}/not-an-id")
    assert res.status_code == 404
    res = await client_client.post(BASE, json={
        "name": "Bad link", "crm_account_id": "64b000000000000000000000",
    })
    assert res.status_code == 404  # CRM account must exist (§1)


# --- the approval engine (§5) -------------------------------------------------

async def test_submit_with_missing_documents_short_circuits_to_issue_report(client_client):
    """§5.2: automated validation failure never reaches an approver — it opens
    an Issue Report and the stage stays unworkable."""
    project = await _create_project(client_client)
    pid = project["id"]

    res = await _submit(client_client, pid, 1)
    assert res.status_code == 200
    body = res.json()["data"]
    assert body["validation"]["passed"] is False
    failed = {c["key"] for c in body["validation"]["checks"] if not c["passed"]}
    assert "documents_present" in failed
    assert body["report"]["type"] == "issue"
    assert body["instance"]["status"] == "waiting"

    # resubmitting does not stack duplicate open reports (dedupe)
    await _submit(client_client, pid, 1)
    issues = await _reports(client_client, pid, type="issue", status="open")
    assert len(issues) == 1

    # nothing pending approval → approve is a 409
    res = await _approve(client_client, pid, 1)
    assert res.status_code == 409


async def test_supply_submit_approve_advances_to_next_stage(client_client):
    project = await _create_project(client_client)
    pid = project["id"]

    instance = await _supply(client_client, pid, 1, *STAGE1_DOCS)
    assert instance["status"] == "in_progress"  # §4: waiting → in_progress

    res = await _submit(client_client, pid, 1)
    body = res.json()["data"]
    assert body["validation"]["passed"] is True
    assert body["instance"]["status"] == "pending_approval"
    assert body["approval"]["state"] == "manager_review"
    assert body["approval"]["approver_role"] == "project_director"

    res = await _approve(client_client, pid, 1, comment="LGTM")
    body = res.json()["data"]
    assert body["stage"] == "approved"
    assert body["next_stage"]["order"] == 2

    # the project moved, history recorded the exit; stage 2's only entry gate is
    # a dependency on stage 1 (now approved), so it opens straight to in_progress
    res = await client_client.get(f"{BASE}/{pid}")
    doc = res.json()["data"]
    assert doc["current_stage_order"] == 2
    assert doc["stage_history"][-1]["key"] == "project_initiation"
    assert doc["stage_history"][-1]["result"] == "approved"
    assert (await _stage(client_client, pid, 2))["instance"]["status"] == "in_progress"

    # a decided stage cannot be re-submitted (§4: approved is terminal)
    res = await _submit(client_client, pid, 1)
    assert res.status_code == 409


async def test_approver_must_hold_the_stage_position(client, client_client, onboarded_company):
    """§9/acceptance #1: projects WRITE alone is not enough to approve — the
    caller must hold the stage's approver position via the Settings map."""
    slug = onboarded_company["slug"]
    project = await _create_project(client_client)
    pid = project["id"]
    await _supply(client_client, pid, 1, *STAGE1_DOCS)
    await _submit(client_client, pid, 1)

    # Member holds projects WRITE but is not project_director
    member = await _employee(client, client_client, slug, "Member", "pm-member")
    res = await client.post(f"{BASE}/{pid}/stages/1/approve", json={},
                            headers=member)
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "PERMISSION_DENIED"
    assert "project_director" in res.json()["error"]["message"]

    # remap the position to the Member role → the same user may now approve
    res = await client_client.patch(
        "/api/v1/settings/approver-roles/project_director",
        json={"client_roles": ["Member"]},
    )
    assert res.status_code == 200, res.text
    res = await client.post(f"{BASE}/{pid}/stages/1/approve", json={},
                            headers=member)
    assert res.status_code == 200, res.text
    assert res.json()["data"]["next_stage"]["order"] == 2


async def test_rejection_opens_typed_report_and_recovery_loop(client_client):
    """§5.5/acceptance #5: reject → typed report + owner, recovery_loops++,
    stage reopened for mandatory resubmission."""
    project = await _create_project(client_client)
    pid = project["id"]
    await _supply(client_client, pid, 1, *STAGE1_DOCS)
    await _submit(client_client, pid, 1)

    res = await _reject(client_client, pid, 1, comment="Scope missing annex B")
    assert res.status_code == 200, res.text
    body = res.json()["data"]
    assert body["recovery_loops"] == 1
    assert body["report"]["type"] == "change"  # stage 1 recovery has no type → default
    assert body["report"]["owner_id"] == project["pm_id"]
    assert body["report"]["status"] == "open"
    assert body["instance"]["status"] == "in_progress"  # docs still supplied

    # nothing is awaiting a decision anymore
    res = await _reject(client_client, pid, 1, comment="again")
    assert res.status_code == 409

    # the mandatory resubmission loop closes: submit again → approve advances
    await _submit(client_client, pid, 1)
    res = await _approve(client_client, pid, 1)
    assert res.status_code == 200
    assert res.json()["data"]["next_stage"]["order"] == 2

    # exactly one typed report was opened for the rejection
    res = await client_client.get(f"{BASE}/{pid}/reports", params={"type": "change"})
    assert res.json()["meta"]["total"] == 1


async def test_starved_stage_raises_missing_information_report(client_client):
    """§6.2: a stage starved of its entry documents raises a Missing Information
    report when its verification task runs (deduped while it stays open). In
    v2.0 the entry documents live on Stage 1 (project_initiation)."""
    project = await _create_project(client_client)
    pid = project["id"]

    res = await client_client.post(
        f"{BASE}/{pid}/stages/1/tasks/log_client_requirements/run"
    )
    assert res.status_code == 200, res.text
    await client_client.post(
        f"{BASE}/{pid}/stages/1/tasks/log_client_requirements/run"
    )
    missing = await _reports(client_client, pid, type="missing_information")
    assert len(missing) == 1
    assert missing[0]["status"] == "open"

    # unknown task key on the stage is a validation error
    res = await client_client.post(f"{BASE}/{pid}/stages/1/tasks/not_a_task/run")
    assert res.status_code == 422


# --- physical gates & the on_hold loop (§8, acceptance #3/#4) -----------------

async def test_reject_holds_the_project_until_the_report_is_resolved(client_client):
    """Stage 7 (Site Readiness) recovery is `on_hold`: a rejected inspection
    suspends the whole project until the recovery report is resolved (§4). No
    crew mobilises before the site is signed off."""
    project = await _create_project(client_client)
    pid = project["id"]
    stages, gates = await _machine_config(client_client)
    for order in range(1, 7):
        await _advance(client_client, pid, order, stages, gates)

    # log passing readiness readings so the stage can reach an approval decision
    for gate_key in ("concrete_rh_astm_f2170", "subfloor_flatness", "substrate_soundness"):
        res = await _gate_result(client_client, pid, 7, gate_key,
                                 **_passing_payload(gates[gate_key]))
        assert res.json()["data"]["result"]["passed"] is True, gate_key
    await _submit(client_client, pid, 7)

    # the inspector rejects: the site is not ready → project + stage on_hold
    res = await _reject(client_client, pid, 7, comment="Slab still wet in zone C")
    assert res.status_code == 200, res.text
    assert res.json()["data"]["instance"]["status"] == "on_hold"

    res = await client_client.get(f"{BASE}/{pid}")
    assert res.json()["data"]["status"] == "on_hold"

    # installation is blocked: the held stage cannot be submitted (§4)
    res = await _submit(client_client, pid, 7)
    assert res.status_code == 409

    # resolving the recovery report clears the hold (§4)
    open_reports = await _reports(client_client, pid, status="open")
    assert len(open_reports) == 1
    rid = open_reports[0]["id"]
    res = await client_client.patch(f"{BASE}/{pid}/reports/{rid}",
                                    json={"status": "resolved"})
    assert res.status_code == 200
    assert res.json()["data"]["resolved_at"] is not None

    res = await client_client.get(f"{BASE}/{pid}")
    assert res.json()["data"]["status"] == "active"
    assert (await _stage(client_client, pid, 7))["instance"]["status"] == "in_progress"

    # the readings still stand → resubmit and the stage approves
    await _submit(client_client, pid, 7)
    res = await _approve(client_client, pid, 7)
    assert res.status_code == 200, res.text
    assert res.json()["data"]["next_stage"]["order"] == 8


async def test_gate_results_are_scored_by_the_engine_not_the_caller(client_client):
    project = await _create_project(client_client)
    pid = project["id"]
    # a gate that does not attach to the stage is rejected
    res = await _gate_result(client_client, pid, 1, "timber_moisture_content",
                             readings=[{"value": 7}])
    assert res.status_code == 422
    res = await _gate_result(client_client, pid, 1, "no_such_gate",
                             readings=[{"value": 7}])
    assert res.status_code == 404


async def test_tenant_edited_threshold_drives_evaluation(client_client):
    """§8: thresholds are seeded defaults, editable per tenant — the engine
    scores against the tenant's copy. Concrete RH (G3) lives on Stage 7."""
    res = await client_client.patch(f"{BASE}/config/gates/concrete_rh_astm_f2170",
                                    json={"threshold": {"max_rh_pct": 60}})
    assert res.status_code == 200
    assert res.json()["data"]["threshold"]["max_rh_pct"] == 60

    project = await _create_project(client_client)
    pid = project["id"]
    stages, gates = await _machine_config(client_client)
    for order in range(1, 7):
        await _advance(client_client, pid, order, stages, gates)

    # 65% RH passes the seeded 75 default but fails the tenant's 60 limit
    res = await _gate_result(client_client, pid, 7, "concrete_rh_astm_f2170",
                             readings=[{"location": "slab", "value": 65}])
    assert res.json()["data"]["result"]["passed"] is False


# --- budget check (§5.2) ------------------------------------------------------

async def test_over_budget_blocks_automated_validation(client_client):
    project = await _create_project(client_client, planned_budget=100)
    pid = project["id"]
    await _supply(client_client, pid, 1, *STAGE1_DOCS)

    # a 200 actual against a 100 plan → budget_ok fails at submit
    res = await client_client.post(f"{BASE}/{pid}/job-costs", json={
        "cost_type": "labor", "hours": 4, "unit_cost": 50,
        "post_to_finance": False,
    })
    assert res.status_code == 201, res.text
    assert res.json()["data"]["amount"] == 200

    res = await _submit(client_client, pid, 1)
    failed = {c["key"] for c in res.json()["data"]["validation"]["checks"]
              if not c["passed"]}
    assert failed == {"budget_ok"}

    # raising the plan unblocks it
    await client_client.patch(f"{BASE}/{pid}", json={"planned_budget": 1000})
    res = await _submit(client_client, pid, 1)
    assert res.json()["data"]["validation"]["passed"] is True

    # a job cost with no quantity/hours or price is rejected
    res = await client_client.post(f"{BASE}/{pid}/job-costs", json={
        "cost_type": "labor", "post_to_finance": False,
    })
    assert res.status_code == 422


# --- job costs post to Finance (§3.9, acceptance #7) --------------------------

async def test_job_cost_posts_balanced_entry_and_rolls_into_budget(client_client):
    project = await _create_project(client_client, planned_budget=10_000)
    pid = project["id"]

    res = await client_client.post(f"{BASE}/{pid}/job-costs", json={
        "cost_type": "labor", "description": "CNC operator",
        "hours": 10, "unit_cost": 45,
    })
    assert res.status_code == 201, res.text
    cost = res.json()["data"]
    assert cost["amount"] == 450
    assert cost["posted_to_finance_ref"] is not None

    # the ledger carries a balanced Dr COGS / Cr AP entry for it
    res = await client_client.get("/api/v1/finance/journal-entries")
    entries = res.json()["data"]
    assert len(entries) == 1
    entry = entries[0]
    assert entry["id"] == cost["posted_to_finance_ref"]
    assert sum(line["debit"] for line in entry["lines"]) == 450
    assert sum(line["credit"] for line in entry["lines"]) == 450
    assert project["code"] in entry["memo"]

    # and the project budget knows the actual
    res = await client_client.get(f"{BASE}/{pid}")
    assert res.json()["data"]["budget"]["actual"] == 450

    res = await client_client.get(f"{BASE}/{pid}/job-costs")
    assert res.json()["meta"]["total"] == 1


# --- stage 5: inventory reservation (§1, acceptance #7) -----------------------

async def test_stage5_reserves_bom_stock_through_inventory(client_client):
    product = await _product_with_stock(client_client, "SKU-CLAD", qty=100, cost_price=40)
    project = await _create_project(client_client, planned_budget=50_000)
    pid = project["id"]
    stages, gates = await _machine_config(client_client)
    for order in range(1, 5):
        await _advance(client_client, pid, order, stages, gates)

    # Stage 5 · Material Procurement (G2): the bom_present gate is a document,
    # the reservable BOM carries the product lines (a bom_present *file* must not
    # shadow the real BOM — §3 trap).
    await _supply(client_client, pid, 5, "bom_present")
    res = await client_client.post(f"{BASE}/{pid}/deliverables", json={
        "kind": "bom", "title": "Lobby BOM", "file_ref": "vault://bom-r1",
        "lines": [{"product_id": product["id"], "qty": 10}],
    })
    assert res.status_code == 201, res.text

    await _submit(client_client, pid, 5)
    res = await _approve(client_client, pid, 5)
    assert res.status_code == 200, res.text
    reservations = res.json()["data"]["integration"]["reservations"]
    assert len(reservations) == 1
    assert reservations[0]["qty"] == 10

    # stock left general availability through a real Inventory movement
    assert await _on_hand(client_client, product) == 90
    res = await client_client.get("/api/v1/inventory/movements",
                                  params={"product_id": product["id"]})
    movement = next(m for m in res.json()["data"] if m["qty"] == -10)
    assert movement["ref"]["module"] == "projects"
    assert movement["ref"]["doc_id"] == pid

    # the reserved value is committed against the budget (10 × 40 cost)
    res = await client_client.get(f"{BASE}/{pid}")
    assert res.json()["data"]["budget"]["committed"] == 400

    # a material actual converts commitment → actual (no double count)
    res = await client_client.post(f"{BASE}/{pid}/job-costs", json={
        "cost_type": "material", "quantity": 10, "unit_cost": 40,
    })
    assert res.status_code == 201, res.text
    budget = (await client_client.get(f"{BASE}/{pid}")).json()["data"]["budget"]
    assert budget["actual"] == 400
    assert budget["committed"] == 0


async def test_insufficient_stock_fails_stage5_approval_recoverably(client_client):
    """Inventory's own INSUFFICIENT_STOCK guard applies (§1) — and a failed
    integration must NOT wedge the machine: the stage stays pending_approval
    and approving again after a receipt succeeds."""
    scarce = await _product_with_stock(client_client, "SKU-RARE", qty=3, cost_price=10)
    plenty = await _product_with_stock(client_client, "SKU-BULK", qty=50, cost_price=5)
    project = await _create_project(client_client)
    pid = project["id"]
    stages, gates = await _machine_config(client_client)
    for order in range(1, 5):
        await _advance(client_client, pid, order, stages, gates)

    await _supply(client_client, pid, 5, "bom_present")
    res = await client_client.post(f"{BASE}/{pid}/deliverables", json={
        "kind": "bom", "title": "BOM", "file_ref": "vault://bom",
        "lines": [
            {"product_id": plenty["id"], "qty": 20},
            {"product_id": scarce["id"], "qty": 10},
        ],
    })
    assert res.status_code == 201, res.text
    await _submit(client_client, pid, 5)

    res = await _approve(client_client, pid, 5)
    assert res.status_code == 409, res.text
    assert res.json()["error"]["code"] == "INSUFFICIENT_STOCK"

    # the partial reservation was compensated — nothing left the warehouse
    assert await _on_hand(client_client, plenty) == 50
    assert await _on_hand(client_client, scarce) == 3

    # the stage is still awaiting the decision, not stuck approved
    assert (await _stage(client_client, pid, 5))["instance"]["status"] == "pending_approval"
    res = await client_client.get(f"{BASE}/{pid}")
    assert res.json()["data"]["current_stage_order"] == 5

    # goods arrive → the same approval now goes through
    wh = scarce["warehouse"]
    res = await client_client.post("/api/v1/inventory/movements", json={
        "product_id": scarce["id"], "warehouse_id": wh["id"],
        "type": "receipt", "qty": 20,
    })
    assert res.status_code == 201
    res = await _approve(client_client, pid, 5)
    assert res.status_code == 200, res.text
    assert await _on_hand(client_client, plenty) == 30
    assert await _on_hand(client_client, scarce) == 13


# --- the full walk (acceptance #1, #4, #8) ------------------------------------

async def test_full_walk_to_handover(client_client):
    """Walk all 9 stages start→finish, proving the machine only ever advances
    through gates+validation+approval, the timber-MC gate holds installation, and
    Stage 9 emits the handover pack (incl. the G1–G5 defence file) + final
    invoice and closes."""
    product = await _product_with_stock(client_client, "SKU-WALK", qty=30, cost_price=25)

    # CRM link (§1: stage 1 links the project to a CRM account)
    res = await client_client.post("/api/v1/crm/accounts",
                                   json={"name": "Globex Towers"})
    account_id = res.json()["data"]["id"]

    project = await _create_project(
        client_client, name="Globex HQ Cladding",
        crm_account_id=account_id, planned_budget=8_000,
    )
    pid = project["id"]
    assert project["crm_account_id"] == account_id
    stages, gates = await _machine_config(client_client)

    for order in range(1, 5):  # Stage 1, auto-advance Stage 2, Stages 3–4
        await _advance(client_client, pid, order, stages, gates)

    # Stage 5 with a real BOM reservation
    await _supply(client_client, pid, 5, "bom_present")
    await client_client.post(f"{BASE}/{pid}/deliverables", json={
        "kind": "bom", "title": "BOM", "file_ref": "vault://bom",
        "lines": [{"product_id": product["id"], "qty": 8}],
    })
    await _submit(client_client, pid, 5)
    assert (await _approve(client_client, pid, 5)).status_code == 200

    for order in (6, 7):  # Factory Release, Site Readiness
        await _advance(client_client, pid, order, stages, gates)

    # Stage 8: installation cannot pass while timber MC is out of range (§15 #4/G5)
    res = await _gate_result(client_client, pid, 8, "timber_moisture_content",
                             readings=[{"location": "panel-A", "value": 10.5}])
    assert res.json()["data"]["result"]["passed"] is False
    res = await _submit(client_client, pid, 8)
    body = res.json()["data"]
    assert body["validation"]["passed"] is False
    failed = {c["key"] for c in body["validation"]["checks"] if not c["passed"]}
    assert "quality_gates_passed" in failed

    # MC back in range + the ambient log recorded → the gate passes
    for gate_key in ("timber_moisture_content", "ambient_rh_temp_log"):
        res = await _gate_result(client_client, pid, 8, gate_key,
                                 **_passing_payload(gates[gate_key]))
        assert res.json()["data"]["result"]["passed"] is True, gate_key
    await _submit(client_client, pid, 8)
    assert (await _approve(client_client, pid, 8)).status_code == 200

    # Stage 9: Final Inspection & Client Handover closes the machine (§15 #8)
    result = await _advance(client_client, pid, 9, stages, gates)
    assert result["project_status"] == "completed"
    assert result["next_stage"] is None
    handover = result["handover"]
    assert {d["title"] for d in handover["documents"]} == {
        "Completion Certificate", "Warranty",
        "Operation & Maintenance Manuals", "As-built Drawings",
        "Gate Records G1–G5 (Technical Defence File)",
    }
    assert handover["final_invoice"]["total"] == 8_000

    res = await client_client.get(f"{BASE}/{pid}")
    doc = res.json()["data"]
    assert doc["status"] == "completed"
    assert len(doc["stage_history"]) == 9

    res = await client_client.get(f"{BASE}/{pid}/timeline")
    assert all(s["status"] == "approved" for s in res.json()["data"]["stages"])

    # the final invoice is a real Finance document tied to the CRM account
    res = await client_client.get("/api/v1/finance/invoices")
    invoice = next(i for i in res.json()["data"]
                   if i["id"] == handover["final_invoice"]["id"])
    assert invoice["customer_ref"]["crm_account_id"] == account_id

    # newest-first feed: the closing lifecycle events sit on the first page
    # (project.created is proven in the creation test; by now it has scrolled off)
    res = await client_client.get("/api/v1/activity",
                                  params={"module": "projects", "page_size": 100})
    actions = {a["action"] for a in res.json()["data"]}
    assert {"stage.approved", "project.handover", "project.completed"} <= actions


# --- deliverables (§3.7, acceptance #6) ---------------------------------------

async def test_deliverable_revisions_are_append_only(client_client):
    project = await _create_project(client_client)
    pid = project["id"]
    res = await client_client.post(f"{BASE}/{pid}/deliverables", json={
        "kind": "shop_drawing", "title": "Lobby elevations",
        "file_ref": "vault://rev-a",
    })
    assert res.status_code == 201
    did = res.json()["data"]["id"]

    for ref in ("vault://rev-b", "vault://rev-c"):
        res = await client_client.post(
            f"{BASE}/{pid}/deliverables/{did}/revisions",
            json={"file_ref": ref, "note": "clash fix"},
        )
        assert res.status_code == 201, res.text

    doc = res.json()["data"]
    assert doc["current_version"] == 3
    # every prior version survives untouched
    assert [v["v"] for v in doc["versions"]] == [1, 2, 3]
    assert doc["versions"][0]["file_ref"] == "vault://rev-a"
    audit = [a["action"] for a in doc["immutable_audit"]]
    assert audit == ["created", "revised", "revised"]

    res = await client_client.get(f"{BASE}/{pid}/deliverables",
                                  params={"kind": "shop_drawing"})
    assert res.json()["meta"]["total"] == 1


# --- client approvals (§9) ----------------------------------------------------
#
# v2.0 folds client acceptance into Stage 9 (project_director): there is no
# `client` approver stage and no client-portal user type. Approving a stage
# requires `projects` WRITE plus the stage's approver position — nothing
# client-scoped remains to test.


# --- calendar contribution (§14) ---------------------------------------------

async def test_calendar_surfaces_every_pm_event_type(client_client):
    """§14: the PM calendar contributes milestone, stage_due, delivery,
    acclimation, and gate_due events from the project's schedule."""
    await _create_project(client_client, name="Scheduled Tower", milestone_schedule=[
        {"key": "kickoff", "name": "Kickoff", "due_date": _iso(2)},
    ], schedule={
        "delivery_date": _iso(10),
        "acclimation_start": _iso(11),
        "acclimation_end": _iso(14),
        "stage_targets": [{"stage_key": "site_survey", "due_date": _iso(5)}],
        "gate_deadlines": [
            {"gate_key": "timber_moisture_content", "stage_key": "installation",
             "due_at": _iso(12)},
        ],
    })

    res = await client_client.get("/api/v1/calendar",
                                  params={"from": _iso(0), "to": _iso(30)})
    assert res.status_code == 200, res.text
    types = {e["type"] for e in res.json()["data"] if e["source_module"] == "projects"}
    assert types == {"milestone", "stage_due", "delivery", "acclimation", "gate_due"}

    # a narrow window keeps only what falls inside it (range filtering)
    res = await client_client.get("/api/v1/calendar",
                                  params={"from": _iso(0), "to": _iso(3)})
    types = {e["type"] for e in res.json()["data"] if e["source_module"] == "projects"}
    assert types == {"milestone"}  # only the day-2 kickoff is in [0, 3]


async def test_calendar_project_events_respect_read_permission(
    client, client_client, onboarded_company
):
    """A user who cannot READ projects sees no project events on the calendar,
    even though they can open the calendar (CLIENT_DASHBOARD §6)."""
    slug = onboarded_company["slug"]
    await _create_project(client_client, name="Hidden", milestone_schedule=[
        {"key": "m", "name": "Milestone", "due_date": _iso(3)},
    ])

    # Viewer: calendar READ, projects NONE
    viewer = await _employee(client, client_client, slug, "Viewer", "cal-viewer")
    res = await client.get("/api/v1/calendar", headers=viewer,
                           params={"from": _iso(0), "to": _iso(30)})
    assert res.status_code == 200
    assert not [e for e in res.json()["data"] if e["source_module"] == "projects"]


# --- RBAC gates ---------------------------------------------------------------

async def test_projects_rbac_gates(client, client_client, onboarded_company):
    slug = onboarded_company["slug"]
    await _create_project(client_client)

    # Viewer: projects=NONE → hidden entirely
    viewer = await _employee(client, client_client, slug, "Viewer", "pm-viewer")
    res = await client.get(BASE, headers=viewer)
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "PERMISSION_DENIED"

    # projects=VIEW (below READ) → sees it exists, cannot open the module
    await client_client.post("/api/v1/settings/roles", json={
        "name": "Contact", "permissions": {"dashboard": 2, "projects": 1},  # VIEW
    })
    contact = await _employee(client, client_client, slug, "Contact", "pm-contact")
    assert (await client.get(BASE, headers=contact)).status_code == 403

    # Manager: WRITE → full lifecycle allowed
    manager = await _employee(client, client_client, slug, "Manager", "pm-manager")
    assert (await client.get(BASE, headers=manager)).status_code == 200
    res = await client.post(BASE, json={"name": "Manager project"}, headers=manager)
    assert res.status_code == 201

    # admin realm tokens never reach client routes (audience separation)
    res = await client.get(BASE)
    assert res.status_code == 401
