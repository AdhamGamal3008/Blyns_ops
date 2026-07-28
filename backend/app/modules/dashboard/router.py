"""Dashboard API (docs/modules/CLIENT_DASHBOARD.md §4).

GET /api/v1/dashboard/quick-actions
GET /api/v1/dashboard/kpis
GET /api/v1/calendar
GET /api/v1/activity
All tenant-bound; RBAC per surface (dashboard / calendar / activity).
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from app.modules.dashboard import service
from app.shared.enums import Level
from app.shared.schemas import envelope, to_api
from app.tenant.deps import ClientPrincipal, require

router = APIRouter(prefix="/api/v1", tags=["client-dashboard"])


class QuickActionPrefsInput(BaseModel):
    """A full replacement of the caller's pins/hides (Phase 2). Order of `pinned`
    is the order they appear inline."""

    pinned: list[str] = Field(default_factory=list)
    hidden: list[str] = Field(default_factory=list)


@router.get("/dashboard/quick-actions")
async def quick_actions(
    principal: ClientPrincipal = Depends(require("dashboard", Level.VIEW)),
):
    actions, customizable = await service.quick_actions(principal)
    return envelope(actions, meta={"customizable": customizable})


@router.get("/dashboard/quick-actions/prefs")
async def quick_action_prefs(
    principal: ClientPrincipal = Depends(require("dashboard", Level.VIEW)),
):
    return envelope(await service.customizable_actions(principal))


@router.put("/dashboard/quick-actions/prefs")
async def update_quick_action_prefs(
    body: QuickActionPrefsInput,
    principal: ClientPrincipal = Depends(require("dashboard", Level.VIEW)),
):
    return envelope(
        await service.set_quick_action_prefs(principal, body.pinned, body.hidden)
    )


@router.get("/dashboard/suggestions")
async def suggestions(
    principal: ClientPrincipal = Depends(require("dashboard", Level.VIEW)),
):
    return envelope(await service.suggestions(principal))


@router.post("/dashboard/suggestions/{key}/dismiss")
async def dismiss_suggestion(
    key: str,
    principal: ClientPrincipal = Depends(require("dashboard", Level.VIEW)),
):
    return envelope(await service.dismiss_suggestion(principal, key))


@router.get("/dashboard/kpis")
async def kpis(
    principal: ClientPrincipal = Depends(require("dashboard", Level.VIEW)),
):
    return envelope(await service.kpis(principal))


@router.get("/calendar")
async def calendar(
    from_: datetime | None = Query(default=None, alias="from"),
    to: datetime | None = Query(default=None),
    modules: str | None = Query(default=None, description="comma-separated filter"),
    principal: ClientPrincipal = Depends(require("calendar", Level.READ)),
):
    module_list = [m.strip() for m in modules.split(",")] if modules else None
    events = await service.calendar(principal, from_, to, module_list)
    return envelope(to_api(events))


@router.get("/activity")
async def activity(
    module: str | None = Query(default=None),
    actor: str | None = Query(default=None),
    from_: datetime | None = Query(default=None, alias="from"),
    to: datetime | None = Query(default=None),
    cursor: str | None = Query(default=None),
    page_size: int = Query(default=25, ge=1, le=100),
    principal: ClientPrincipal = Depends(require("activity", Level.READ)),
):
    items, next_cursor = await service.activity(
        principal, module, actor, from_, to, cursor, page_size
    )
    return envelope(
        to_api(items), meta={"next_cursor": next_cursor, "page_size": page_size}
    )
