"""Inventory Analytics / Overview (docs/PROJECT_ANALYTICS_PLAN.md §6-D).

Same role-tiered contract as the other modules: VIEW = headline KPI row, READ =
+ chart blocks, absent-not-null below READ. Reads are not audited; every
aggregation filters soft-deletes (and only active products count).
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.modules.inventory import repository as repo
from app.shared.enums import Level
from app.shared.timebuckets import month_buckets, window_start
from app.tenant.deps import ClientPrincipal

RESOURCE = "inventory_analytics"

TOP_PRODUCTS = 8
LOW_STOCK_TOP = 8
MOVEMENT_MONTHS = 6


# --- KPI row (VIEW+) ----------------------------------------------------------

async def _kpis(db) -> dict:
    by_cat = await repo.analytics_value_by_category(db)
    status = await repo.analytics_stock_status(db)
    out, low = status.get("out", 0), status.get("low", 0)
    return {
        "active_skus": await repo.analytics_active_products(db),
        "stock_value": sum(c["value"] for c in by_cat),
        "low_stock": out + low,        # on_hand ≤ reorder (includes out-of-stock)
        "out_of_stock": out,
        "categories": await repo.analytics_categories(db),
    }


# --- chart blocks (READ) ------------------------------------------------------

async def _charts(db) -> dict:
    now = datetime.now(UTC)
    status = await repo.analytics_stock_status(db)
    stock_status = [
        {"status": "Out of stock", "count": status.get("out", 0)},
        {"status": "Low", "count": status.get("low", 0)},
        {"status": "Healthy", "count": status.get("healthy", 0)},
    ]

    monthly = await repo.analytics_movements_monthly(db, window_start(now, MOVEMENT_MONTHS))
    movements = []
    for m in month_buckets(now, MOVEMENT_MONTHS):
        by_type = monthly.get(m, {})
        movements.append({
            "month": m,
            "received": by_type.get("receipt", 0.0),   # receipts post +qty
            "issued": -by_type.get("issue", 0.0),       # issues post −qty → flip
        })

    return {
        "value_by_category": await repo.analytics_value_by_category(db),
        "low_stock_items": await repo.analytics_low_stock_top(db, LOW_STOCK_TOP),
        "top_products": await repo.analytics_top_products_by_value(db, TOP_PRODUCTS),
        "movements": movements,
        "stock_status": stock_status,
    }


# --- entry point --------------------------------------------------------------

async def overview(principal: ClientPrincipal) -> dict:
    db = principal.tenant_db
    out: dict = {"kpis": await _kpis(db)}
    if principal.level_for(RESOURCE) >= Level.READ:
        out.update(await _charts(db))
    return out
