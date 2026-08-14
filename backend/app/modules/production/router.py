"""Production API (docs/PRODUCTION_MODULE_PLAN.md §6).

GET → production READ. Propose/confirm → production WRITE; confirm additionally
requires the `production_manager` position (enforced in the service, D4). The
release approval itself stays a pipeline action — Production never hosts it.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.modules.production import analytics, service
from app.modules.production.models import (
    AllocateInput,
    DispatchInput,
    PackInput,
    ProposeRequest,
    QCResultInput,
    RequestQCInput,
    ReworkInput,
    ShortfallInput,
    StageInput,
    WorkOrderConfirm,
)
from app.shared.enums import Level
from app.shared.schemas import PaginationParams, envelope, page_meta, to_api
from app.tenant.deps import ClientPrincipal, require

router = APIRouter(prefix="/api/v1/production", tags=["client-production"])

_read = require("production", Level.READ)
_write = require("production", Level.WRITE)
_analytics = require("production_analytics", Level.VIEW)


# --- analytics (docs/PRODUCTION_MODULE_PLAN.md §7 Phase 5) --------------------

@router.get("/analytics")
async def analytics_overview(principal: ClientPrincipal = Depends(_analytics)):
    return envelope(to_api(await analytics.overview(principal)))


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


# --- status transitions (§2.2). Release additionally requires the
# production_manager position (enforced in the service); the floor actions are
# plain WRITE (soft functions, plan §4). ---------------------------------------

@router.post("/work-orders/{wo_id}/release")
async def release(wo_id: str, principal: ClientPrincipal = Depends(_write)):
    return envelope(to_api(await service.release_work_order(principal, wo_id)))


@router.post("/work-orders/{wo_id}/start")
async def start(wo_id: str, principal: ClientPrincipal = Depends(_write)):
    return envelope(to_api(await service.start_work_order(principal, wo_id)))


@router.post("/work-orders/{wo_id}/request-qc")
async def request_qc(
    wo_id: str, body: RequestQCInput, principal: ClientPrincipal = Depends(_write)
):
    return envelope(to_api(await service.request_qc(principal, wo_id, body)))


@router.post("/work-orders/{wo_id}/qc")
async def record_qc(
    wo_id: str, body: QCResultInput, principal: ClientPrincipal = Depends(_write)
):
    return envelope(to_api(await service.record_qc(principal, wo_id, body)))


@router.post("/work-orders/{wo_id}/rework")
async def rework(
    wo_id: str, body: ReworkInput, principal: ClientPrincipal = Depends(_write)
):
    return envelope(to_api(await service.rework_work_order(principal, wo_id, body)))


@router.post("/work-orders/{wo_id}/shortfall")
async def shortfall(
    wo_id: str, body: ShortfallInput, principal: ClientPrincipal = Depends(_write)
):
    return envelope(to_api(await service.flag_shortfall(principal, wo_id, body)))


# --- packing + dispatch (Phase 4, §2.2). Floor actions — plain WRITE. ---------

@router.post("/work-orders/{wo_id}/pack")
async def pack(
    wo_id: str, body: PackInput, principal: ClientPrincipal = Depends(_write)
):
    return envelope(to_api(await service.pack_work_order(principal, wo_id, body)))


@router.post("/work-orders/{wo_id}/stage")
async def stage(
    wo_id: str, body: StageInput, principal: ClientPrincipal = Depends(_write)
):
    return envelope(to_api(await service.stage_work_order(principal, wo_id, body)))


@router.post("/work-orders/{wo_id}/dispatch")
async def dispatch(
    wo_id: str, body: DispatchInput, principal: ClientPrincipal = Depends(_write)
):
    return envelope(to_api(await service.dispatch_work_order(principal, wo_id, body)))


@router.get("/work-orders/{wo_id}/manifest")
async def manifest(wo_id: str, principal: ClientPrincipal = Depends(_read)):
    return envelope(to_api(await service.work_order_manifest(principal, wo_id)))


@router.get("/dispatch")
async def dispatch_board(
    project_id: str | None = None, principal: ClientPrincipal = Depends(_read)
):
    return envelope(to_api(await service.dispatch_board(principal, project_id)))


# --- station allocation (§3). Both require the production_manager position
# (enforced in the service) — operators do not move WOs between work centres. ---

@router.post("/work-orders/{wo_id}/allocate")
async def allocate(
    wo_id: str, body: AllocateInput, principal: ClientPrincipal = Depends(_write)
):
    return envelope(to_api(await service.allocate_work_order(principal, wo_id, body.station_id)))


@router.post("/work-orders/{wo_id}/auto-allocate")
async def auto_allocate(wo_id: str, principal: ClientPrincipal = Depends(_write)):
    return envelope(to_api(await service.auto_allocate_work_order(principal, wo_id)))


# --- pipeline mirror (read-only; the approve lives in the pipeline) ----------

@router.get("/projects/{project_id}/rollup")
async def project_rollup(project_id: str, principal: ClientPrincipal = Depends(_read)):
    return envelope(to_api(await service.project_rollup(principal, project_id)))
