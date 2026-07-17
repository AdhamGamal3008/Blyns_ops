"""Inventory module acceptance criteria (docs/modules/INVENTORY.md §6):
on-hand == signed ledger sum, over-issue rejection, balanced transfers, and the
low-stock list."""

from __future__ import annotations

import pytest


async def _product(client_client, sku: str, **extra) -> dict:
    res = await client_client.post("/api/v1/inventory/products", json={
        "sku": sku, "name": f"Product {sku}", "unit": "pcs", **extra,
    })
    assert res.status_code == 201, res.text
    return res.json()["data"]


async def _warehouse(client_client, code: str, name: str | None = None) -> dict:
    res = await client_client.post("/api/v1/inventory/warehouses", json={
        "code": code, "name": name or f"WH {code}",
    })
    assert res.status_code == 201, res.text
    return res.json()["data"]


async def _main_wh(client_client) -> dict:
    """The seeded `Main WH` (INVENTORY.md §4)."""
    res = await client_client.get("/api/v1/inventory/warehouses")
    return next(w for w in res.json()["data"] if w["code"] == "WH1")


async def _move(client_client, product, warehouse, mtype, qty, note=None):
    return await client_client.post("/api/v1/inventory/movements", json={
        "product_id": product["id"], "warehouse_id": warehouse["id"],
        "type": mtype, "qty": qty, "note": note,
    })


async def _on_hand(client_client, product, warehouse) -> float:
    res = await client_client.get("/api/v1/inventory/stock-levels", params={
        "product_id": product["id"], "warehouse_id": warehouse["id"],
    })
    rows = res.json()["data"]
    return rows[0]["on_hand"] if rows else 0.0


# --- acceptance #1: on-hand == signed ledger sum ------------------------------

async def test_on_hand_equals_signed_ledger_sum(client_client):
    p = await _product(client_client, "SKU-001")
    wh = await _main_wh(client_client)

    assert (await _move(client_client, p, wh, "receipt", 100)).status_code == 201
    assert (await _move(client_client, p, wh, "issue", 30)).status_code == 201
    assert (await _move(client_client, p, wh, "receipt", 5)).status_code == 201
    assert (await _move(
        client_client, p, wh, "adjustment", -5, note="damaged in transit"
    )).status_code == 201

    # 100 - 30 + 5 - 5 = 70
    assert await _on_hand(client_client, p, wh) == 70

    # the cache agrees with the ledger it is derived from
    res = await client_client.get("/api/v1/inventory/movements", params={
        "product_id": p["id"]})
    assert sum(m["qty"] for m in res.json()["data"]) == 70

    res = await client_client.get("/api/v1/inventory/reconcile")
    assert res.json()["data"]["consistent"] is True
    assert res.json()["data"]["drift"] == []


async def test_receipt_and_issue_signs_come_from_the_type(client_client):
    """A caller passes a positive qty; the type decides the direction, so an
    `issue` can never secretly add stock."""
    p = await _product(client_client, "SKU-SIGN")
    wh = await _main_wh(client_client)
    await _move(client_client, p, wh, "receipt", 10)

    res = await _move(client_client, p, wh, "issue", 4)
    assert res.json()["data"]["qty"] == -4
    assert await _on_hand(client_client, p, wh) == 6

    # a negative qty on a receipt/issue is a caller mistake, not a sign flip
    assert (await _move(client_client, p, wh, "issue", -4)).status_code == 422
    assert (await _move(client_client, p, wh, "receipt", -4)).status_code == 422
    assert (await _move(client_client, p, wh, "receipt", 0)).status_code == 422


async def test_movements_are_immutable(client_client):
    """§2: corrections are new adjustment entries — the ledger is never edited."""
    p = await _product(client_client, "SKU-IMMUT")
    wh = await _main_wh(client_client)
    res = await _move(client_client, p, wh, "receipt", 10)
    mid = res.json()["data"]["id"]

    for method in ("patch", "delete"):
        r = await getattr(client_client, method)(f"/api/v1/inventory/movements/{mid}")
        assert r.status_code in (404, 405), f"{method} → {r.status_code}"


