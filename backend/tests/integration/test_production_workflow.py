"""Production Phase 2 (docs/PRODUCTION_MODULE_PLAN.md §7): the WO status machine,
QC hold that blocks only its own WO, the Stage-6 checklist drive, material/labor
job costs, and the rework new-reservation rule (D1).

Reuses the projects stage-walk helpers to get a project to Stage 6 · Factory
Release (release requires Stage 5 approved — sync rule 1).
"""

from __future__ import annotations

from tests.integration.test_projects import (
    _advance,
    _approve,
    _create_project,
    _machine_config,
    _product_with_stock,
    _submit,
    _supply,
)

PP = "/api/v1/production"
PJ = "/api/v1/projects"


async def _at_factory_release(client_client) -> dict:
    """Walk a project through Stages 1–5 (a two-line BOM reserved) so it sits at
    Stage 6 · Factory Release. Returns the project id + the two products."""
    p1 = await _product_with_stock(client_client, "SKU-A", qty=100, cost_price=40)
    p2 = await _product_with_stock(client_client, "SKU-B", qty=100, cost_price=40)
    project = await _create_project(client_client, planned_budget=50_000)
    pid = project["id"]
    stages, gates = await _machine_config(client_client)
    for order in range(1, 5):
        await _advance(client_client, pid, order, stages, gates)

    await _supply(client_client, pid, 5, "bom_present")
    res = await client_client.post(f"{PJ}/{pid}/deliverables", json={
        "kind": "bom", "title": "BOM", "file_ref": "vault://bom",
        "lines": [{"product_id": p1["id"], "qty": 10}, {"product_id": p2["id"], "qty": 10}],
    })
    assert res.status_code == 201, res.text
    await _submit(client_client, pid, 5)
    res = await _approve(client_client, pid, 5)
    assert res.status_code == 200, res.text
    return {"pid": pid, "products": [p1, p2]}


async def _make_two_wos(client_client, pid: str) -> list[dict]:
    drafts = (await client_client.post(
        f"{PP}/work-orders/propose", json={"project_id": pid})).json()["data"]
    assert len(drafts) == 2
    return (await client_client.post(
        f"{PP}/work-orders", json={"work_orders": drafts})).json()["data"]


async def test_release_requires_stage_5_approved(client_client):
    p = await _product_with_stock(client_client, "SKU-G", qty=10, cost_price=5)
    pid = (await _create_project(client_client))["id"]
    await client_client.post(f"{PJ}/{pid}/deliverables",
        json={"kind": "shop_drawing", "title": "SD", "file_ref": "vault://sd"})
    await client_client.post(f"{PJ}/{pid}/deliverables", json={
        "kind": "bom", "title": "BOM", "file_ref": "vault://bom",
        "lines": [{"product_id": p["id"], "qty": 2}]})
    drafts = (await client_client.post(
        f"{PP}/work-orders/propose", json={"project_id": pid})).json()["data"]
    wo = (await client_client.post(
        f"{PP}/work-orders", json={"work_orders": drafts})).json()["data"][0]["id"]

    res = await client_client.post(f"{PP}/work-orders/{wo}/release")
    assert res.status_code == 422, res.text
    assert "Material Procurement" in res.json()["error"]["message"]


async def test_qc_hold_blocks_only_its_wo_and_drives_the_stage6_checklist(client_client):
    ctx = await _at_factory_release(client_client)
    pid = ctx["pid"]
    a, b = (w["id"] for w in await _make_two_wos(client_client, pid))

    # reservation committed 2 × 10 × 40 = 800
    proj = (await client_client.get(f"{PJ}/{pid}")).json()["data"]
    assert proj["budget"]["committed"] == 800

    # release + start both → each start issues material (400), drawing commitment down
    for wo in (a, b):
        assert (await client_client.post(f"{PP}/work-orders/{wo}/release")).status_code == 200
        assert (await client_client.post(f"{PP}/work-orders/{wo}/start")).status_code == 200
    proj = (await client_client.get(f"{PJ}/{pid}")).json()["data"]
    assert proj["budget"]["actual"] == 800 and proj["budget"]["committed"] == 0

    # both to QC (labor captured on A) → production section complete in the pipeline
    assert (await client_client.post(f"{PP}/work-orders/{a}/request-qc",
        json={"labor_hours": 8, "labor_rate": 25})).status_code == 200
    assert (await client_client.post(
        f"{PP}/work-orders/{b}/request-qc", json={})).status_code == 200
    rollup = (await client_client.get(f"{PP}/projects/{pid}/rollup")).json()["data"]
    assert rollup["sections"]["production"] == 100
    assert "production" in rollup["checklist_done"]
    assert "quality_control" not in rollup["checklist_done"]

    # pass A, hold B
    assert (await client_client.post(f"{PP}/work-orders/{a}/qc",
        json={"result": "pass"})).status_code == 200
    assert (await client_client.post(f"{PP}/work-orders/{b}/qc",
        json={"result": "hold", "defects": ["edge chip"]})).status_code == 200

    # the hold freezes only B; A passed; the project keeps moving (not frozen)
    assert (await client_client.get(f"{PP}/work-orders/{a}")).json()["data"]["status"] == "passed"
    assert (await client_client.get(f"{PP}/work-orders/{b}")).json()["data"]["status"] == "qc_hold"
    proj = (await client_client.get(f"{PJ}/{pid}")).json()["data"]
    assert proj["status"] == "active" and proj["current_stage_order"] == 6

    # QC section stays incomplete while B is held; production still complete
    rollup = (await client_client.get(f"{PP}/projects/{pid}/rollup")).json()["data"]
    assert rollup["sections"]["quality_control"] == 50
    assert "quality_control" not in rollup["checklist_done"]
    assert rollup["releasable"] is False

    # material + labor actuals posted to the project
    costs = (await client_client.get(f"{PJ}/{pid}/job-costs")).json()["data"]
    assert any(c["cost_type"] == "labor" and c["amount"] == 200 for c in costs)
    assert any(c["cost_type"] == "material" for c in costs)


async def test_rework_draws_a_new_inventory_reservation(client_client):
    ctx = await _at_factory_release(client_client)
    pid = ctx["pid"]
    wo = (await _make_two_wos(client_client, pid))[0]["id"]

    await client_client.post(f"{PP}/work-orders/{wo}/release")
    await client_client.post(f"{PP}/work-orders/{wo}/start")
    await client_client.post(f"{PP}/work-orders/{wo}/request-qc", json={})
    await client_client.post(f"{PP}/work-orders/{wo}/qc",
        json={"result": "hold", "defects": ["warp"]})

    res = await client_client.post(f"{PP}/work-orders/{wo}/rework", json={"note": "re-mill"})
    assert res.status_code == 200, res.text
    assert res.json()["data"]["status"] == "rework"

    # D1: the rework physically drew a new issue tagged to Production
    product_id = ctx["products"][0]["id"]
    movements = (await client_client.get(
        "/api/v1/inventory/movements", params={"product_id": product_id})).json()["data"]
    assert any(m["ref"]["module"] == "production" and m["ref"]["doc_id"] == wo
               for m in movements)
