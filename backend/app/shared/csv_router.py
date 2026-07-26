"""The CSV routes, attached to any module's router.

Every module's CSV surface is the same shape — describe, export, template,
import, and the import-approval inbox — differing only in its entity registry.
Generating them keeps CRM and Inventory literally identical rather than similar,
so a fix to one is a fix to both.

    csv_routes(router, module="inventory", registry=ENTITIES)

Access is the per-tab CSV grant (shared/csv_access.py), layered on module READ:

    GET  /export/{entity}/fields    export OR import grant → columns + filters
    GET  /export/{entity}           export grant           → text/csv
    GET  /import/{entity}/template   import grant            → headers to fill in
    POST /import/{entity}           import grant            → validate | commit/stage
    GET  /import-requests           approve grant           → pending inbox / mine
    GET  /import-requests/{id}/file approve grant           → the staged CSV
    POST /import-requests/{id}/approve|reject  approve grant

Because the capability depends on the `{entity}` path parameter, the checks live
in the handlers (a static Depends cannot see the path), not in a role dependency.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, File, Query, UploadFile
from fastapi.responses import StreamingResponse

from app.core import storage
from app.core.config import settings
from app.core.errors import PERMISSION_DENIED, DomainError
from app.shared import csv_access, csv_service
from app.shared.schemas import CsvExportQuery, envelope
from app.tenant.deps import ClientPrincipal, current_client_user

_CSV_MEDIA = "text/csv; charset=utf-8"


def _attachment(filename: str) -> dict[str, str]:
    return {"Content-Disposition": f'attachment; filename="{filename}"'}


def _deny(module: str, entity: str, capability: str) -> DomainError:
    verb = {"export": "export", "import": "import",
            "approve_import": "approve imports for"}[capability]
    return DomainError(
        PERMISSION_DENIED,
        f"Your role cannot {verb} {module} {entity}.",
        http_status=403,
    )


def csv_routes(router: APIRouter, *, module: str, registry: dict[str, Any]) -> None:
    """Attach the CSV surface to `router`, gated by per-tab CSV grants."""

    @router.get("/export/{entity}/fields", name=f"{module}_export_fields")
    async def export_fields(
        entity: str, principal: ClientPrincipal = Depends(current_client_user)
    ):
        """Columns and filters for this data set — rendered by both the export
        dialog and the import guide, so either grant may read it."""
        spec = csv_service.entity_for(registry, module, entity)
        if not (
            csv_access.can_export(principal, module, entity)
            or csv_access.can_import(principal, module, entity)
        ):
            raise _deny(module, entity, "export")
        return envelope(csv_service.describe(spec))

    @router.get("/export/{entity}", name=f"{module}_export")
    async def export_entity(
        entity: str,
        params: CsvExportQuery = Depends(),
        principal: ClientPrincipal = Depends(current_client_user),
    ):
        spec = csv_service.entity_for(registry, module, entity)
        if not csv_access.can_export(principal, module, entity):
            raise _deny(module, entity, "export")
        selected = csv_service.select_fields(spec, params.fields)
        query = csv_service.export_query(principal, spec, params)
        return StreamingResponse(
            csv_service.export_stream(principal, spec, selected, query),
            media_type=_CSV_MEDIA,
            headers=_attachment(csv_service.filename_for(module, spec, "export")),
        )

    @router.get("/import/{entity}/template", name=f"{module}_import_template")
    async def import_template(
        entity: str,
        sample: bool = False,
        principal: ClientPrincipal = Depends(current_client_user),
    ):
        """The blank CSV to fill in: every importable column, in spec order.
        `?sample=1` adds one example row to delete."""
        spec = csv_service.entity_for_import(registry, module, entity)
        if not csv_access.can_import(principal, module, entity):
            raise _deny(module, entity, "import")
        return StreamingResponse(
            iter([csv_service.template(spec, sample=sample)]),
            media_type=_CSV_MEDIA,
            headers=_attachment(csv_service.filename_for(module, spec, "template")),
        )

    @router.post("/import/{entity}", name=f"{module}_import")
    async def import_entity(
        entity: str,
        file: UploadFile = File(...),
        mode: str = Query(default="validate", pattern="^(validate|commit)$"),
        principal: ClientPrincipal = Depends(current_client_user),
    ):
        """`mode=validate` reports what would happen and writes nothing.
        `mode=commit` commits it if the caller may approve imports for this tab;
        otherwise the file is staged and a pending approval request is opened."""
        spec = csv_service.entity_for_import(registry, module, entity)
        if not csv_access.can_import(principal, module, entity):
            raise _deny(module, entity, "import")
        data = await csv_service.read_upload(
            file, max_bytes=settings.max_import_mb * 1024 * 1024
        )
        filename = file.filename or "import.csv"
        if mode == "commit":
            return envelope(await csv_service.submit_import(
                principal, spec, data, module=module, filename=filename,
                can_approve=csv_access.can_approve(principal, module, entity),
            ))
        return envelope(await csv_service.import_csv(
            principal, spec, data, module=module, filename=filename, mode="validate",
        ))

    # --- import approval inbox ------------------------------------------------

    def _approvable_entities(principal: ClientPrincipal) -> set[str]:
        return {
            name for name in registry
            if csv_access.can_approve(principal, module, name)
        }

    @router.get("/import-requests", name=f"{module}_import_requests")
    async def list_import_requests(
        mine: bool = False,
        status: str | None = Query(default=None, pattern="^(pending|approved|rejected)$"),
        principal: ClientPrincipal = Depends(current_client_user),
    ):
        """`mine=1` lists the caller's own requests (any status); otherwise the
        approver inbox — pending requests for tabs the caller can approve."""
        approvable = _approvable_entities(principal)
        if not mine and not approvable:
            raise DomainError(
                PERMISSION_DENIED,
                f"Your role cannot approve {module} imports.", http_status=403,
            )
        return envelope(await csv_service.list_import_requests(
            principal, module, mine=mine, status=status,
            approvable_entities=approvable,
        ))

    async def _guard_request(
        principal: ClientPrincipal, request_id: str
    ) -> Any:
        """Load a request and confirm the caller may approve its entity."""
        doc = await csv_service.load_request(principal, module, request_id)
        entity = doc["entity"]
        if not csv_access.can_approve(principal, module, entity):
            raise _deny(module, entity, "approve_import")
        return doc, csv_service.entity_for_import(registry, module, entity)

    @router.get("/import-requests/{request_id}/file",
                name=f"{module}_import_request_file")
    async def import_request_file(
        request_id: str,
        principal: ClientPrincipal = Depends(current_client_user),
    ):
        await _guard_request(principal, request_id)
        grid_out, filename, content_type = await csv_service.open_request_file(
            principal, module, request_id
        )
        return StreamingResponse(
            storage.read_chunks(grid_out),
            media_type=content_type, headers=_attachment(filename),
        )

    @router.post("/import-requests/{request_id}/approve",
                 name=f"{module}_import_request_approve")
    async def approve_import_request(
        request_id: str,
        principal: ClientPrincipal = Depends(current_client_user),
    ):
        _, spec = await _guard_request(principal, request_id)
        return envelope(await csv_service.approve_import_request(
            principal, spec, module, request_id
        ))

    @router.post("/import-requests/{request_id}/reject",
                 name=f"{module}_import_request_reject")
    async def reject_import_request(
        request_id: str,
        reason: str = Body(default="", embed=True),
        principal: ClientPrincipal = Depends(current_client_user),
    ):
        _, spec = await _guard_request(principal, request_id)
        return envelope(await csv_service.reject_import_request(
            principal, spec, module, request_id, reason.strip(),
        ))
