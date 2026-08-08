"""CRM API (docs/modules/CRM.md §3).

GET → crm READ; every mutation → crm WRITE. A `crm=NONE` role fails the guard
on every route here with PERMISSION_DENIED (acceptance #4).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.modules.crm import analytics, service
from app.modules.crm.csv_schema import ENTITIES as CSV_ENTITIES
from app.modules.crm.models import (
    AccountCreate,
    AccountPatch,
    ActivityCreate,
    ActivityPatch,
    ContactCreate,
    ContactPatch,
    DealCreate,
    DealPatch,
    DealStageChange,
    LeadConvert,
    LeadCreate,
    LeadPatch,
)
from app.shared.csv_router import csv_routes
from app.shared.enums import Level
from app.shared.schemas import PaginationParams, envelope, page_meta, to_api
from app.tenant.deps import ClientPrincipal, require

router = APIRouter(prefix="/api/v1/crm", tags=["client-crm"])

_read = require("crm", Level.READ)
_write = require("crm", Level.WRITE)
# Analytics is a separate resource (management-only by default): VIEW = KPI row,
# READ = KPIs + charts. The service tiers the body; the guard is the floor.
_analytics = require("crm_analytics", Level.VIEW)

OwnerFilter = Query(default=None, pattern="^(mine|all)$")


# --- analytics (docs/PROJECT_ANALYTICS_PLAN.md §6-D) -------------------------

@router.get("/analytics")
async def analytics_overview(principal: ClientPrincipal = Depends(_analytics)):
    return envelope(to_api(await analytics.overview(principal)))


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
# `{entity}` is one of accounts | contacts | leads | deals. The routes are
# generated from the shared engine, so CRM and Inventory run the same code.

csv_routes(router, module="crm", registry=CSV_ENTITIES)
