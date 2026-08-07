"""Projects Analytics / Overview (docs/PROJECT_ANALYTICS_PLAN.md).

A read-only, role-tiered portfolio surface:
- VIEW → the headline **KPI row** only (summary numbers).
- READ → the KPI row **plus** the decision-grade chart blocks.

A block the role can't reach is simply **absent** from the response (the same
contract the dashboard KPIs use — "render if present"), so the frontend never
has to know the caller's level. Reads are not audited (non-negotiable rule 4 =
writes only). Every aggregation filters soft-deletes in the repository.
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.modules.projects import repository as repo
from app.modules.projects.permissions import (
    COST_TYPES,
    OPEN_REPORT_STATUSES,
    STALLED_STATES,
)
from app.shared.enums import Level
from app.shared.timebuckets import month_buckets, window_start
from app.tenant.deps import ClientPrincipal

RESOURCE = "projects_analytics"

# Terminal statuses never sit in the "stalled" denominator; overdue counts any
# still-live delivery (on_hold included) but not work that is already done.
_TERMINAL_STATUSES = ["completed", "cancelled", "archived"]
_OVERDUE_EXCLUDE = ["completed", "cancelled"]

TOP_PROJECTS = 8
THROUGHPUT_MONTHS = 6


# --- KPI row (VIEW+) ----------------------------------------------------------

async def _kpis(db) -> dict:
    now = datetime.now(UTC)
    status_counts = await repo.analytics_status_counts(db)
    budget = await repo.analytics_budget_totals(db)
    variance = budget["actual"] - budget["planned"]
    return {
        "active": status_counts.get("active", 0),
        "on_hold_blocked": await repo.analytics_stalled_count(
            db, list(STALLED_STATES), _TERMINAL_STATUSES
        ),
        "overdue": await repo.analytics_overdue_count(db, now, _OVERDUE_EXCLUDE),
        "open_exceptions": await repo.analytics_open_report_count(
            db, OPEN_REPORT_STATUSES
        ),
        "budget": {
            "planned": budget["planned"],
            "actual": budget["actual"],
            "committed": budget["committed"],
            "variance": variance,
            "variance_pct": (
                round(variance / budget["planned"] * 100, 1)
                if budget["planned"] else None
            ),
        },
    }


# --- chart blocks (READ) ------------------------------------------------------

async def _charts(db) -> dict:
    now = datetime.now(UTC)
    defs = await repo.stage_defs(db)  # ordered 1..N
    label = {d["order"]: (d.get("name") or d["key"]) for d in defs}

    by_stage_counts = await repo.analytics_active_by_stage(db)
    by_stage = [
        {"order": d["order"], "key": d["key"], "label": label[d["order"]],
         "count": by_stage_counts.get(d["order"], 0)}
        for d in defs
    ]

    tis = await repo.analytics_time_in_current_stage(db, now)
    # Only stages that actually hold active projects — a bottleneck view.
    time_in_stage = [
        {"order": d["order"], "key": d["key"], "label": label[d["order"]],
         "avg_days": tis[d["order"]]["avg_days"], "count": tis[d["order"]]["count"]}
        for d in defs if d["order"] in tis
    ]

    budget = await repo.analytics_budget_totals(db)
    cost_map = await repo.analytics_cost_by_type(db)
    budget_block = {
        "portfolio": {
            "planned": budget["planned"], "actual": budget["actual"],
            "committed": budget["committed"],
        },
        "top_projects": await repo.analytics_top_projects(db, TOP_PROJECTS),
        "cost_by_type": [
            {"cost_type": t, "amount": cost_map.get(t, 0.0)} for t in COST_TYPES
        ],
    }

    exceptions = _shape_exceptions(
        await repo.analytics_exceptions_by_type_status(db, OPEN_REPORT_STATUSES)
    )

    since = window_start(now, THROUGHPUT_MONTHS)
    started = await repo.analytics_monthly_counts(db, "created_at", since)
    completed = await repo.analytics_monthly_counts(db, "completed_at", since)
    throughput = [
        {"month": m, "started": started.get(m, 0), "completed": completed.get(m, 0)}
        for m in month_buckets(now, THROUGHPUT_MONTHS)
    ]

    return {
        "by_stage": by_stage,
        "time_in_stage": time_in_stage,
        "budget": budget_block,
        "exceptions": exceptions,
        "throughput": throughput,
    }


def _shape_exceptions(rows: list[dict]) -> list[dict]:
    """Collapse (type, status) counts into one stacked row per type:
    {type, open, in_progress, total}, biggest exposure first."""
    by_type: dict[str, dict] = {}
    for r in rows:
        slot = by_type.setdefault(
            r["type"], {"type": r["type"], "open": 0, "in_progress": 0}
        )
        if r["status"] in slot:
            slot[r["status"]] += r["n"]
    ranked = ({**s, "total": s["open"] + s["in_progress"]} for s in by_type.values())
    return sorted(ranked, key=lambda s: (-s["total"], s["type"]))


# --- entry point --------------------------------------------------------------

async def overview(principal: ClientPrincipal) -> dict:
    """The analytics payload for the caller's tier: KPIs always; chart blocks
    only at READ+ (absent otherwise, never null)."""
    db = principal.tenant_db
    out: dict = {"kpis": await _kpis(db)}
    if principal.level_for(RESOURCE) >= Level.READ:
        out.update(await _charts(db))
    return out
