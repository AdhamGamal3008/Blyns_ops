"""Production module request/response models (docs/PRODUCTION_MODULE_PLAN.md §3, §6).

Phase 1: the Work Order + its generation from a project BOM. A WO is proposed
(computed, not persisted) and then confirmed by the production_manager (D4) — the
propose payload round-trips into the confirm payload so the manager can review and
trim the drafts before they are created.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class ProposeRequest(BaseModel):
    project_id: str = Field(min_length=1)


class WorkOrderLine(BaseModel):
    """A BOM line, resolved against Inventory so the WO snapshot is self-contained
    (plan §3). Cost is deliberately never carried here (plan D3)."""

    product_id: str = Field(min_length=1)
    sku: str | None = None
    description: str | None = None
    qty: float = Field(gt=0)
    uom: str | None = None


class SourceDrawing(BaseModel):
    """The shop-drawing revision a WO is pinned to — never 'latest' (plan §2.1)."""

    deliverable_id: str = Field(min_length=1)
    title: str | None = None
    version: int = Field(ge=1)


class WorkOrderInput(BaseModel):
    """One WO to create — the shape `propose` returns and `confirm` accepts."""

    project_id: str = Field(min_length=1)
    item_name: str = Field(min_length=1)
    source_drawing: SourceDrawing | None = None
    bom_lines: list[WorkOrderLine] = Field(default_factory=list)
    qty_ordered: float = Field(gt=0)
    station_id: str | None = None
    due_date: datetime | None = None


class WorkOrderConfirm(BaseModel):
    """The reviewed set the manager commits (D4)."""

    work_orders: list[WorkOrderInput] = Field(min_length=1)
