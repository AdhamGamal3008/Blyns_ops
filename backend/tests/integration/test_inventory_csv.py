"""Inventory CSV import & export (docs/modules/INVENTORY.md §7).

The load-bearing property is that a spreadsheet cannot corrupt the ledger:
importing movements goes through the same service the API uses, so on-hand
still equals the signed sum of the ledger (acceptance #1) and an issue beyond
stock is still refused. Stock levels are derived and must not be importable at
all.
"""

from __future__ import annotations

import csv
import io

from app.modules.inventory import csv_schema
from tests.integration.test_crm import _limited_client

BOM = "﻿"


def _table(text: str) -> list[list[str]]:
    return list(csv.reader(io.StringIO(text.lstrip(BOM), newline="")))


def _csv(*rows: list[str]) -> str:
    out = io.StringIO()
    csv.writer(out, lineterminator="\r\n").writerows(rows)
    return out.getvalue()


async def _upload(client_client, entity: str, text: str, *, mode: str = "validate",
                  name: str = "import.csv"):
    return await client_client.post(
        f"/api/v1/inventory/import/{entity}",
        params={"mode": mode},
        files={"file": (name, text.encode("utf-8"), "text/csv")},
    )


async def _commit(client_client, entity: str, text: str, **kw) -> dict:
    res = await _upload(client_client, entity, text, mode="commit", **kw)
    assert res.status_code == 200, res.text
    return res.json()["data"]


async def _product(client_client, sku: str, **extra) -> dict:
    res = await client_client.post("/api/v1/inventory/products", json={
        "sku": sku, "name": extra.pop("name", f"Product {sku}"), **extra,
    })
    assert res.status_code == 201, res.text
    return res.json()["data"]


async def _warehouse(client_client, code: str, name: str | None = None) -> dict:
    res = await client_client.post("/api/v1/inventory/warehouses", json={
        "code": code, "name": name or f"Warehouse {code}",
    })
    assert res.status_code == 201, res.text
    return res.json()["data"]


async def _on_hand(client_client, product_id: str) -> float:
    res = await client_client.get("/api/v1/inventory/stock-levels",
                                  params={"product_id": product_id})
    rows = res.json()["data"]
    return sum(float(r["on_hand"]) for r in rows)


# --- templates ---------------------------------------------------------------

async def test_templates_match_the_importable_columns(client_client):
    for name, entity in csv_schema.ENTITIES.items():
        res = await client_client.get(f"/api/v1/inventory/import/{name}/template")
        if not entity.can_import:
            continue
        assert res.status_code == 200, res.text
        assert _table(res.text)[0] == [f.header for f in entity.importable_fields]


async def test_products_and_warehouses_import_and_round_trip(client_client):
    text = _csv(
        ["SKU", "Name", "Category", "Unit", "Cost price", "Reorder point", "Active"],
        ["CSV-001", "Oak plank", "Timber", "pcs", "12.5", "20", "yes"],
        ["CSV-002", "Pine plank", "Timber", "pcs", "8", "0", "no"],
    )
    report = await _commit(client_client, "products", text)
    assert (report["created"], report["updated"], report["failed"]) == (2, 0, 0)

    res = await client_client.get("/api/v1/inventory/products", params={"q": "CSV-001"})
    product = res.json()["data"][0]
    assert product["name"] == "Oak plank"
    assert product["cost_price"] == 12.5
    assert product["reorder_point"] == 20
    assert product["is_active"] is True

    # exporting and re-importing changes nothing and duplicates nothing
    exported = (await client_client.get("/api/v1/inventory/export/products")).text
    report = await _commit(client_client, "products", exported)
    assert report["created"] == 0
    assert report["failed"] == 0
    res = await client_client.get("/api/v1/inventory/products", params={"q": "CSV-00"})
    assert res.json()["meta"]["total"] == 2