async def test_adjustment_requires_a_note(client_client):
    p = await _product(client_client, "SKU-ADJ")
    wh = await _main_wh(client_client)
    await _move(client_client, p, wh, "receipt", 10)

    assert (await _move(client_client, p, wh, "adjustment", -1)).status_code == 422
    assert (await _move(
        client_client, p, wh, "adjustment", -1, note="   "
    )).status_code == 422
    assert (await _move(
        client_client, p, wh, "adjustment", -1, note="miscount"
    )).status_code == 201


# --- acceptance #2: over-issue rejected unless negative stock is enabled ------

async def test_issuing_more_than_on_hand_is_rejected(client_client):
    p = await _product(client_client, "SKU-002")
    wh = await _main_wh(client_client)
    await _move(client_client, p, wh, "receipt", 10)

    res = await _move(client_client, p, wh, "issue", 11)
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "INSUFFICIENT_STOCK"
    assert res.json()["error"]["details"]["on_hand"] == 10
    assert res.json()["error"]["details"]["requested"] == 11

    # the rejected issue left neither stock nor ledger behind
    assert await _on_hand(client_client, p, wh) == 10
    res = await client_client.get("/api/v1/inventory/movements", params={
        "product_id": p["id"]})
    assert res.json()["meta"]["total"] == 1

    # issuing exactly what is on hand is fine
    assert (await _move(client_client, p, wh, "issue", 10)).status_code == 201
    assert await _on_hand(client_client, p, wh) == 0


async def test_negative_stock_allowed_when_the_company_enables_it(client_client):
    p = await _product(client_client, "SKU-003")
    wh = await _main_wh(client_client)
    await _move(client_client, p, wh, "receipt", 5)

    assert (await _move(client_client, p, wh, "issue", 8)).status_code == 409

    # the company setting lives on the tenant company profile (SETTINGS.md §1.1)
    res = await client_client.patch("/api/v1/settings/company", json={
        "allow_negative_stock": True,
    })
    assert res.status_code == 200
    assert res.json()["data"]["allow_negative_stock"] is True

    assert (await _move(client_client, p, wh, "issue", 8)).status_code == 201
    assert await _on_hand(client_client, p, wh) == -3
    # even negative, the cache still equals the ledger
    assert (await client_client.get(
        "/api/v1/inventory/reconcile")).json()["data"]["consistent"] is True

    # turning it back off restores the guard
    await client_client.patch("/api/v1/settings/company", json={
        "allow_negative_stock": False,
    })
    assert (await _move(client_client, p, wh, "issue", 1)).status_code == 409


async def test_stock_is_tracked_per_warehouse(client_client):
    p = await _product(client_client, "SKU-004")
    main = await _main_wh(client_client)
    annex = await _warehouse(client_client, "WH2", "Annex")

    await _move(client_client, p, main, "receipt", 10)
    # stock in Main does not fund an issue from the Annex
    res = await _move(client_client, p, annex, "issue", 1)
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "INSUFFICIENT_STOCK"


# --- acceptance #3: balanced transfers ---------------------------------------

async def test_transfer_moves_qty_with_a_balanced_pair(client_client):
    p = await _product(client_client, "SKU-005")
    main = await _main_wh(client_client)
    annex = await _warehouse(client_client, "WH3", "Annex 3")
    await _move(client_client, p, main, "receipt", 40)

    res = await client_client.post("/api/v1/inventory/transfers", json={
        "product_id": p["id"], "from_warehouse_id": main["id"],
        "to_warehouse_id": annex["id"], "qty": 15, "note": "rebalance",
    })
    assert res.status_code == 201, res.text

    assert await _on_hand(client_client, p, main) == 25
    assert await _on_hand(client_client, p, annex) == 15

    # a balanced pair: the two entries net to zero and reference each other
    res = await client_client.get("/api/v1/inventory/movements", params={
        "product_id": p["id"], "type": "transfer"})
    pair = res.json()["data"]
    assert len(pair) == 2
    assert sum(m["qty"] for m in pair) == 0
    assert {m["qty"] for m in pair} == {15, -15}
    out = next(m for m in pair if m["qty"] == -15)
    into = next(m for m in pair if m["qty"] == 15)
    assert out["ref"]["doc_id"] == into["id"]
    assert into["ref"]["doc_id"] == out["id"]
    assert out["ref"]["module"] == "transfer"

    # total across warehouses is conserved
    assert (await client_client.get(
        "/api/v1/inventory/reconcile")).json()["data"]["consistent"] is True


