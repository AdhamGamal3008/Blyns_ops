"""Project Management payloads (docs/modules/PROJECT_MANAGEMENT.md §3)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

ProjectStatus = Literal["active", "on_hold", "completed", "archived", "cancelled"]
DeliverableKind = Literal["shop_drawing", "bom", "scan", "photo", "report", "certificate"]
ReportType = Literal[
    "missing_information", "issue", "change", "ncr", "capa", "rfi", "qa", "na"
]
ReportStatus = Literal["open", "in_progress", "resolved", "closed"]
CostType = Literal["labor", "material", "subcontractor", "machine"]


class Milestone(BaseModel):
    key: str = Field(min_length=1)
    name: str = Field(min_length=1)
    due_date: datetime


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1)
    scope: str | None = None
    crm_account_id: str | None = None  # §1: stage 1 links to a CRM account
    pm_id: str | None = None
    team_ids: list[str] = Field(default_factory=list)
    milestone_schedule: list[Milestone] = Field(default_factory=list)
    planned_budget: float = Field(default=0, ge=0)
    currency: str = Field(default="USD", min_length=3, max_length=3)


class ProjectPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1)
    scope: str | None = None
    crm_account_id: str | None = None
    pm_id: str | None = None
    team_ids: list[str] | None = None
    milestone_schedule: list[Milestone] | None = None
    planned_budget: float | None = Field(default=None, ge=0)
    status: ProjectStatus | None = None


class DocumentSupply(BaseModel):
    """Satisfy a `document` entry gate — §4: waiting → in_progress once supplied."""

    deliverable_id: str | None = None
    note: str | None = None


class GateResultCreate(BaseModel):
    """§3.5 — a physical measurement or inspection result.

    `readings` for a measurement, `checklist_results` for an inspection. The
    engine evaluates against the seeded gate_rules threshold; a caller never
    declares `passed` itself.
    """

    readings: list[dict[str, Any]] = Field(default_factory=list)
    checklist_results: list[dict[str, Any]] = Field(default_factory=list)
    notes: str | None = None


class SubmitBody(BaseModel):
    note: str | None = None


class ApproveBody(BaseModel):
    comment: str | None = None


class RejectBody(BaseModel):
    comment: str = Field(min_length=1)  # §5.5 a rejection must say why
    report_type: ReportType | None = None  # defaults to the stage's recovery type
    owner_id: str | None = None


class DeliverableCreate(BaseModel):
    kind: DeliverableKind
    title: str = Field(min_length=1)
    stage_key: str | None = None
    file_ref: str = Field(min_length=1)
    note: str | None = None
    classification: Literal["auto", "manual"] = "manual"
    ocr_text: str | None = None


class RevisionCreate(BaseModel):
    file_ref: str = Field(min_length=1)
    note: str | None = None


class ReportCreate(BaseModel):
    type: ReportType
    title: str = Field(min_length=1)
    details: dict[str, Any] = Field(default_factory=dict)
    owner_id: str | None = None
    stage_instance_id: str | None = None


class ReportPatch(BaseModel):
    status: ReportStatus | None = None
    title: str | None = Field(default=None, min_length=1)
    details: dict[str, Any] | None = None
    owner_id: str | None = None


class JobCostCreate(BaseModel):
    """§3.9 — labor/material actuals captured by PM and posted to Finance."""

    stage_key: str | None = None
    cost_type: CostType
    description: str | None = None
    hours: float = Field(default=0, ge=0)
    quantity: float = Field(default=0, ge=0)
    unit_cost: float = Field(default=0, ge=0)
    post_to_finance: bool = True


class StageConfigPatch(BaseModel):
    """§12 /config/stages — tenant-editable stage template."""

    name: str | None = Field(default=None, min_length=1)
    approver_role: str | None = None
    is_active: bool | None = None
    automated_tasks: list[str] | None = None


class GateConfigPatch(BaseModel):
    """§8 — thresholds are seeded defaults, editable per tenant."""

    threshold: dict[str, Any] | None = None
    severe_threshold: dict[str, Any] | None = None
    blocking: bool | None = None
    checklist: list[str] | None = None