async def test_sku_matching_is_case_sensitive(client_client):
    """A SKU is an exact identifier with a unique index. Folding case here would
    let `sku-001` silently rename `SKU-001` on the next import."""
    await _commit(client_client, "products",
                  _csv(["SKU", "Name"], ["CASE-1", "Original"]))
    report = await _commit(client_client, "products",
                           _csv(["SKU", "Name"], ["case-1", "Different item"]))
    assert (report["created"], report["updated"]) == (1, 0)

    res = await client_client.get("/api/v1/inventory/products", params={"q": "CASE-1"})
    assert res.json()["data"][0]["name"] == "Original"


async def test_warehouses_import_with_a_nested_address(client_client):
    text = _csv(["Code", "Name", "Address", "City"],
                ["CSVWH", "CSV Depot", "1 Dock Road", "Springfield"])
    assert (await _commit(client_client, "warehouses", text))["created"] == 1

    res = await client_client.get("/api/v1/inventory/warehouses")
    wh = next(w for w in res.json()["data"] if w["code"] == "CSVWH")
    assert wh["address"] == {"street": "1 Dock Road", "city": "Springfield"}


# --- movements: the ledger keeps its invariants ------------------------------

async def test_importing_movements_moves_stock_through_the_service(
    client_client, onboarded_company
):
    """Acceptance #1 must still hold after a CSV import: the cached on-hand
    equals the signed sum of the ledger. A raw insert would break exactly this."""
    product = await _product(client_client, "MOV-001")
    await _warehouse(client_client, "MVWH")

    text = _csv(
        ["SKU", "Warehouse", "Type", "Qty", "Note"],
        ["MOV-001", "MVWH", "receipt", "100", "Opening balance"],
        ["MOV-001", "MVWH", "issue", "30", "First job"],
        ["MOV-001", "MVWH", "adjustment", "-5", "Damaged in transit"],
    )
    report = await _commit(client_client, "movements", text)
    assert (report["created"], report["failed"]) == (3, 0)

    assert await _on_hand(client_client, product["id"]) == 65  # 100 - 30 - 5

    # the ledger and the cache agree — the module's own integrity check
    res = await client_client.get("/api/v1/inventory/reconcile")
    assert res.json()["data"]["consistent"] is True
    assert res.json()["data"]["drift"] == []


async def test_movements_are_append_only(client_client):
    """§2: the ledger is immutable. Importing the same file twice means the
    movements happened twice — it must never be read as an update."""
    await _product(client_client, "APP-001")
    await _warehouse(client_client, "APWH")
    text = _csv(["SKU", "Warehouse", "Type", "Qty"], ["APP-001", "APWH", "receipt", "10"])

    first = await _commit(client_client, "movements", text)
    second = await _commit(client_client, "movements", text)
    assert first["created"] == second["created"] == 1
    assert second["updated"] == 0

    res = await client_client.get("/api/v1/inventory/movements")
    assert res.json()["meta"]["total"] == 2


async def test_an_issue_beyond_stock_is_refused_and_the_rest_still_lands(
    client_client
):
    """The negative-stock guard is not bypassable by CSV. The failing row is
    reported; the good rows still post."""
    product = await _product(client_client, "SHORT-1")
    await _warehouse(client_client, "SHWH")

    text = _csv(
        ["SKU", "Warehouse", "Type", "Qty"],
        ["SHORT-1", "SHWH", "receipt", "10"],
        ["SHORT-1", "SHWH", "issue", "999"],   # far more than on hand
        ["SHORT-1", "SHWH", "receipt", "5"],
    )
    report = await _commit(client_client, "movements", text)
    assert report["created"] == 2
    assert report["failed"] == 1
    assert report["errors"][0]["row"] == 3
    assert "on hand" in report["errors"][0]["message"]

    assert await _on_hand(client_client, product["id"]) == 15
    assert (await client_client.get(
        "/api/v1/inventory/reconcile")).json()["data"]["consistent"] is True


