"""Production API (docs/PRODUCTION_MODULE_PLAN.md §6).

GET → production READ. Propose/confirm → production WRITE; confirm additionally
requires the `production_manager` position (enforced in the service, D4). The
release approval itself stays a pipeline action — Production never hosts it.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.modules.production import service
from app.modules.production.models import ProposeRequest, WorkOrderConfirm
from app.shared.enums import Level
from app.shared.schemas import PaginationParams, envelope, page_meta, to_api
from app.tenant.deps import ClientPrincipal, require

router = APIRouter(prefix="/api/v1/production", tags=["client-production"])

_read = require("production", Level.READ)
_write = require("production", Level.WRITE)


@router.get("/context")
async def get_context(principal: ClientPrincipal = Depends(_read)):
    return envelope(to_api(await service.context(principal)))


@router.get("/stations")
async def list_stations(principal: ClientPrincipal = Depends(_read)):
    return envelope(to_api(await service.list_stations(principal)))


# --- Queue (default landing view) --------------------------------------------

@router.get("/queue")
async def queue(
    station_id: str | None = None,
    project_id: str | None = None,
    due_days: int = 14,
    all_due: bool = False,
    principal: ClientPrincipal = Depends(_read),
):
    docs = await service.queue(principal, station_id, project_id, due_days, all_due)
    return envelope(to_api(docs))


# --- Work Orders -------------------------------------------------------------

@router.post("/work-orders/propose")
async def propose(body: ProposeRequest, principal: ClientPrincipal = Depends(_write)):
    return envelope(to_api(await service.propose_work_orders(principal, body.project_id)))


@router.post("/work-orders")
async def create(body: WorkOrderConfirm, principal: ClientPrincipal = Depends(_write)):
    return envelope(to_api(await service.create_work_orders(principal, body)))


@router.get("/work-orders")
async def list_work_orders(
    page: PaginationParams = Depends(),
    project_id: str | None = None,
    status: str | None = None,
    station_id: str | None = None,
    principal: ClientPrincipal = Depends(_read),
):
    docs, total = await service.list_work_orders(
        principal, project_id, status, station_id, page.skip, page.page_size
    )
    return envelope(to_api(docs), page_meta(page.page, page.page_size, total))


@router.get("/work-orders/{wo_id}")
async def get_work_order(wo_id: str, principal: ClientPrincipal = Depends(_read)):
    return envelope(to_api(await service.get_work_order(principal, wo_id)))