async def test_transfer_beyond_on_hand_is_rejected_and_moves_nothing(client_client):
    p = await _product(client_client, "SKU-006")
    main = await _main_wh(client_client)
    annex = await _warehouse(client_client, "WH4", "Annex 4")
    await _move(client_client, p, main, "receipt", 5)

    res = await client_client.post("/api/v1/inventory/transfers", json={
        "product_id": p["id"], "from_warehouse_id": main["id"],
        "to_warehouse_id": annex["id"], "qty": 9,
    })
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "INSUFFICIENT_STOCK"

    # nothing left in limbo: source untouched, destination never created
    assert await _on_hand(client_client, p, main) == 5
    assert await _on_hand(client_client, p, annex) == 0
    res = await client_client.get("/api/v1/inventory/movements", params={
        "product_id": p["id"], "type": "transfer"})
    assert res.json()["meta"]["total"] == 0


async def test_transfer_to_the_same_warehouse_is_rejected(client_client):
    p = await _product(client_client, "SKU-007")
    main = await _main_wh(client_client)
    await _move(client_client, p, main, "receipt", 5)
    res = await client_client.post("/api/v1/inventory/transfers", json={
        "product_id": p["id"], "from_warehouse_id": main["id"],
        "to_warehouse_id": main["id"], "qty": 1,
    })
    assert res.status_code == 422


# --- acceptance #4: low-stock list -------------------------------------------

async def test_low_stock_matches_on_hand_at_or_below_reorder_point(client_client):
    wh = await _main_wh(client_client)
    low = await _product(client_client, "SKU-LOW", reorder_point=10, reorder_qty=50)
    at = await _product(client_client, "SKU-AT", reorder_point=10)
    high = await _product(client_client, "SKU-HIGH", reorder_point=10)

    await _move(client_client, low, wh, "receipt", 3)    # 3  <= 10 → low
    await _move(client_client, at, wh, "receipt", 10)    # 10 <= 10 → low (boundary)
    await _move(client_client, high, wh, "receipt", 40)  # 40 >  10 → not low

    res = await client_client.get("/api/v1/inventory/low-stock")
    assert res.status_code == 200
    rows = {r["sku"]: r for r in res.json()["data"]}
    assert set(rows) == {"SKU-LOW", "SKU-AT"}
    assert rows["SKU-LOW"]["on_hand"] == 3
    assert rows["SKU-LOW"]["reorder_point"] == 10
    assert rows["SKU-LOW"]["reorder_qty"] == 50


async def test_low_stock_ignores_products_with_no_reorder_policy(client_client):
    """reorder_point 0 means "not configured", not "always low" — otherwise every
    zero-stock item would be flagged forever."""
    wh = await _main_wh(client_client)
    p = await _product(client_client, "SKU-NOPOLICY")  # reorder_point defaults to 0
    await _move(client_client, p, wh, "receipt", 1)
    await _move(client_client, p, wh, "issue", 1)      # on_hand 0, 0 <= 0

    skus = {r["sku"] for r in (
        await client_client.get("/api/v1/inventory/low-stock")).json()["data"]}
    assert "SKU-NOPOLICY" not in skus


async def test_low_stock_ignores_inactive_products(client_client):
    wh = await _main_wh(client_client)
    p = await _product(client_client, "SKU-GONE", reorder_point=10)
    await _move(client_client, p, wh, "receipt", 1)
    assert "SKU-GONE" in {r["sku"] for r in (
        await client_client.get("/api/v1/inventory/low-stock")).json()["data"]}

    await client_client.patch(f"/api/v1/inventory/products/{p['id']}",
                              json={"is_active": False})
    assert "SKU-GONE" not in {r["sku"] for r in (
        await client_client.get("/api/v1/inventory/low-stock")).json()["data"]}


