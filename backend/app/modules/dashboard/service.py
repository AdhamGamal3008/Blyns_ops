"""Dashboard business logic (docs/modules/CLIENT_DASHBOARD.md).

All three surfaces are role-aware:
- quick actions: WRITE on the target resource AND module enabled (§1)
- KPIs: READ on the source module AND module enabled (§1)
- calendar: union of dated items from modules the user can READ (§2)
- activity: gated by `activity` READ; entries from modules below READ are
  dropped (§3) — a Viewer with crm=NONE never sees CRM activity.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.control_plane.companies.models import KNOWN_MODULES
from app.core.errors import VALIDATION_ERROR, DomainError
from app.modules.dashboard import repository as repo
from app.modules.dashboard.permissions import KPI_SOURCES, QUICK_ACTIONS
from app.shared.enums import Level
from app.tenant.deps import ClientPrincipal

CALENDAR_MAX_WINDOW_DAYS = 90


def _readable_modules(principal: ClientPrincipal) -> set[str]:
    enabled = set(principal.tenant.company["enabled_modules"])
    return {
        m for m in KNOWN_MODULES
        if m in enabled and principal.level_for(m) >= Level.READ
    }


def quick_actions(principal: ClientPrincipal) -> list[dict]:
    enabled = set(principal.tenant.company["enabled_modules"])
    return [
        a for a in QUICK_ACTIONS
        if a["module"] in enabled
        and principal.level_for(a["module"]) >= Level(a["required_level"])
    ]


async def kpis(principal: ClientPrincipal) -> dict:
    readable = _readable_modules(principal)
    db = principal.tenant_db
    out: dict = {}
    if KPI_SOURCES["open_projects"] in readable:
        out["open_projects"] = await repo.kpi_open_projects(db)
        out["overdue_tasks"] = await repo.kpi_overdue_tasks(db)
    if KPI_SOURCES["open_deals"] in readable:
        out["open_deals"] = await repo.kpi_open_deals(db)
    if KPI_SOURCES["low_stock_items"] in readable:
        out["low_stock_items"] = await repo.kpi_low_stock_items(db)
    if KPI_SOURCES["unpaid_invoices_total"] in readable:
        out["unpaid_invoices_total"] = await repo.kpi_unpaid_invoices_total(db)
    return out


async def calendar(
    principal: ClientPrincipal,
    start: datetime | None,
    end: datetime | None,
    modules: list[str] | None,
) -> list[dict]:
    now = datetime.now(UTC)
    start = start or now
    end = end or (start + timedelta(days=30))
    if start.tzinfo is None:
        start = start.replace(tzinfo=UTC)
    if end.tzinfo is None:
        end = end.replace(tzinfo=UTC)
    if end < start:
        raise DomainError(VALIDATION_ERROR, "`to` must be after `from`.", 422)
    if (end - start) > timedelta(days=CALENDAR_MAX_WINDOW_DAYS):
        raise DomainError(
            VALIDATION_ERROR,
            f"Calendar window is capped at {CALENDAR_MAX_WINDOW_DAYS} days.",
            422,
        )

    wanted = _readable_modules(principal)
    if modules:
        wanted &= set(modules)

    db = principal.tenant_db
    events: list[dict] = []
    if "projects" in wanted:
        events += await repo.calendar_projects(db, start, end)
    if "crm" in wanted:
        events += await repo.calendar_crm(db, start, end)
    if "finance" in wanted:
        events += await repo.calendar_finance(db, start, end)
    if "settings" in wanted:
        events += await repo.calendar_settings(
            db, start, end,
            user_id=str(principal.user["_id"]),
            role_id=principal.user["role_id"],
        )
    # inventory: reorder/restock dates not modeled yet (spec: "if modeled")
    events.sort(key=lambda e: e["start"])
    return events


async def activity(
    principal: ClientPrincipal,
    module: str | None,
    actor: str | None,
    start: datetime | None,
    end: datetime | None,
    cursor: str | None,
    limit: int,
) -> tuple[list[dict], str | None]:
    readable = _readable_modules(principal)
    if module is not None:
        if module in KNOWN_MODULES and module not in readable:
            return [], None  # asked for a module they cannot READ
        query: dict = {"module": module}
    else:
        # entries from business modules below READ are excluded; entries from
        # non-module sources (e.g. "auth") pass — the `activity` READ guard on
        # the endpoint is their gate
        hidden = [m for m in KNOWN_MODULES if m not in readable]
        query = {"module": {"$nin": hidden}}
    if actor:
        query["actor_id"] = actor
    time_range: dict = {}
    if start:
        time_range["$gte"] = start.replace(tzinfo=start.tzinfo or UTC)
    if end:
        time_range["$lte"] = end.replace(tzinfo=end.tzinfo or UTC)
    if time_range:
        query["occurred_at"] = time_range
    return await repo.activity_page(principal.tenant_db, query, cursor, limit)
