"""Discovery-booking APIs.

- `public_router` — `POST /api/v1/public/discovery-bookings`: **unauthenticated**
  lead capture from the landing page. Validated at the edge; a honeypot hit is
  accepted but dropped; the global rate-limit middleware fronts it for floods.
- `router` — `GET/GET/PATCH /api/v1/admin/discovery-bookings`: the admin surface,
  gated on the `leads` resource. VIEW sees a non-PII summary (it exists); READ+
  sees the full record; WRITE can advance status / add notes (audited).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request

from app.control_plane.discovery_bookings import service
from app.control_plane.discovery_bookings.models import (
    STATUSES,
    BookingCreate,
    BookingUpdate,
)
from app.core.client_ip import client_ip
from app.core.config import settings
from app.core.db import get_db_manager
from app.shared.enums import Level
from app.shared.schemas import PaginationParams, envelope, page_meta, to_api
from app.tenant.deps import AdminPrincipal, require_admin

router = APIRouter(
    prefix="/api/v1/admin/discovery-bookings", tags=["admin-discovery-bookings"]
)
public_router = APIRouter(
    prefix="/api/v1/public/discovery-bookings", tags=["public-discovery-bookings"]
)

# VIEW gets a non-PII summary — enough to see a lead exists, without name/email/
# phone/message (docs/AUTH_RBAC.md §2). READ+ gets the full document.
_SUMMARY_FIELDS = ("_id", "company", "industry", "status", "created_at")
_STATUS_PATTERN = f"^({'|'.join(STATUSES)})$"


def _booking_view(doc: dict, level: Level) -> dict:
    if level == Level.VIEW:
        return {k: doc.get(k) for k in _SUMMARY_FIELDS}
    return doc


@public_router.post("", status_code=201)
async def submit(payload: BookingCreate, request: Request):
    """Public booking submission. Returns a minimal confirmation only."""
    if payload.is_honeypot:
        # A bot filled the hidden field: report success so it moves on, but never
        # persist the row.
        return envelope({"received": True})
    ip = client_ip(request, settings.ip_trusted_proxies)
    await service.create_booking(get_db_manager().control, payload, source_ip=ip)
    return envelope({"received": True})


@router.get("")
async def list_all(
    params: PaginationParams = Depends(),
    status: str | None = Query(default=None, pattern=_STATUS_PATTERN),
    admin: AdminPrincipal = Depends(require_admin("leads", Level.VIEW)),
):
    docs, total = await service.list_bookings(
        get_db_manager().control, status, params.skip, params.page_size
    )
    level = admin.level_for("leads")
    return envelope(
        [to_api(_booking_view(d, level)) for d in docs],
        meta=page_meta(params.page, params.page_size, total),
    )


@router.get("/{booking_id}")
async def detail(
    booking_id: str,
    admin: AdminPrincipal = Depends(require_admin("leads", Level.READ)),
):
    booking = await service.get_booking(get_db_manager().control, booking_id)
    return envelope(to_api(booking))


@router.patch("/{booking_id}")
async def update(
    booking_id: str,
    payload: BookingUpdate,
    admin: AdminPrincipal = Depends(require_admin("leads", Level.WRITE)),
):
    updated = await service.update_booking(
        get_db_manager().control, booking_id, payload, actor_id=str(admin.user["_id"])
    )
    return envelope(to_api(updated))