async def test_movement_rows_obey_the_same_rules_as_the_api(client_client):
    await _product(client_client, "RULE-1")
    await _warehouse(client_client, "RLWH")

    text = _csv(
        ["SKU", "Warehouse", "Type", "Qty", "Note"],
        ["RULE-1", "RLWH", "adjustment", "5", ""],       # adjustment needs a note
        ["RULE-1", "RLWH", "receipt", "-5", ""],         # direction comes from type
        ["RULE-1", "RLWH", "receipt", "0", ""],          # zero is not a movement
        ["NOPE-9", "RLWH", "receipt", "5", ""],          # unknown SKU
        ["RULE-1", "NOWH", "receipt", "5", ""],          # unknown warehouse
        ["RULE-1", "RLWH", "transfer", "5", ""],         # pairs only, via the app
    )
    report = await _upload(client_client, "movements", text)
    data = report.json()["data"]
    assert data["created"] == 0
    assert data["failed"] == 6

    messages = {e["row"]: e["message"] for e in data["errors"]}
    assert "requires a note" in messages[2]
    assert "positive qty" in messages[3]
    assert "cannot be zero" in messages[4]
    assert "No product matches" in messages[5]
    assert "No warehouse matches" in messages[6]
    assert "receipt, issue, adjustment" in messages[7]


async def test_validate_mode_posts_no_movements(client_client):
    product = await _product(client_client, "DRY-1")
    await _warehouse(client_client, "DRWH")
    text = _csv(["SKU", "Warehouse", "Type", "Qty"], ["DRY-1", "DRWH", "receipt", "50"])

    res = await _upload(client_client, "movements", text, mode="validate")
    assert res.json()["data"]["created"] == 1
    assert await _on_hand(client_client, product["id"]) == 0


async def test_the_ledger_preview_counts_every_row_as_new(client_client):
    """Regression: an append-only entity has no natural key, and an empty tuple
    is not one — every row shared it, so the preview called the second row an
    'update' of the first. Commit was right; only the dry run lied."""
    await _product(client_client, "PREV-1")
    await _warehouse(client_client, "PVWH")
    text = _csv(
        ["SKU", "Warehouse", "Type", "Qty"],
        ["PREV-1", "PVWH", "receipt", "5"],
        ["PREV-1", "PVWH", "receipt", "6"],
        ["PREV-1", "PVWH", "receipt", "7"],
    )
    preview = (await _upload(client_client, "movements", text)).json()["data"]
    assert (preview["created"], preview["updated"]) == (3, 0)

    committed = await _commit(client_client, "movements", text)
    assert (committed["created"], committed["updated"]) == (3, 0)


async def test_movement_import_writes_one_activity_entry(client_client):
    await _product(client_client, "AUD-1")
    await _warehouse(client_client, "AUWH")
    await _commit(
        client_client, "movements",
        _csv(["SKU", "Warehouse", "Type", "Qty"],
             ["AUD-1", "AUWH", "receipt", "5"],
             ["AUD-1", "AUWH", "receipt", "6"]),
        name="stock-take.csv",
    )
    res = await client_client.get("/api/v1/activity", params={"module": "inventory"})
    entries = [a for a in res.json()["data"]
               if a["action"] == "inventory.import.completed"]
    assert len(entries) == 1
    assert entries[0]["details"]["created"] == 2
    assert entries[0]["details"]["file"] == "stock-take.csv"


# --- stock levels are derived ------------------------------------------------

async def test_stock_levels_cannot_be_imported(client_client):
    """§2: stock is derived from the ledger and never edited directly. Letting a
    CSV set on_hand would make the cache disagree with the movements."""
    res = await client_client.get("/api/v1/inventory/import/stock-levels/template")
    assert res.status_code == 422
    assert "derived" in res.json()["error"]["message"]

    res = await _upload(client_client, "stock-levels",
                        _csv(["SKU", "On hand"], ["X", "9999"]), mode="commit")
    assert res.status_code == 422


