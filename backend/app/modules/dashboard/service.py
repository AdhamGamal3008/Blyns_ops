"""Dashboard business logic (docs/modules/CLIENT_DASHBOARD.md).

All three surfaces are role-aware:
- quick actions: WRITE on the target resource AND module enabled (§1)
- KPIs: READ on the source module AND module enabled (§1)
- calendar: union of dated items from modules the user can READ (§2)
- activity: gated by `activity` READ; entries from modules below READ are
  dropped (§3) — a Viewer with crm=NONE never sees CRM activity.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.control_plane.companies.models import KNOWN_MODULES
from app.core.audit import write_activity
from app.core.config import settings
from app.core.errors import VALIDATION_ERROR, DomainError
from app.modules.dashboard import repository as repo
from app.modules.dashboard.permissions import (
    EXACT_ACTIONS,
    KPI_SOURCES,
    QUICK_ACTIONS,
)
from app.shared.enums import Level
from app.tenant.deps import ClientPrincipal

CALENDAR_MAX_WINDOW_DAYS = 90


def _readable_modules(principal: ClientPrincipal) -> set[str]:
    enabled = set(principal.tenant.company["enabled_modules"])
    return {
        m for m in KNOWN_MODULES
        if m in enabled and principal.level_for(m) >= Level.READ
    }


@dataclass(frozen=True)
class QaConfig:
    """Ranking constants snapshotted from settings per request, so `_score` stays
    a pure function of its arguments (config + role + events) — no global reads
    inside the formula (docs/QUICK_ACTIONS_PERSONALIZATION_PLAN.md §5)."""

    window_days: int
    half_life_days: float
    w_exact: float
    w_module: float
    role_write: float
    role_read: float
    tie_epsilon: float
    event_fetch_cap: int

    @classmethod
    def from_settings(cls) -> QaConfig:
        return cls(
            window_days=settings.qa_window_days,
            half_life_days=settings.qa_half_life_days,
            w_exact=settings.qa_weight_exact,
            w_module=settings.qa_weight_module,
            role_write=settings.qa_role_weight_write,
            role_read=settings.qa_role_weight_read,
            tie_epsilon=settings.qa_tie_epsilon,
            event_fetch_cap=settings.qa_event_fetch_cap,
        )


def _role_weight(level: Level, cfg: QaConfig) -> float:
    if level >= Level.WRITE:
        return cfg.role_write
    if level >= Level.READ:
        return cfg.role_read
    return 0.0


def _decay(age_days: float, half_life_days: float) -> float:
    """Recency half-life: an event `half_life_days` old counts half as much."""
    return 0.5 ** (age_days / half_life_days)


def _score(
    action: dict,
    declaration_index: int,
    catalog_size: int,
    level: Level,
    events: list[dict],
    now: datetime,
    cfg: QaConfig,
) -> float:
    """Explainable, deterministic score for one candidate action. Pure: identical
    arguments always yield the identical number (§2).

        role affinity
      + W_EXACT  · Σ decay(age)  over events whose action is exactly this one
      + W_MODULE · Σ decay(age)  over events in this action's module
      + curated tiebreak (earlier-declared wins)

    With no events both sums are zero, so the order collapses to the curated
    declaration order — the cold-start guarantee."""
    exact = EXACT_ACTIONS.get(action["key"], frozenset())
    module = action["module"]
    exact_sum = 0.0
    module_sum = 0.0
    for e in events:
        occurred = e["occurred_at"]
        if occurred.tzinfo is None:  # Mongo may hand back naive UTC
            occurred = occurred.replace(tzinfo=UTC)
        weight = _decay((now - occurred).total_seconds() / 86_400, cfg.half_life_days)
        if e.get("action") in exact:
            exact_sum += weight
        if e.get("module") == module:
            module_sum += weight
    curated_bias = cfg.tie_epsilon * (catalog_size - declaration_index)
    return (
        _role_weight(level, cfg)
        + cfg.w_exact * exact_sum
        + cfg.w_module * module_sum
        + curated_bias
    )


def _candidates(principal: ClientPrincipal) -> list[tuple[int, dict]]:
    """The hard gate: (declaration index, action) for every action whose module
    is enabled AND the caller is ≥ its required level. Everything downstream —
    ranking, pins, hides — only ever reorders or trims this set, so a forbidden
    action can never surface (§ locked decisions, non-negotiable rule 3)."""
    enabled = set(principal.tenant.company["enabled_modules"])
    return [
        (i, a)
        for i, a in enumerate(QUICK_ACTIONS)
        if a["module"] in enabled
        and principal.level_for(a["module"]) >= Level(a["required_level"])
    ]


async def quick_actions(principal: ClientPrincipal) -> tuple[list[dict], bool]:
    """The caller's ranked, personalized quick actions, plus whether they have
    anything to customize (used to keep the Customize entry reachable even when
    every action is hidden).

    Order: the user's pinned actions first (in pin order), then the
    behavior-ranked remainder (Phase 1); hidden actions are dropped. With no
    prefs and no recent activity this is exactly the curated order — cold start
    is preserved. Each returned action carries a `pinned` flag for the UI."""
    candidates = _candidates(principal)
    actor_id = str(principal.user["_id"])
    prefs = await repo.get_quick_action_prefs(principal.tenant_db, actor_id)
    pin_rank = {key: n for n, key in enumerate(prefs["pinned"])}
    hidden = set(prefs["hidden"])

    visible = [(i, a) for i, a in candidates if a["key"] not in hidden]

    cfg = QaConfig.from_settings()
    now = datetime.now(UTC)
    events = await repo.recent_activity_for_actor(
        principal.tenant_db, actor_id, now - timedelta(days=cfg.window_days), cfg.event_fetch_cap
    )
    catalog_size = len(QUICK_ACTIONS)

    pinned_actions = sorted(
        (a for _, a in visible if a["key"] in pin_rank),
        key=lambda a: pin_rank[a["key"]],
    )
    ranked_rest = [
        a
        for _, _, a in sorted(
            (
                (
                    _score(a, i, catalog_size, principal.level_for(a["module"]), events, now, cfg),
                    i,  # explicit tiebreak, so ties never hinge on float equality
                    a,
                )
                for i, a in visible
                if a["key"] not in pin_rank
            ),
            key=lambda t: (-t[0], t[1]),
        )
    ]

    ordered = [{**a, "pinned": a["key"] in pin_rank} for a in pinned_actions + ranked_rest]
    return ordered, len(candidates) > 0


async def customizable_actions(principal: ClientPrincipal) -> list[dict]:
    """Every action the caller may take, in curated order, tagged with its
    current pin/hide state — the source the Customize dialog renders (it includes
    hidden actions, so they can be brought back)."""
    actor_id = str(principal.user["_id"])
    prefs = await repo.get_quick_action_prefs(principal.tenant_db, actor_id)
    pinned, hidden = set(prefs["pinned"]), set(prefs["hidden"])
    return [
        {
            "key": a["key"],
            "label": a["label"],
            "module": a["module"],
            "pinned": a["key"] in pinned,
            "hidden": a["key"] in hidden,
        }
        for _, a in _candidates(principal)
    ]


async def set_quick_action_prefs(
    principal: ClientPrincipal, pinned: list[str], hidden: list[str]
) -> list[dict]:
    """Replace the caller's pins/hides. Only keys they may actually use are
    allowed — you cannot pin or hide what you cannot see — and an action cannot
    be both. The write is audited (non-negotiable rule 4)."""
    permitted = {a["key"] for _, a in _candidates(principal)}
    pinned = list(dict.fromkeys(pinned))  # de-dupe; this order IS the pin order
    hidden = list(dict.fromkeys(hidden))

    unknown = sorted((set(pinned) | set(hidden)) - permitted)
    if unknown:
        raise DomainError(
            VALIDATION_ERROR,
            f"Not permitted or unknown quick actions: {', '.join(unknown)}.",
            422,
        )
    both = sorted(set(pinned) & set(hidden))
    if both:
        raise DomainError(
            VALIDATION_ERROR,
            f"An action cannot be both pinned and hidden: {', '.join(both)}.",
            422,
        )

    await repo.set_quick_action_prefs(
        principal.tenant_db, str(principal.user["_id"]), pinned, hidden
    )
    await write_activity(
        principal.tenant_db,
        actor_id=str(principal.user["_id"]),
        action="dashboard.quick_actions.customized",
        entity={},
        details={"pinned": pinned, "hidden": hidden},
        actor_name=principal.user["name"],
        module="dashboard",
    )
    return await customizable_actions(principal)


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
