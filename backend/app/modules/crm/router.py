"""CRM API (docs/modules/CRM.md §3).

GET → crm READ; every mutation → crm WRITE. A `crm=NONE` role fails the guard
on every route here with PERMISSION_DENIED (acceptance #4).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import StreamingResponse

from app.core.config import settings
from app.modules.crm import csv_service, service
from app.modules.crm.models import (
    AccountCreate,
    AccountPatch,
    ActivityCreate,
    ActivityPatch,
    ContactCreate,
    ContactPatch,
    CsvExportQuery,
    DealCreate,
    DealPatch,
    DealStageChange,
    LeadConvert,
    LeadCreate,
    LeadPatch,
)
from app.shared.enums import Level
from app.shared.schemas import PaginationParams, envelope, page_meta, to_api
from app.tenant.deps import ClientPrincipal, require

router = APIRouter(prefix="/api/v1/crm", tags=["client-crm"])

_read = require("crm", Level.READ)
_write = require("crm", Level.WRITE)

OwnerFilter = Query(default=None, pattern="^(mine|all)$")


# --- accounts ----------------------------------------------------------------

@router.get("/accounts")
async def list_accounts(
    page: PaginationParams = Depends(),
    owner: str | None = OwnerFilter,
    status: str | None = None,
    q: str | None = None,
    principal: ClientPrincipal = Depends(_read),
):
    docs, total = await service.list_accounts(
        principal, owner, status, q, page.skip, page.page_size
    )
    return envelope(to_api(docs), page_meta(page.page, page.page_size, total))


@router.post("/accounts", status_code=201)
async def create_account(
    body: AccountCreate, principal: ClientPrincipal = Depends(_write)
):
    return envelope(to_api(await service.create_account(principal, body)))


@router.patch("/accounts/{account_id}")
async def patch_account(
    account_id: str, body: AccountPatch,
    principal: ClientPrincipal = Depends(_write),
):
    return envelope(to_api(await service.patch_account(principal, account_id, body)))


@router.delete("/accounts/{account_id}")
async def delete_account(account_id: str, principal: ClientPrincipal = Depends(_write)):
    await service.delete_account(principal, account_id)
    return envelope({"deleted": True})


# --- contacts ----------------------------------------------------------------

@router.get("/contacts")
async def list_contacts(
    page: PaginationParams = Depends(),
    owner: str | None = OwnerFilter,
    account_id: str | None = None,
    q: str | None = None,
    principal: ClientPrincipal = Depends(_read),
):
    docs, total = await service.list_contacts(
        principal, owner, account_id, q, page.skip, page.page_size
    )
    return envelope(to_api(docs), page_meta(page.page, page.page_size, total))


@router.post("/contacts", status_code=201)
async def create_contact(
    body: ContactCreate, principal: ClientPrincipal = Depends(_write)
):
    return envelope(to_api(await service.create_contact(principal, body)))


@router.patch("/contacts/{contact_id}")
async def patch_contact(
    contact_id: str, body: ContactPatch,
    principal: ClientPrincipal = Depends(_write),
):
    return envelope(to_api(await service.patch_contact(principal, contact_id, body)))


@router.delete("/contacts/{contact_id}")
async def delete_contact(contact_id: str, principal: ClientPrincipal = Depends(_write)):
    await service.delete_contact(principal, contact_id)
    return envelope({"deleted": True})


# --- leads -------------------------------------------------------------------

@router.get("/leads")
async def list_leads(
    page: PaginationParams = Depends(),
    owner: str | None = OwnerFilter,
    status: str | None = None,
    q: str | None = None,
    principal: ClientPrincipal = Depends(_read),
):
    docs, total = await service.list_leads(
        principal, owner, status, q, page.skip, page.page_size
    )
    return envelope(to_api(docs), page_meta(page.page, page.page_size, total))


@router.post("/leads", status_code=201)
async def create_lead(body: LeadCreate, principal: ClientPrincipal = Depends(_write)):
    return envelope(to_api(await service.create_lead(principal, body)))


@router.patch("/leads/{lead_id}")
async def patch_lead(
    lead_id: str, body: LeadPatch, principal: ClientPrincipal = Depends(_write)
):
    return envelope(to_api(await service.patch_lead(principal, lead_id, body)))


@router.delete("/leads/{lead_id}")
async def delete_lead(lead_id: str, principal: ClientPrincipal = Depends(_write)):
    await service.delete_lead(principal, lead_id)
    return envelope({"deleted": True})


@router.post("/leads/{lead_id}/convert", status_code=201)
async def convert_lead(
    lead_id: str, body: LeadConvert, principal: ClientPrincipal = Depends(_write)
):
    return envelope(to_api(await service.convert_lead(principal, lead_id, body)))


# --- deals -------------------------------------------------------------------

@router.get("/deals")
async def list_deals(
    page: PaginationParams = Depends(),
    owner: str | None = OwnerFilter,
    stage: str | None = None,
    account_id: str | None = None,
    pipeline: str | None = None,
    principal: ClientPrincipal = Depends(_read),
):
    docs, total = await service.list_deals(
        principal, owner, stage, account_id, page.skip, page.page_size, pipeline
    )
    return envelope(to_api(docs), page_meta(page.page, page.page_size, total))


@router.post("/deals", status_code=201)
async def create_deal(body: DealCreate, principal: ClientPrincipal = Depends(_write)):
    return envelope(to_api(await service.create_deal(principal, body)))


@router.patch("/deals/{deal_id}")
async def patch_deal(
    deal_id: str, body: DealPatch, principal: ClientPrincipal = Depends(_write)
):
    return envelope(to_api(await service.patch_deal(principal, deal_id, body)))


@router.patch("/deals/{deal_id}/stage")
async def change_deal_stage(
    deal_id: str, body: DealStageChange, principal: ClientPrincipal = Depends(_write)
):
    return envelope(to_api(await service.change_deal_stage(principal, deal_id, body)))


@router.delete("/deals/{deal_id}")
async def delete_deal(deal_id: str, principal: ClientPrincipal = Depends(_write)):
    await service.delete_deal(principal, deal_id)
    return envelope({"deleted": True})


@router.get("/pipeline")
async def get_pipeline(
    key: str = "default", principal: ClientPrincipal = Depends(_read)
):
    return envelope(to_api(await service.get_pipeline(principal, key)))


# --- activities --------------------------------------------------------------

@router.get("/activities")
async def list_activities(
    page: PaginationParams = Depends(),
    owner: str | None = OwnerFilter,
    entity_id: str | None = None,
    done: bool | None = None,
    principal: ClientPrincipal = Depends(_read),
):
    docs, total = await service.list_activities(
        principal, owner, entity_id, done, page.skip, page.page_size
    )
    return envelope(to_api(docs), page_meta(page.page, page.page_size, total))


@router.post("/activities", status_code=201)
async def create_activity(
    body: ActivityCreate, principal: ClientPrincipal = Depends(_write)
):
    return envelope(to_api(await service.create_activity(principal, body)))


@router.patch("/activities/{activity_id}")
async def patch_activity(
    activity_id: str, body: ActivityPatch,
    principal: ClientPrincipal = Depends(_write),
):
    return envelope(to_api(await service.patch_activity(principal, activity_id, body)))


@router.delete("/activities/{activity_id}")
async def delete_activity(activity_id: str, principal: ClientPrincipal = Depends(_write)):
    await service.delete_activity(principal, activity_id)
    return envelope({"deleted": True})


# --- CSV import & export (§7) ------------------------------------------------
#
# `{entity}` is one of accounts | contacts | leads | deals. Reading data out is
# crm READ; writing a spreadsheet back in is crm WRITE, exactly like the
# single-record routes above.

def _csv_response(body: str, filename: str) -> StreamingResponse:
    return StreamingResponse(
        iter([body]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/export/{entity}/fields")
async def export_fields(entity: str, principal: ClientPrincipal = Depends(_read)):
    """Columns and filters available for this data set — the export dialog and
    the import guide are both rendered from this, so the UI can never offer a
    column the server doesn't know."""
    return envelope(csv_service.describe(csv_service.entity_for(entity)))