async def test_stock_levels_export_resolves_sku_and_warehouse(client_client):
    await _product(client_client, "LVL-1", name="Level product")
    await _warehouse(client_client, "LVWH")
    await _commit(client_client, "movements",
                  _csv(["SKU", "Warehouse", "Type", "Qty"],
                       ["LVL-1", "LVWH", "receipt", "42"]))

    res = await client_client.get("/api/v1/inventory/export/stock-levels")
    assert res.status_code == 200
    rows = _table(res.text)
    assert rows[0] == ["SKU", "Product", "Warehouse", "On hand", "Updated at"]
    row = next(r for r in rows[1:] if r[0] == "LVL-1")
    assert row[1] == "Level product"   # ids resolved to human values
    assert row[2] == "LVWH"
    assert row[3] == "42"

    res = await client_client.get("/api/v1/inventory/export/stock-levels/fields")
    assert res.json()["data"]["importable"] is False


# --- export ------------------------------------------------------------------

async def test_product_export_honours_columns_and_the_active_filter(client_client):
    await _product(client_client, "EXP-ON", name="Live item", is_active=True)
    await _product(client_client, "EXP-OFF", name="Retired item", is_active=False)

    res = await client_client.get("/api/v1/inventory/export/products",
                                  params={"fields": "sku,name", "status": "no"})
    rows = _table(res.text)
    assert rows[0] == ["SKU", "Name"]
    skus = [r[0] for r in rows[1:]]
    assert "EXP-OFF" in skus and "EXP-ON" not in skus

    res = await client_client.get("/api/v1/inventory/export/products",
                                  params={"status": "maybe"})
    assert res.status_code == 422


async def test_movement_export_resolves_references(client_client):
    await _product(client_client, "MEX-1")
    await _warehouse(client_client, "MEWH")
    await _commit(client_client, "movements",
                  _csv(["SKU", "Warehouse", "Type", "Qty", "Note"],
                       ["MEX-1", "MEWH", "receipt", "7", "Booked in"]))

    res = await client_client.get(
        "/api/v1/inventory/export/movements",
        params={"fields": "sku_ref,warehouse_code,type,qty,note"},
    )
    rows = _table(res.text)
    assert rows[0] == ["SKU", "Warehouse", "Type", "Qty", "Note"]
    row = next(r for r in rows[1:] if r[0] == "MEX-1")
    assert row[1] == "MEWH"
    assert row[2] == "receipt"
    assert row[3] == "7"
    assert row[4] == "Booked in"


async def test_unknown_inventory_data_set_is_404(client_client):
    res = await client_client.get("/api/v1/inventory/export/gadgets")
    assert res.status_code == 404
    assert "products" in res.json()["error"]["message"]


# --- RBAC --------------------------------------------------------------------

async def test_inventory_read_can_export_but_not_import(
    client, client_client, onboarded_company
):
    headers = await _limited_client(
        client, client_client, onboarded_company,
        {"dashboard": 2, "inventory": 2}, "invread",
    )
    assert (await client.get("/api/v1/inventory/export/products",
                             headers=headers)).status_code == 200
    res = await client.post(
        "/api/v1/inventory/import/products", headers=headers,
        files={"file": ("x.csv", _csv(["SKU", "Name"], ["X", "Y"]).encode(),
                        "text/csv")},
    )
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "PERMISSION_DENIED"


async def test_inventory_none_is_denied_on_every_csv_route(
    client, client_client, onboarded_company
):
    headers = await _limited_client(
        client, client_client, onboarded_company, {"dashboard": 2}, "invnone",
    )
    for path in (
        "/api/v1/inventory/export/products",
        "/api/v1/inventory/export/products/fields",
        "/api/v1/inventory/import/products/template",
    ):
        res = await client.get(path, headers=headers)
        assert res.status_code == 403, f"{path} → {res.status_code}"
