"""Production Phase 3 (docs/PRODUCTION_MODULE_PLAN.md §7): station load/capacity
and manager allocation. Enables Production on the fixture tenant so the work
centres seed, then reuses the Phase 2 walk to Stage 6 to get real WOs to place.
"""

from __future__ import annotations

from tests.integration.test_production_workflow import (
    _at_factory_release,
    _make_two_wos,
)

PP = "/api/v1/production"


async def _enable_production(admin_client, onboarded_company) -> None:
    cid = str(onboarded_company["company"]["_id"])
    res = await admin_client.patch(f"/api/v1/admin/companies/{cid}", json={
        "enabled_modules": [
            "dashboard", "settings", "projects", "production", "crm", "inventory", "finance",
        ],
    })
    assert res.status_code == 200, res.text


async def test_station_load_and_manager_allocation(
    client_client, admin_client, onboarded_company
):
    await _enable_production(admin_client, onboarded_company)

    # the work centres seeded, and start on an empty board
    stations = (await client_client.get(f"{PP}/stations")).json()["data"]
    assert len(stations) >= 2
    cut = next(s for s in stations if s["code"] == "CUT")
    assert cut["load"]["work_orders"] == 0

    ctx = await _at_factory_release(client_client)
    a, b = (w["id"] for w in await _make_two_wos(client_client, ctx["pid"]))

    # a manager reallocates WO A onto CUT
    res = await client_client.post(f"{PP}/work-orders/{a}/allocate",
        json={"station_id": cut["id"]})
    assert res.status_code == 200, res.text
    assert res.json()["data"]["current_station_id"] == cut["id"]
    assert res.json()["data"]["station_name"] == cut["name"]

    # CUT's load now reflects the 10 units still to build
    stations = (await client_client.get(f"{PP}/stations")).json()["data"]
    cut = next(s for s in stations if s["code"] == "CUT")
    assert cut["load"]["work_orders"] == 1 and cut["load"]["units"] == 10

    # auto-allocate WO B by load → never the already-loaded CUT
    res = await client_client.post(f"{PP}/work-orders/{b}/auto-allocate")
    assert res.status_code == 200, res.text
    chosen = res.json()["data"]["current_station_id"]
    assert chosen is not None and chosen != cut["id"]
