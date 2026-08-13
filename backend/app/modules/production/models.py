"""Production module request/response models (docs/PRODUCTION_MODULE_PLAN.md §3, §6).

Phase 1: the Work Order + its generation from a project BOM. A WO is proposed
(computed, not persisted) and then confirmed by the production_manager (D4) — the
propose payload round-trips into the confirm payload so the manager can review and
trim the drafts before they are created.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

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


# --- Phase 2 status transitions (§2.2) ---------------------------------------

class RequestQCInput(BaseModel):
    """Production complete → QC. Optionally capture labor for a job cost."""

    qty_done: float | None = Field(default=None, gt=0)
    labor_hours: float = Field(default=0, ge=0)
    labor_rate: float = Field(default=0, ge=0)


class QCResultInput(BaseModel):
    result: Literal["pass", "hold"]
    defects: list[str] = Field(default_factory=list)
    note: str | None = None


class ReworkInput(BaseModel):
    note: str | None = None


class ShortfallInput(BaseModel):
    note: str = Field(min_length=1)


class AllocateInput(BaseModel):
    station_id: str = Field(min_length=1)


# --- Phase 4 packing + dispatch (§2.2, §3) -----------------------------------

class PackInput(BaseModel):
    """Pack a passed WO. The protection spec defaults from the WO's material
    (plan §Phase 4); the floor may override the packing type and add labels or
    handling notes."""

    packing_type: str | None = None
    labels: list[str] = Field(default_factory=list)
    handling: list[str] = Field(default_factory=list)
    note: str | None = None


class StageInput(BaseModel):
    """Stage a packed WO for dispatch: confirm the delivery window — the schedule
    that clears `delivery_planning` (sync rule 5) — and optionally override the
    load-suggested vehicle. Generating the manifest + notifying site happen here."""

    delivery_window_start: datetime | None = None
    delivery_window_end: datetime | None = None
    vehicle: str | None = None
    note: str | None = None


class DispatchInput(BaseModel):
    """Record the physical dispatch — the truck leaves and the WO is done."""

    note: str | None = None
