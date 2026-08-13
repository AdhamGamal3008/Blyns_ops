"""Production Phase 4 (docs/PRODUCTION_MODULE_PLAN.md §7): packing + dispatch +
manifest. A passed WO packs (protection spec by material), stages (load → vehicle,
a confirmed delivery window, a generated manifest, an in-app site-supervisor
notice), then dispatches. Once every WO is staged all four Stage-6 checklist
sections are complete and the pipeline can release Stage 6 (the approve stays a
pipeline action — Production never hosts it).

Reuses the Phase 2 walk to Stage 6 · Factory Release.
"""

from __future__ import annotations

from app.core.db import get_db_manager
from tests.integration.test_production_workflow import (
    _at_factory_release,
    _make_two_wos,
)
from tests.integration.test_projects import _approve, _submit

PP = "/api/v1/production"
INV = "/api/v1/inventory"


def _tenant_db(onboarded_company):
    return get_db_manager().tenant(onboarded_company["company"]["db_name"])


async def _to_passed(client_client, wo_id: str) -> None:
    """Drive a queued WO through release → start → QC to `passed`."""
    for action in ("release", "start"):
        assert (await client_client.post(
            f"{PP}/work-orders/{wo_id}/{action}")).status_code == 200
    assert (await client_client.post(
        f"{PP}/work-orders/{wo_id}/request-qc", json={})).status_code == 200
    assert (await client_client.post(
        f"{PP}/work-orders/{wo_id}/qc", json={"result": "pass"})).status_code == 200


async def test_pack_stage_dispatch_completes_and_releases_stage6(
    client_client, onboarded_company
):
    ctx = await _at_factory_release(client_client)
    pid = ctx["pid"]
    # tag the first WO's product as a panel so the paneled protection spec flows;
    # the second stays uncategorised → the plain carton default.
    assert (await client_client.patch(
        f"{INV}/products/{ctx['products'][0]['id']}",
        json={"category": "panel"})).status_code == 200

    a, b = (w["id"] for w in await _make_two_wos(client_client, pid))
    for wo in (a, b):
        await _to_passed(client_client, wo)

    # --- pack A: protection spec derived from the panel material -------------
    res = await client_client.post(f"{PP}/work-orders/{a}/pack", json={})
    assert res.status_code == 200, res.text
    body = res.json()["data"]
    assert body["status"] == "packed"
    assert body["packing"]["type"] == "pallet"
    assert body["packing"]["moisture_barrier_ref"]          # panels get a barrier
    assert body["packing"]["labels"] == [body["code"]]

    # packing_protection clears only for A (50%) — the gate does not open early
    rollup = (await client_client.get(f"{PP}/projects/{pid}/rollup")).json()["data"]
    assert rollup["sections"]["packing_protection"] == 50
    assert "packing_protection" not in rollup["checklist_done"]

    # a passed WO cannot skip packing and stage directly
    assert (await client_client.post(
        f"{PP}/work-orders/{b}/stage", json={})).status_code == 422

    # --- stage A: load → vehicle, confirmed window, manifest, site notice ----
    res = await client_client.post(f"{PP}/work-orders/{a}/stage", json={
        "delivery_window_start": "2026-09-01T08:00:00Z",
        "delivery_window_end": "2026-09-01T12:00:00Z",
    })
    assert res.status_code == 200, res.text
    dispatch = res.json()["data"]["dispatch"]
    assert res.json()["data"]["status"] == "staged"
    assert dispatch["vehicle"] == "van"                     # 10 units → smallest band
    assert dispatch["manifest_ref"] and dispatch["delivery_note_ref"]
    assert dispatch["delivery_window"]["start"].startswith("2026-09-01")
    assert dispatch["site_notified_at"]

    # the site-supervisor notice landed in-app (activity, never an external send)
    db = _tenant_db(onboarded_company)
    assert await db.activity_log.count_documents(
        {"action": "production.site_notified", "entity.id": a}) == 1

    # B packs to the plain carton default, then stages
    res = await client_client.post(f"{PP}/work-orders/{b}/pack", json={})
    assert res.json()["data"]["packing"]["type"] == "carton"
    assert (await client_client.post(
        f"{PP}/work-orders/{b}/stage", json={})).status_code == 200

    # --- all four sections complete → Stage 6 is releasable ------------------
    rollup = (await client_client.get(f"{PP}/projects/{pid}/rollup")).json()["data"]
    assert set(rollup["checklist_done"]) >= {
        "production", "quality_control", "packing_protection", "delivery_planning"}
    assert rollup["releasable"] is True

    # Prove: the pipeline can now release Stage 6 (Production never hosts approve)
    res = await _submit(client_client, pid, 6)
    assert res.status_code == 200 and res.json()["data"]["validation"]["passed"], res.text
    assert (await _approve(client_client, pid, 6)).status_code == 200

    # --- dispatch A: it leaves the building and drops out of the Queue -------
    assert (await client_client.post(
        f"{PP}/work-orders/{a}/dispatch", json={})).status_code == 200
    board = {w["id"]: w["status"] for w in
             (await client_client.get(f"{PP}/dispatch")).json()["data"]}
    assert board[a] == "dispatched" and board[b] == "staged"
    queue = (await client_client.get(
        f"{PP}/queue", params={"all_due": True})).json()["data"]
    assert all(w["id"] != a for w in queue)

    # the manifest carries the generated refs + the packed spec
    manifest = (await client_client.get(
        f"{PP}/work-orders/{a}/manifest")).json()["data"]
    assert manifest["manifest_ref"] == dispatch["manifest_ref"]
    assert manifest["packing"]["type"] == "pallet"
    assert manifest["lines"]


async def test_dispatch_board_and_manifest_reflect_state(client_client):
    """A WO not yet staged has no manifest ref; the board only lists packed+."""
    ctx = await _at_factory_release(client_client)
    pid = ctx["pid"]
    a = (await _make_two_wos(client_client, pid))[0]["id"]
    await _to_passed(client_client, a)

    # before packing: absent from the dispatch board, no manifest ref yet
    board = (await client_client.get(f"{PP}/dispatch")).json()["data"]
    assert all(w["id"] != a for w in board)
    manifest = (await client_client.get(
        f"{PP}/work-orders/{a}/manifest")).json()["data"]
    assert manifest["manifest_ref"] is None

    # once packed it joins the board
    assert (await client_client.post(f"{PP}/work-orders/{a}/pack", json={})).status_code == 200
    board = (await client_client.get(f"{PP}/dispatch")).json()["data"]
    assert any(w["id"] == a and w["status"] == "packed" for w in board)
