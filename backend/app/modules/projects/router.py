"""Project Management API (docs/modules/PROJECT_MANAGEMENT.md §12).

GET → projects READ; mutations → projects WRITE. approve/reject additionally
require the stage's approver_role, which the service enforces (§9) because the
required position depends on which stage is being decided.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import StreamingResponse

from app.core import storage
from app.core.errors import PERMISSION_DENIED, DomainError
from app.modules.projects import service
from app.modules.projects.models import (
    ApproveBody,
    DeliverableCreate,
    DocumentSupply,
    GateConfigPatch,
    GateDocumentAttach,
    GateResultCreate,
    JobCostCreate,
    ProjectCreate,
    ProjectPatch,
    RejectBody,
    ReportCreate,
    ReportPatch,
    RevisionCreate,
    StageConfigPatch,
    SubmitBody,
)
from app.shared.enums import Level
from app.shared.schemas import PaginationParams, envelope, page_meta, to_api
from app.tenant.deps import ClientPrincipal, current_client_user, require

router = APIRouter(prefix="/api/v1/projects", tags=["client-projects"])

_read = require("projects", Level.READ)
_write = require("projects", Level.WRITE)


async def _approve_access(
    principal: ClientPrincipal = Depends(current_client_user),
) -> ClientPrincipal:
    """Guard for approve/reject (§9, acceptance #9). Two ways in:

      * `projects` WRITE — a normal staff approver, or
      * scoped client-portal access (`projects` >= VIEW **and** the role's
        `is_client_portal` flag) — a client-contact signing off THEIR stages
        without full module access.

    The service's `_assert_may_approve` still enforces that the caller holds the
    stage's approver position, so portal access alone approves nothing.
    """
    level = principal.level_for("projects")
    if level >= Level.WRITE:
        return principal
    if level >= Level.VIEW and principal.role.get("is_client_portal"):
        return principal
    raise DomainError(
        PERMISSION_DENIED,
        "Requires WRITE on 'projects', or scoped client-portal access.",
        http_status=403,
    )


async def _document_access(
    principal: ClientPrincipal = Depends(current_client_user),
) -> ClientPrincipal:
    """Guard for opening a document's file. Same two ways in as approve/reject:
    `projects` READ, or scoped client-portal access. An approver must be able to
    view the evidence attached to the stage they are signing off — a client
    contact holds VIEW, which is below READ, so plain `_read` would lock them out.
    """
    level = principal.level_for("projects")
    if level >= Level.READ:
        return principal
    if level >= Level.VIEW and principal.role.get("is_client_portal"):
        return principal
    raise DomainError(
        PERMISSION_DENIED,
        "Requires READ on 'projects', or scoped client-portal access.",
        http_status=403,
    )


# --- config (§12) — declared before /{project_id} so `config` is not an id ----

@router.get("/config/stages")
async def list_stage_config(principal: ClientPrincipal = Depends(_read)):
    return envelope(to_api(await service.list_stage_config(principal)))


@router.patch("/config/stages/{key}")
async def patch_stage_config(
    key: str, body: StageConfigPatch, principal: ClientPrincipal = Depends(_write)
):
    return envelope(to_api(await service.patch_stage_config(principal, key, body)))


@router.get("/config/gates")
async def list_gate_config(principal: ClientPrincipal = Depends(_read)):
    return envelope(to_api(await service.list_gate_config(principal)))


@router.patch("/config/gates/{key}")
async def patch_gate_config(
    key: str, body: GateConfigPatch, principal: ClientPrincipal = Depends(_write)
):
    return envelope(to_api(await service.patch_gate_config(principal, key, body)))


@router.get("/config/approver-roles")
async def list_approver_config(principal: ClientPrincipal = Depends(_read)):
    return envelope(to_api(await service.list_approver_config(principal)))


# --- projects & portfolio ----------------------------------------------------

@router.get("")
async def list_projects(
    page: PaginationParams = Depends(),
    status: str | None = None,
    pm_id: str | None = None,
    stage: int | None = None,
    principal: ClientPrincipal = Depends(_read),
):
    docs, total = await service.list_projects(
        principal, status, pm_id, stage, page.skip, page.page_size
    )
    return envelope(to_api(docs), page_meta(page.page, page.page_size, total))


@router.post("", status_code=201)
async def create_project(
    body: ProjectCreate, principal: ClientPrincipal = Depends(_write)
):
    return envelope(to_api(await service.create_project(principal, body)))


@router.get("/{project_id}")
async def get_project(project_id: str, principal: ClientPrincipal = Depends(_read)):
    return envelope(to_api(await service.get_project(principal, project_id)))


@router.patch("/{project_id}")
async def patch_project(
    project_id: str, body: ProjectPatch, principal: ClientPrincipal = Depends(_write)
):
    return envelope(to_api(await service.patch_project(principal, project_id, body)))


@router.delete("/{project_id}")
async def delete_project(project_id: str, principal: ClientPrincipal = Depends(_write)):
    await service.delete_project(principal, project_id)
    return envelope({"deleted": True})


@router.get("/{project_id}/timeline")
async def timeline(project_id: str, principal: ClientPrincipal = Depends(_read)):
    return envelope(to_api(await service.timeline(principal, project_id)))


@router.get("/{project_id}/board")
async def board(project_id: str, principal: ClientPrincipal = Depends(_read)):
    return envelope(to_api(await service.board(principal, project_id)))


# --- stage machine -----------------------------------------------------------

@router.get("/{project_id}/stages")
async def list_stages(project_id: str, principal: ClientPrincipal = Depends(_read)):
    return envelope(to_api(await service.list_stages(principal, project_id)))


@router.get("/{project_id}/stages/{order}")
async def get_stage(
    project_id: str, order: int, principal: ClientPrincipal = Depends(_read)
):
    return envelope(to_api(await service.get_stage(principal, project_id, order)))


@router.post("/{project_id}/stages/{order}/submit")
async def submit_stage(
    project_id: str, order: int, body: SubmitBody,
    principal: ClientPrincipal = Depends(_write),
):
    return envelope(to_api(
        await service.submit_stage(principal, project_id, order, body.note)
    ))


@router.post("/{project_id}/stages/{order}/approve")
async def approve_stage(
    project_id: str, order: int, body: ApproveBody,
    principal: ClientPrincipal = Depends(_approve_access),
):
    return envelope(to_api(
        await service.approve_stage(principal, project_id, order, body.comment)
    ))


@router.post("/{project_id}/stages/{order}/reject")
async def reject_stage(
    project_id: str, order: int, body: RejectBody,
    principal: ClientPrincipal = Depends(_approve_access),
):
    return envelope(to_api(await service.reject_stage(
        principal, project_id, order, body.comment, body.report_type, body.owner_id
    )))


@router.post("/{project_id}/stages/{order}/documents/{gate_key}")
async def supply_document(
    project_id: str, order: int, gate_key: str, body: DocumentSupply,
    principal: ClientPrincipal = Depends(_write),
):
    """Satisfy a `document` entry gate — §4 waiting → in_progress."""
    return envelope(to_api(
        await service.supply_document(principal, project_id, order, gate_key, body)
    ))


@router.post("/{project_id}/stages/{order}/documents/{gate_key}/attach", status_code=201)
async def attach_gate_document(
    project_id: str, order: int, gate_key: str, body: GateDocumentAttach,
    principal: ClientPrincipal = Depends(_write),
):
    """Attach the evidence a document gate requires — an uploaded file or a URL —
    and satisfy the gate in one step (§4). The gate defines the kind and stage,
    so neither is part of the payload."""
    return envelope(to_api(
        await service.attach_gate_document(principal, project_id, order, gate_key, body)
    ))


@router.post("/{project_id}/stages/{order}/gates/{gate_key}/result")
async def record_gate_result(
    project_id: str, order: int, gate_key: str, body: GateResultCreate,
    principal: ClientPrincipal = Depends(_write),
):
    return envelope(to_api(
        await service.record_gate_result(principal, project_id, order, gate_key, body)
    ))


@router.post("/{project_id}/stages/{order}/tasks/{task_key}/run")
async def run_task(
    project_id: str, order: int, task_key: str,
    principal: ClientPrincipal = Depends(_write),
):
    return envelope(to_api(
        await service.run_task(principal, project_id, order, task_key)
    ))


# --- deliverables & reports --------------------------------------------------

@router.get("/{project_id}/deliverables")
async def list_deliverables(
    project_id: str, page: PaginationParams = Depends(), kind: str | None = None,
    principal: ClientPrincipal = Depends(_read),
):
    docs, total = await service.list_deliverables(
        principal, project_id, kind, page.skip, page.page_size
    )
    return envelope(to_api(docs), page_meta(page.page, page.page_size, total))


@router.post("/{project_id}/deliverables/files", status_code=201)
async def upload_deliverable_file(
    project_id: str,
    file: UploadFile = File(...),
    principal: ClientPrincipal = Depends(_write),
):
    """Store an uploaded file in the tenant GridFS (§3.7); returns a handle to
    reference when creating a document or revision."""
    return envelope(await service.store_deliverable_file(principal, project_id, file))


@router.get("/{project_id}/deliverables/{did}/download")
async def download_deliverable(
    project_id: str, did: str, version: int | None = None,
    principal: ClientPrincipal = Depends(_document_access),
):
    """Stream an uploaded document version as an attachment (never inline)."""
    grid_out, filename, content_type = await service.open_deliverable_file(
        principal, project_id, did, version
    )
    return StreamingResponse(
        storage.read_chunks(grid_out),
        media_type=content_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/{project_id}/deliverables", status_code=201)
async def create_deliverable(
    project_id: str, body: DeliverableCreate,
    principal: ClientPrincipal = Depends(_write),
):
    return envelope(to_api(await service.create_deliverable(principal, project_id, body)))


@router.post("/{project_id}/deliverables/{did}/revisions", status_code=201)
async def add_revision(
    project_id: str, did: str, body: RevisionCreate,
    principal: ClientPrincipal = Depends(_write),
):
    return envelope(to_api(await service.add_revision(principal, project_id, did, body)))


@router.get("/{project_id}/reports")
async def list_reports(
    project_id: str, page: PaginationParams = Depends(),
    type: str | None = None, status: str | None = None,
    principal: ClientPrincipal = Depends(_read),
):
    docs, total = await service.list_reports(
        principal, project_id, type, status, page.skip, page.page_size
    )
    return envelope(to_api(docs), page_meta(page.page, page.page_size, total))


@router.post("/{project_id}/reports", status_code=201)
async def create_report(
    project_id: str, body: ReportCreate, principal: ClientPrincipal = Depends(_write)
):
    return envelope(to_api(await service.create_report(principal, project_id, body)))


@router.patch("/{project_id}/reports/{rid}")
async def patch_report(
    project_id: str, rid: str, body: ReportPatch,
    principal: ClientPrincipal = Depends(_write),
):
    return envelope(to_api(await service.patch_report(principal, project_id, rid, body)))


# --- job costing -------------------------------------------------------------

@router.get("/{project_id}/job-costs")
async def list_job_costs(
    project_id: str, page: PaginationParams = Depends(),
    principal: ClientPrincipal = Depends(_read),
):
    docs, total = await service.list_job_costs(
        principal, project_id, page.skip, page.page_size
    )
    return envelope(to_api(docs), page_meta(page.page, page.page_size, total))


@router.post("/{project_id}/job-costs", status_code=201)
async def create_job_cost(
    project_id: str, body: JobCostCreate, principal: ClientPrincipal = Depends(_write)
):
    return envelope(to_api(await service.create_job_cost(principal, project_id, body)))