@router.get("/export/{entity}")
async def export_entity(
    entity: str,
    params: CsvExportQuery = Depends(),
    principal: ClientPrincipal = Depends(_read),
):
    spec = csv_service.entity_for(entity)
    selected = csv_service.select_fields(spec, params.fields)
    query = csv_service.export_query(principal, spec, params)
    return StreamingResponse(
        csv_service.export_stream(principal, spec, selected, query),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition":
                f'attachment; filename="{csv_service.filename_for(spec, "export")}"',
        },
    )


@router.get("/import/{entity}/template")
async def import_template(
    entity: str, sample: bool = False, principal: ClientPrincipal = Depends(_read),
):
    """The blank CSV to fill in: every importable column, in spec order.
    `?sample=1` adds one example row to delete."""
    spec = csv_service.entity_for(entity)
    return _csv_response(
        csv_service.template(spec, sample=sample),
        csv_service.filename_for(spec, "template"),
    )


@router.post("/import/{entity}")
async def import_entity(
    entity: str,
    file: UploadFile = File(...),
    mode: str = Query(default="validate", pattern="^(validate|commit)$"),
    principal: ClientPrincipal = Depends(_write),
):
    """`mode=validate` reports what would happen and writes nothing;
    `mode=commit` applies it. The client posts the same file twice."""
    spec = csv_service.entity_for(entity)
    data = await csv_service.read_upload(
        file, max_bytes=settings.max_import_mb * 1024 * 1024
    )
    return envelope(await csv_service.import_csv(
        principal, spec, data,
        filename=(file.filename or "import.csv"),
        mode="commit" if mode == "commit" else "validate",
    ))
