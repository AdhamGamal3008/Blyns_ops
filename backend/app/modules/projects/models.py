"""Project Management payloads (docs/modules/PROJECT_MANAGEMENT.md §3)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

ProjectStatus = Literal["active", "on_hold", "completed", "archived", "cancelled"]
# Which stage machine a project runs: the classic linear 9-stage chain, or the
# concurrent template where stages 2-8 run in parallel (docs/CONCURRENT_WORKFLOW_PLAN.md).
WorkflowType = Literal["sequential", "concurrent"]
DeliverableKind = Literal["shop_drawing", "bom", "scan", "photo", "report", "certificate"]
# How a document's file is held: an uploaded file in GridFS, or an external URL.
DeliverableSource = Literal["upload", "url"]
ReportType = Literal[
    "missing_information", "issue", "change", "ncr", "capa", "rfi", "qa", "na"
]
ReportStatus = Literal["open", "in_progress", "resolved", "closed"]
CostType = Literal["labor", "material", "subcontractor", "machine"]


def _validate_source(source_type: str, file_id: str | None, file_ref: str | None) -> None:
    if source_type == "upload":
        if not file_id:
            raise ValueError("file_id is required when source_type is 'upload'")
    elif not (file_ref and file_ref.strip()):
        raise ValueError("file_ref (a URL) is required when source_type is 'url'")


class Milestone(BaseModel):
    key: str = Field(min_length=1)
    name: str = Field(min_length=1)
    due_date: datetime


class StageTarget(BaseModel):
    """A target date for reaching/clearing a stage — calendar `stage_due` (§14)."""

    stage_key: str = Field(min_length=1)
    due_date: datetime


class GateDeadline(BaseModel):
    """A deadline for a physical gate — calendar `gate_due` (§14)."""

    gate_key: str = Field(min_length=1)
    stage_key: str | None = None
    due_at: datetime


class ProjectSchedule(BaseModel):
    """Dated planning items the calendar surfaces beyond milestones (§14): stage
    target dates, the Stage-12 delivery date, the acclimation window (§8), and
    gate deadlines. All optional — a project may schedule as much or little as
    it wants."""

    delivery_date: datetime | None = None          # Stage 12 → `delivery`
    acclimation_start: datetime | None = None       # §8 window → `acclimation`
    acclimation_end: datetime | None = None
    stage_targets: list[StageTarget] = Field(default_factory=list)
    gate_deadlines: list[GateDeadline] = Field(default_factory=list)


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1)
    scope: str | None = None
    workflow_type: WorkflowType = "sequential"  # §1: chosen at creation (Stage 1)
    crm_account_id: str | None = None  # §1: stage 1 links to a CRM account
    pm_id: str | None = None
    team_ids: list[str] = Field(default_factory=list)
    milestone_schedule: list[Milestone] = Field(default_factory=list)
    schedule: ProjectSchedule | None = None
    planned_budget: float = Field(default=0, ge=0)
    currency: str = Field(default="USD", min_length=3, max_length=3)


class ProjectPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1)
    scope: str | None = None
    crm_account_id: str | None = None
    pm_id: str | None = None
    team_ids: list[str] | None = None
    milestone_schedule: list[Milestone] | None = None
    schedule: ProjectSchedule | None = None
    planned_budget: float | None = Field(default=None, ge=0)
    status: ProjectStatus | None = None


class DocumentSupply(BaseModel):
    """Satisfy a `document` entry gate — §4: waiting → in_progress once supplied."""

    deliverable_id: str | None = None
    note: str | None = None


class GateDocumentAttach(BaseModel):
    """Attach the evidence a `document` entry gate requires (§4) — an uploaded
    file or a URL — and satisfy the gate in one step.

    There is deliberately no `kind` and no `stage_key`: the gate itself says what
    is required and which stage it belongs to, so asking would be redundant.
    """

    source_type: DeliverableSource = "url"
    file_id: str | None = None
    file_ref: str | None = None
    title: str | None = None  # defaults to the gate's own label
    note: str | None = None

    @model_validator(mode="after")
    def _require_source(self) -> GateDocumentAttach:
        _validate_source(self.source_type, self.file_id, self.file_ref)
        return self


class GateResultCreate(BaseModel):
    """§3.5 — a physical measurement or inspection result.

    `readings` for a measurement, `checklist_results` for an inspection. The
    engine evaluates against the seeded gate_rules threshold; a caller never
    declares `passed` itself.
    """

    readings: list[dict[str, Any]] = Field(default_factory=list)
    checklist_results: list[dict[str, Any]] = Field(default_factory=list)
    notes: str | None = None


class GateWaive(BaseModel):
    """§3 (SOP) — a director's written waiver of a hard gate. Recorded as a
    passing gate result with provenance; the reason is mandatory."""

    reason: str = Field(min_length=1)


class DelegationCreate(BaseModel):
    """SOP §2 — an approver delegates their position to a named deputy, in
    writing, for a defined period. `starts_at` defaults to now; `ends_at` is
    required and must be after the start."""

    approver_role: str = Field(min_length=1)
    delegate_user_id: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    starts_at: datetime | None = None
    ends_at: datetime

    @model_validator(mode="after")
    def _window_is_valid(self) -> DelegationCreate:
        if self.starts_at is not None and self.ends_at <= self.starts_at:
            raise ValueError("ends_at must be after starts_at")
        return self


class ChecklistMark(BaseModel):
    """v2.0 Stage 6 · Factory Release — mark one of the four release-checklist
    sections complete (or reopen it). All four must be complete before release."""

    complete: bool = True


class ClientAcceptanceCreate(BaseModel):
    """v2.0 Stage 9 (SOP §9) — a written client acceptance that lets the handover
    proceed with an open snag. The note (what the client accepted) is mandatory."""

    note: str = Field(min_length=1)


class SubmitBody(BaseModel):
    note: str | None = None


class ApproveBody(BaseModel):
    comment: str | None = None


class RejectBody(BaseModel):
    comment: str = Field(min_length=1)  # §5.5 a rejection must say why
    report_type: ReportType | None = None  # defaults to the stage's recovery type
    owner_id: str | None = None


class BomLine(BaseModel):
    """One BOM row — what Stage 8 reserves through Inventory (§1, acceptance #7)."""

    product_id: str = Field(min_length=1)
    qty: float = Field(gt=0)


class DeliverableCreate(BaseModel):
    kind: DeliverableKind
    title: str = Field(min_length=1)
    stage_key: str | None = None  # None → a general project document, no stage
    source_type: DeliverableSource = "url"
    file_id: str | None = None  # GridFS id when source_type == "upload"
    file_ref: str | None = None  # external URL when source_type == "url"
    note: str | None = None
    classification: Literal["auto", "manual"] = "manual"
    ocr_text: str | None = None
    lines: list[BomLine] = Field(default_factory=list)  # meaningful for kind="bom"

    @model_validator(mode="after")
    def _require_source(self) -> DeliverableCreate:
        _validate_source(self.source_type, self.file_id, self.file_ref)
        return self


class RevisionCreate(BaseModel):
    source_type: DeliverableSource = "url"
    file_id: str | None = None
    file_ref: str | None = None
    note: str | None = None

    @model_validator(mode="after")
    def _require_source(self) -> RevisionCreate:
        _validate_source(self.source_type, self.file_id, self.file_ref)
        return self


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
