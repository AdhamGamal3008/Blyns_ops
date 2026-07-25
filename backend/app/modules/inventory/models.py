"""Inventory module payloads (docs/modules/INVENTORY.md §1)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

Unit = Literal["pcs", "kg", "box"]
UNITS: tuple[str, ...] = ("pcs", "kg", "box")
DirectMovementType = Literal["receipt", "issue", "adjustment"]
# Every type that can appear in the ledger. `transfer` is written only by
# create_transfer, as a balanced pair — it is filterable and exportable, but
# never something a single row can post on its own.
MOVEMENT_TYPES: tuple[str, ...] = ("receipt", "issue", "transfer", "adjustment")
# INVENTORY.md §1 lists finance|manual|transfer, but PROJECT_MANAGEMENT.md §1
# has PM reserve/consume stock "via Inventory movements" — so a movement must be
# able to name `projects` as its origin.
RefModule = Literal["finance", "manual", "transfer", "projects"]


class ProductCreate(BaseModel):
    sku: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1)
    description: str | None = None
    category: str | None = None
    unit: Unit = "pcs"
    barcode: str | None = None
    cost_price: float = Field(default=0, ge=0)
    sale_price: float = Field(default=0, ge=0)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    reorder_point: float = Field(default=0, ge=0)
    reorder_qty: float = Field(default=0, ge=0)
    is_active: bool = True


class ProductPatch(BaseModel):
    sku: str | None = Field(default=None, min_length=1, max_length=64)
    name: str | None = Field(default=None, min_length=1)
    description: str | None = None
    category: str | None = None
    unit: Unit | None = None
    barcode: str | None = None
    cost_price: float | None = Field(default=None, ge=0)
    sale_price: float | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    reorder_point: float | None = Field(default=None, ge=0)
    reorder_qty: float | None = Field(default=None, ge=0)
    is_active: bool | None = None


class WarehouseCreate(BaseModel):
    name: str = Field(min_length=1)
    code: str = Field(min_length=1, max_length=16)
    address: dict | None = None
    is_active: bool = True


class WarehousePatch(BaseModel):
    name: str | None = Field(default=None, min_length=1)
    code: str | None = Field(default=None, min_length=1, max_length=16)
    address: dict | None = None
    is_active: bool | None = None


class MovementCreate(BaseModel):
    """A direct ledger entry (§3 POST /movements).

    `qty` is always supplied POSITIVE; the service applies the sign from `type`
    (+receipt, -issue) so a caller can't post an issue that secretly adds stock.
    An `adjustment` is the one type that takes a signed qty, since it corrects
    a discrepancy in either direction — and it requires a note (§2).
    """

    product_id: str
    warehouse_id: str
    type: DirectMovementType
    qty: float
    note: str | None = None
    occurred_at: datetime | None = None
    ref_module: RefModule = "manual"
    ref_doc_id: str | None = None


class TransferCreate(BaseModel):
    """§3 POST /transfers — one paired issue+receipt across two warehouses."""

    product_id: str
    from_warehouse_id: str
    to_warehouse_id: str
    qty: float = Field(gt=0)
    note: str | None = None
    occurred_at: datetime | None = None
