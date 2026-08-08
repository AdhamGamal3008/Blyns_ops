"""Inventory Analytics/Overview endpoint (docs/PROJECT_ANALYTICS_PLAN.md §6-D).

Seeds products + stock levels + movements (the exact shapes the service writes)
and asserts every KPI and chart, plus the RBAC tiering.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from bson import ObjectId

from app.core.db import get_db_manager


def _tenant_db(onboarded_company):
    return get_db_manager().tenant(onboarded_company["company"]["db_name"])


async def _seed(db) -> None:
    now = datetime.now(UTC)
    p1, p2, p3, p4, p5 = (ObjectId() for _ in range(5))
    w1, w2 = ObjectId(), ObjectId()

    def product(_id, sku, name, category, cost, reorder, active=True, deleted=False):
        return {
            "_id": _id, "sku": sku, "name": name, "category": category,
            "cost_price": cost, "reorder_point": reorder,
            "is_active": active, "is_deleted": deleted,
        }

    await db.products.insert_many([
        product(p1, "PA", "Widget", "Hardware", 10.0, 5),
        product(p2, "PB", "Gadget", "Hardware", 20.0, 10),
        product(p3, "PC", "Gizmo", "Tools", 50.0, 4),
        product(p4, "PD", "OldThing", "Tools", 5.0, 3, active=False),   # excluded
        product(p5, "PE", "Deleted", "Ghost", 100.0, 3, deleted=True),  # excluded
    ])

    def level(pid, wid, on_hand):
        return {"product_id": pid, "warehouse_id": wid, "on_hand": on_hand}

    await db.stock_levels.insert_many([
        level(p1, w1, 3.0),   # low  (value 30)
        level(p1, w2, 2.0),   # low  (value 20) → p1 total 50 across 2 warehouses
        level(p2, w1, 0.0),   # out  (value 0)
        level(p3, w1, 20.0),  # healthy (value 1000)
        level(p4, w1, 99.0),  # excluded — inactive product
        level(p5, w1, 99.0),  # excluded — deleted product
    ])

    def move(pid, mtype, qty, days):
        return {"product_id": pid, "warehouse_id": w1, "type": mtype, "qty": qty,
                "occurred_at": now - timedelta(days=days)}

    await db.movements.insert_many([
        move(p1, "receipt", 10.0, 20),
        move(p1, "issue", -4.0, 10),   # issues post negative qty
        move(p3, "receipt", 5.0, 5),
    ])


async def test_inventory_analytics_kpis_and_charts(client_client, onboarded_company):
    await _seed(_tenant_db(onboarded_company))

    res = await client_client.get("/api/v1/inventory/analytics")
    assert res.status_code == 200, res.text
    data = res.json()["data"]

    k = data["kpis"]
    assert k["active_skus"] == 3                # p4 inactive, p5 deleted excluded
    assert k["stock_value"] == 1050.0           # Tools 1000 + Hardware 50
    assert k["low_stock"] == 3                   # 2 low lines + 1 out
    assert k["out_of_stock"] == 1               # p2 @ w1
    assert k["categories"] == 2                  # Hardware, Tools

    by_cat = {r["category"]: r["value"] for r in data["value_by_category"]}
    assert by_cat == {"Tools": 1000.0, "Hardware": 50.0}
    assert data["value_by_category"][0]["category"] == "Tools"  # biggest first

    status = {r["status"]: r["count"] for r in data["stock_status"]}
    assert status == {"Out of stock": 1, "Low": 2, "Healthy": 1}

    assert data["top_products"][0]["name"] == "Gizmo"
    assert data["top_products"][0]["value"] == 1000.0

    low = data["low_stock_items"]
    assert len(low) == 3                         # p2, p1@w2, p1@w1
    assert low[0]["on_hand"] == 0.0 and low[0]["reorder"] == 10.0  # most urgent

    assert len(data["movements"]) == 6
    assert sum(m["received"] for m in data["movements"]) == 15.0   # 10 + 5
    assert sum(m["issued"] for m in data["movements"]) == 4.0      # −(−4)


async def _set_owner_inv_analytics(db, level: int) -> None:
    await db.roles.update_one(
        {"name": "Owner"}, {"$set": {"permissions.inventory_analytics": level}}
    )


async def test_inventory_analytics_rbac_tiers(client_client, onboarded_company):
    db = _tenant_db(onboarded_company)
    await _seed(db)

    res = await client_client.get("/api/v1/inventory/analytics")  # Owner WRITE → full
    assert res.status_code == 200
    assert "value_by_category" in res.json()["data"]

    await _set_owner_inv_analytics(db, 1)  # VIEW → KPIs only
    data = (await client_client.get("/api/v1/inventory/analytics")).json()["data"]
    assert set(data) == {"kpis"}

    await _set_owner_inv_analytics(db, 0)  # NONE → 403
    assert (await client_client.get("/api/v1/inventory/analytics")).status_code == 403
