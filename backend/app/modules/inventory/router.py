"""Inventory API (docs/modules/INVENTORY.md §3).

GET → inventory READ; products/warehouses/movements changes → inventory WRITE.
There is deliberately no PATCH/DELETE for movements: the ledger is immutable
(§2), and corrections are posted as new `adjustment` entries.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.modules.inventory import service
from app.modules.inventory.csv_schema import ENTITIES as CSV_ENTITIES
from app.modules.inventory.models import (
    MovementCreate,
    ProductCreate,
    ProductPatch,
    TransferCreate,
    WarehouseCreate,
    WarehousePatch,
)
from app.shared.csv_router import csv_routes
from app.shared.enums import Level
from app.shared.schemas import PaginationParams, envelope, page_meta, to_api
from app.tenant.deps import ClientPrincipal, require

router = APIRouter(prefix="/api/v1/inventory", tags=["client-inventory"])

_read = require("inventory", Level.READ)
_write = require("inventory", Level.WRITE)


# --- products ----------------------------------------------------------------

@router.get("/products")
async def list_products(
    page: PaginationParams = Depends(),
    q: str | None = None,
    category: str | None = None,
    is_active: bool | None = None,
    principal: ClientPrincipal = Depends(_read),
):
    docs, total = await service.list_products(
        principal, q, category, is_active, page.skip, page.page_size
    )
    return envelope(to_api(docs), page_meta(page.page, page.page_size, total))


@router.post("/products", status_code=201)
async def create_product(
    body: ProductCreate, principal: ClientPrincipal = Depends(_write)
):
    return envelope(to_api(await service.create_product(principal, body)))


@router.patch("/products/{product_id}")
async def patch_product(
    product_id: str, body: ProductPatch, principal: ClientPrincipal = Depends(_write)
):
    return envelope(to_api(await service.patch_product(principal, product_id, body)))


@router.delete("/products/{product_id}")
async def delete_product(product_id: str, principal: ClientPrincipal = Depends(_write)):
    await service.delete_product(principal, product_id)
    return envelope({"deleted": True})


# --- warehouses --------------------------------------------------------------

@router.get("/warehouses")
async def list_warehouses(
    page: PaginationParams = Depends(),
    principal: ClientPrincipal = Depends(_read),
):
    docs, total = await service.list_warehouses(principal, page.skip, page.page_size)
    return envelope(to_api(docs), page_meta(page.page, page.page_size, total))


@router.post("/warehouses", status_code=201)
async def create_warehouse(
    body: WarehouseCreate, principal: ClientPrincipal = Depends(_write)
):
    return envelope(to_api(await service.create_warehouse(principal, body)))


@router.patch("/warehouses/{warehouse_id}")
async def patch_warehouse(
    warehouse_id: str, body: WarehousePatch,
    principal: ClientPrincipal = Depends(_write),
):
    return envelope(to_api(await service.patch_warehouse(principal, warehouse_id, body)))


@router.delete("/warehouses/{warehouse_id}")
async def delete_warehouse(
    warehouse_id: str, principal: ClientPrincipal = Depends(_write)
):
    await service.delete_warehouse(principal, warehouse_id)
    return envelope({"deleted": True})


# --- movements (immutable ledger) --------------------------------------------

@router.get("/movements")
async def list_movements(
    page: PaginationParams = Depends(),
    product_id: str | None = None,
    warehouse_id: str | None = None,
    type: str | None = None,
    principal: ClientPrincipal = Depends(_read),
):
    docs, total = await service.list_movements(
        principal, product_id, warehouse_id, type, page.skip, page.page_size
    )
    return envelope(to_api(docs), page_meta(page.page, page.page_size, total))


@router.post("/movements", status_code=201)
async def create_movement(
    body: MovementCreate, principal: ClientPrincipal = Depends(_write)
):
    return envelope(to_api(await service.create_movement(principal, body)))


@router.post("/transfers", status_code=201)
async def create_transfer(
    body: TransferCreate, principal: ClientPrincipal = Depends(_write)
):
    return envelope(to_api(await service.create_transfer(principal, body)))


# --- stock views -------------------------------------------------------------

@router.get("/stock-levels")
async def list_stock_levels(
    page: PaginationParams = Depends(),
    product_id: str | None = None,
    warehouse_id: str | None = None,
    principal: ClientPrincipal = Depends(_read),
):
    docs, total = await service.list_stock_levels(
        principal, product_id, warehouse_id, page.skip, page.page_size
    )
    return envelope(to_api(docs), page_meta(page.page, page.page_size, total))


@router.get("/low-stock")
async def list_low_stock(principal: ClientPrincipal = Depends(_read)):
    return envelope(await service.list_low_stock(principal))


@router.get("/reconcile")
async def reconcile(principal: ClientPrincipal = Depends(_read)):
    """Integrity check: cached on_hand vs. the movement ledger (§2)."""
    return envelope(await service.reconcile(principal))


# --- CSV import & export (§7) ------------------------------------------------
#
# `{entity}` is one of products | warehouses | movements | stock-levels, served
# by the same shared engine CRM uses. Two data sets behave differently, and the
# difference is enforced in csv_schema.py, not here: a movement row is posted
# through create_movement (so it claims stock and can be refused), and stock
# levels are export-only because they are derived from the ledger.

csv_routes(router, module="inventory", registry=CSV_ENTITIES)
