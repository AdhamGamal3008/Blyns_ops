"""Production Phase 1 (docs/PRODUCTION_MODULE_PLAN.md §7): the Work Order object +
the cross-project Queue. WOs are proposed from a project's BOM (one per line),
pinned to the newest shop-drawing revision, and confirmed by the production_manager
(the seeded Owner holds that position by default).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

PP = "/api/v1/production"
PJ = "/api/v1/projects"


def _iso(days: int) -> str:
    return (datetime.now(UTC) + timedelta(days=days)).isoformat()


async def _product(client_client, sku: str, cost: float = 10.0) -> str:
    res = await client_client.post("/api/v1/inventory/products", json={
        "sku": sku, "name": f"Item {sku}", "unit": "pcs", "cost_price": cost,
    })
    assert res.status_code == 201, res.text
    return res.json()["data"]["id"]


async def _project_with_bom(client_client, *, lines, drawing=True, delivery_in=10) -> dict:
    res = await client_client.post(PJ, json={
        "name": "Lobby Cladding", "schedule": {"delivery_date": _iso(delivery_in)},
    })
    assert res.status_code == 201, res.text
    pid = res.json()["data"]["id"]

    drawing_id = None
    if drawing:
        res = await client_client.post(f"{PJ}/{pid}/deliverables", json={
            "kind": "shop_drawing", "title": "SD-01 Lobby cladding",
            "file_ref": "vault://sd-01-v1",
        })
        assert res.status_code == 201, res.text
        drawing_id = res.json()["data"]["id"]

    res = await client_client.post(f"{PJ}/{pid}/deliverables", json={
        "kind": "bom", "title": "Lobby BOM", "file_ref": "vault://bom", "lines": lines,
    })
    assert res.status_code == 201, res.text
    return {"pid": pid, "drawing_id": drawing_id}


async def test_propose_generates_one_wo_per_bom_line_pinned_to_the_drawing(client_client):
    p1 = await _product(client_client, "PANEL-1")
    p2 = await _product(client_client, "DESK-1")
    ctx = await _project_with_bom(client_client, lines=[
        {"product_id": p1, "qty": 42},
        {"product_id": p2, "qty": 1},
    ])

    res = await client_client.post(f"{PP}/work-orders/propose", json={"project_id": ctx["pid"]})
    assert res.status_code == 200, res.text
    drafts = res.json()["data"]

    assert len(drafts) == 2                                   # one per BOM line
    assert sorted(d["qty_ordered"] for d in drafts) == [1, 42]
    for d in drafts:
        # pinned to a specific revision, never "latest" (plan §2.1)
        assert d["source_drawing"]["deliverable_id"] == ctx["drawing_id"]
        assert d["source_drawing"]["version"] == 1
        assert d["due_date"] is not None                     # back-calc from delivery


async def test_confirm_creates_work_orders_that_land_in_the_queue_and_register(client_client):
    p1 = await _product(client_client, "PANEL-2")
    ctx = await _project_with_bom(client_client, lines=[{"product_id": p1, "qty": 42}])
    drafts = (await client_client.post(
        f"{PP}/work-orders/propose", json={"project_id": ctx["pid"]})).json()["data"]

    res = await client_client.post(f"{PP}/work-orders", json={"work_orders": drafts})
    assert res.status_code == 200, res.text
    created = res.json()["data"]
    assert len(created) == 1
    wo = created[0]
    assert wo["status"] == "queued"
    assert wo["code"].startswith("WO-")
    assert wo["qty"]["ordered"] == 42 and wo["qty"]["done"] == 0

    register = (await client_client.get(f"{PP}/work-orders")).json()
    assert register["meta"]["total"] == 1
    assert register["data"][0]["code"] == wo["code"]

    queue = (await client_client.get(f"{PP}/queue")).json()["data"]
    assert any(w["id"] == wo["id"] for w in queue)

    detail = (await client_client.get(f"{PP}/work-orders/{wo['id']}")).json()["data"]
    assert detail["revision_conflict"] is False


async def test_a_new_drawing_revision_raises_a_revision_conflict(client_client):
    p1 = await _product(client_client, "PANEL-3")
    ctx = await _project_with_bom(client_client, lines=[{"product_id": p1, "qty": 5}])
    drafts = (await client_client.post(
        f"{PP}/work-orders/propose", json={"project_id": ctx["pid"]})).json()["data"]
    wo_id = (await client_client.post(
        f"{PP}/work-orders", json={"work_orders": drafts})).json()["data"][0]["id"]

    # a revision issued mid-production must not update the WO in place — it flags
    res = await client_client.post(
        f"{PJ}/{ctx['pid']}/deliverables/{ctx['drawing_id']}/revisions",
        json={"file_ref": "vault://sd-01-v2", "note": "clash fix"},
    )
    assert res.status_code == 201, res.text

    detail = (await client_client.get(f"{PP}/work-orders/{wo_id}")).json()["data"]
    assert detail["revision_conflict"] is True


async def test_propose_requires_a_bom_carrying_line_items(client_client):
    pid = (await client_client.post(PJ, json={"name": "No BOM"})).json()["data"]["id"]
    res = await client_client.post(f"{PP}/work-orders/propose", json={"project_id": pid})
    assert res.status_code == 422, res.text
