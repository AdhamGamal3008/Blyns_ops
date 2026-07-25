"""The four CSV routes, attached to any module's router.

Every module's CSV surface is the same shape — describe, export, template,
import — differing only in its entity registry and its RBAC guards. Generating
them keeps CRM and Inventory literally identical rather than similar, so a fix
to one is a fix to both.

    csv_routes(router, module="inventory", registry=ENTITIES,
               read=_read, write=_write)

gives:
    GET  /export/{entity}/fields    READ   → columns + filters (drives the UI)
    GET  /export/{entity}           READ   → text/csv
    GET  /import/{entity}/template  READ   → text/csv headers to fill in
    POST /import/{entity}           WRITE  → multipart; mode=validate|commit
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import StreamingResponse

from app.core.config import settings
from app.shared import csv_service
from app.shared.schemas import CsvExportQuery, envelope
from app.tenant.deps import ClientPrincipal

_CSV_MEDIA = "text/csv; charset=utf-8"


def _attachment(filename: str) -> dict[str, str]:
    return {"Content-Disposition": f'attachment; filename="{filename}"'}


def csv_routes(
    router: APIRouter,
    *,
    module: str,
    registry: dict[str, Any],
    read: Any,
    write: Any,
) -> None:
    """Attach the CSV surface to `router`. Reading data out takes the module's
    READ level; writing a spreadsheet back in takes WRITE — the same guards its
    single-record routes use."""

    @router.get("/export/{entity}/fields", name=f"{module}_export_fields")
    async def export_fields(
        entity: str, principal: ClientPrincipal = Depends(read)
    ):
        """Columns and filters available for this data set. The export dialog
        and the import guide are both rendered from this, so the UI can never
        offer a column the server doesn't know."""
        return envelope(
            csv_service.describe(csv_service.entity_for(registry, module, entity))
        )

    @router.get("/export/{entity}", name=f"{module}_export")
    async def export_entity(
        entity: str,
        params: CsvExportQuery = Depends(),
        principal: ClientPrincipal = Depends(read),
    ):
        spec = csv_service.entity_for(registry, module, entity)
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
        principal: ClientPrincipal = Depends(read),
    ):
        """The blank CSV to fill in: every importable column, in spec order.
        `?sample=1` adds one example row to delete."""
        spec = csv_service.entity_for_import(registry, module, entity)
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
        principal: ClientPrincipal = Depends(write),
    ):
        """`mode=validate` reports what would happen and writes nothing;
        `mode=commit` applies it. The client posts the same file twice, so the
        server holds no half-finished import state."""
        spec = csv_service.entity_for_import(registry, module, entity)
        data = await csv_service.read_upload(
            file, max_bytes=settings.max_import_mb * 1024 * 1024
        )
        return envelope(await csv_service.import_csv(
            principal, spec, data,
            module=module,
            filename=(file.filename or "import.csv"),
            mode="commit" if mode == "commit" else "validate",
        ))
