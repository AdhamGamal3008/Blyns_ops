"""Discovery-booking service (docs/LANDING_PAGE.md §4).

- Public create: build the stored doc from the validated payload. No audit — the
  submitter is anonymous, not an admin actor.
- Admin read/update: list + detail, and a status/notes update that is audited to
  the control audit log (every admin write is audited, per the non-negotiables).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.control_plane.discovery_bookings import repository as repo
from app.control_plane.discovery_bookings.models import BookingCreate, BookingUpdate
from app.core.audit import write_admin_audit
from app.core.errors import NOT_FOUND, DomainError

_AUDIT_TARGET = "discovery_booking"


async def create_booking(
    control: AsyncIOMotorDatabase, payload: BookingCreate, source_ip: str | None
) -> dict:
    doc: dict[str, Any] = {
        "full_name": payload.full_name,
        "work_email": payload.work_email,
        "company": payload.company,
        "industry": payload.industry,
        "phone": payload.phone or None,
        "company_size": payload.company_size,
        "preferred_at": payload.preferred_at,
        "message": payload.message or None,
        "status": "new",
        "source": "landing",
        "source_ip": source_ip,
        "notes": [],
    }
    return await repo.insert(control, doc)


async def list_bookings(
    control: AsyncIOMotorDatabase, status: str | None, skip: int, limit: int
) -> tuple[list[dict], int]:
    return await repo.list_bookings(control, status, skip=skip, limit=limit)


async def get_booking(control: AsyncIOMotorDatabase, booking_id: str) -> dict:
    doc = await repo.get(control, booking_id)
    if doc is None:
        raise DomainError(NOT_FOUND, "Booking not found.", http_status=404)
    return doc


async def update_booking(
    control: AsyncIOMotorDatabase,
    booking_id: str,
    payload: BookingUpdate,
    actor_id: str,
) -> dict:
    set_fields: dict[str, str] = {}
    if payload.status is not None:
        set_fields["status"] = payload.status

    note = None
    if payload.note and payload.note.strip():
        note = {
            "author_id": actor_id,
            "text": payload.note.strip(),
            "at": datetime.now(UTC),
        }

    updated = await repo.update(control, booking_id, set_fields, note=note)
    if updated is None:
        raise DomainError(NOT_FOUND, "Booking not found.", http_status=404)

    await write_admin_audit(
        actor_id=actor_id,
        action="discovery_booking.updated",
        target={"type": _AUDIT_TARGET, "id": str(updated["_id"])},
        details={"status": payload.status, "note_added": note is not None},
    )
    return updated