async def test_low_stock_list_and_dashboard_kpi_agree(client_client):
    """The KPI delegates to the same predicate as the list; if they ever drifted
    the dashboard would contradict the module."""
    wh = await _main_wh(client_client)
    for i, (point, qty) in enumerate([(10, 2), (10, 99), (0, 0), (5, 5)]):
        p = await _product(client_client, f"SKU-AGREE-{i}", reorder_point=point)
        if qty:
            await _move(client_client, p, wh, "receipt", qty)

    listed = (await client_client.get("/api/v1/inventory/low-stock")).json()["data"]
    kpis = (await client_client.get("/api/v1/dashboard/kpis")).json()["data"]
    assert kpis["low_stock_items"] == len(listed) == 2  # AGREE-0 and AGREE-3


# --- products / warehouses ---------------------------------------------------

async def test_duplicate_sku_is_rejected(client_client):
    await _product(client_client, "SKU-DUP")
    res = await client_client.post("/api/v1/inventory/products", json={
        "sku": "SKU-DUP", "name": "Clash",
    })
    assert res.status_code == 409


async def test_product_with_stock_cannot_be_deleted(client_client):
    p = await _product(client_client, "SKU-HELD")
    wh = await _main_wh(client_client)
    await _move(client_client, p, wh, "receipt", 4)

    res = await client_client.delete(f"/api/v1/inventory/products/{p['id']}")
    assert res.status_code == 409
    assert res.json()["error"]["details"]["on_hand"] == 4

    await _move(client_client, p, wh, "issue", 4)
    assert (await client_client.delete(
        f"/api/v1/inventory/products/{p['id']}")).status_code == 200


async def test_warehouse_holding_stock_cannot_be_deleted(client_client):
    p = await _product(client_client, "SKU-WH")
    wh = await _warehouse(client_client, "WH9", "Doomed")
    await _move(client_client, p, wh, "receipt", 2)
    assert (await client_client.delete(
        f"/api/v1/inventory/warehouses/{wh['id']}")).status_code == 409


async def test_movement_needs_a_live_product_and_warehouse(client_client):
    wh = await _main_wh(client_client)
    res = await client_client.post("/api/v1/inventory/movements", json={
        "product_id": "6a57fc000ea6cf67cc8c211a", "warehouse_id": wh["id"],
        "type": "receipt", "qty": 1,
    })
    assert res.status_code == 404


# --- RBAC --------------------------------------------------------------------

async def _limited_client(client, client_client, onboarded_company, perms, who):
    res = await client_client.post("/api/v1/settings/roles", json={
        "name": f"role-{who}", "permissions": perms,
    })
    role_id = res.json()["data"]["id"]
    email = f"{who}@{onboarded_company['slug']}.com"
    res = await client_client.post("/api/v1/settings/employees", json={
        "name": who, "email": email, "role_id": role_id,
    })
    temp_pw = res.json()["data"]["temp_password"]
    login = {"company": onboarded_company["slug"], "email": email}
    first = await client.post("/api/v1/auth/login", json={**login, "password": temp_pw})
    headers = {"Authorization": f"Bearer {first.json()['data']['access_token']}"}
    await client.post("/api/v1/auth/change-password", headers=headers, json={
        "current_password": temp_pw, "new_password": "LimitedPass1!",
    })
    res = await client.post("/api/v1/auth/login",
                            json={**login, "password": "LimitedPass1!"})
    return {"Authorization": f"Bearer {res.json()['data']['access_token']}"}


@pytest.mark.parametrize("path", [
    "/api/v1/inventory/products", "/api/v1/inventory/warehouses",
    "/api/v1/inventory/movements", "/api/v1/inventory/stock-levels",
    "/api/v1/inventory/low-stock",
])
async def test_inventory_none_is_denied(
    client, client_client, onboarded_company, path
):
    headers = await _limited_client(
        client, client_client, onboarded_company, {"dashboard": 2}, "noinv",
    )
    res = await client.get(path, headers=headers)
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "PERMISSION_DENIED"


async def test_inventory_read_cannot_post_movements(
    client, client_client, onboarded_company
):
    headers = await _limited_client(
        client, client_client, onboarded_company,
        {"dashboard": 2, "inventory": 2}, "readinv",
    )
    assert (await client.get(
        "/api/v1/inventory/products", headers=headers)).status_code == 200
    res = await client.post("/api/v1/inventory/movements", headers=headers, json={
        "product_id": "6a57fc000ea6cf67cc8c211a",
        "warehouse_id": "6a57fc000ea6cf67cc8c211b",
        "type": "receipt", "qty": 1,
    })
    assert res.status_code == 403
