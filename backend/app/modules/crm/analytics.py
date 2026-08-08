"""CRM Analytics / Overview (docs/PROJECT_ANALYTICS_PLAN.md §6-D).

Same role-tiered contract as Projects: VIEW returns the headline KPI row, READ
adds the chart blocks, and a block the role can't reach is simply absent (never
null). Reads are not audited. Every aggregation filters soft-deletes.
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.modules.crm import repository as repo
from app.modules.crm.permissions import LEAD_STATUSES, OPEN_STAGES
from app.shared.enums import Level
from app.shared.timebuckets import month_buckets, window_start
from app.tenant.deps import ClientPrincipal

RESOURCE = "crm_analytics"

# Leads still worth working (not yet converted or discarded).
OPEN_LEAD_STATUSES = ["new", "contacted", "qualified"]
TOP_DEALS = 8
SOURCES = 6
INFLOW_MONTHS = 6


def _title(s: str) -> str:
    return s.replace("_", " ").capitalize()


# --- KPI row (VIEW+) ----------------------------------------------------------

async def _kpis(db) -> dict:
    stages = await repo.analytics_deal_stage(db)  # {stage: {count, amount}}
    lead_counts = await repo.analytics_status_counts(db, repo.LEADS)
    account_counts = await repo.analytics_status_counts(db, repo.ACCOUNTS)

    won = stages.get("won", {}).get("count", 0)
    lost = stages.get("lost", {}).get("count", 0)
    closed = won + lost
    return {
        "open_deals": sum(stages.get(s, {}).get("count", 0) for s in OPEN_STAGES),
        "pipeline_value": sum(stages.get(s, {}).get("amount", 0.0) for s in OPEN_STAGES),
        "pipeline_weighted": await repo.analytics_weighted_pipeline(db, list(OPEN_STAGES)),
        "win_rate": round(won / closed * 100, 1) if closed else None,
        "open_leads": sum(lead_counts.get(s, 0) for s in OPEN_LEAD_STATUSES),
        "customers": account_counts.get("customer", 0),
    }


# --- chart blocks (READ) ------------------------------------------------------

async def _charts(db) -> dict:
    now = datetime.now(UTC)
    stages = await repo.analytics_deal_stage(db)
    pipeline_by_stage = [
        {"stage": s, "label": _title(s),
         "count": stages.get(s, {}).get("count", 0),
         "amount": stages.get(s, {}).get("amount", 0.0)}
        for s in OPEN_STAGES
    ]

    lead_counts = await repo.analytics_status_counts(db, repo.LEADS)
    lead_status = [
        {"status": s, "label": _title(s), "count": lead_counts.get(s, 0)}
        for s in LEAD_STATUSES
    ]

    since = window_start(now, INFLOW_MONTHS)
    leads_m = await repo.analytics_monthly_new(db, repo.LEADS, since)
    deals_m = await repo.analytics_monthly_new(db, repo.DEALS, since)
    inflow = [
        {"month": m, "leads": leads_m.get(m, 0), "deals": deals_m.get(m, 0)}
        for m in month_buckets(now, INFLOW_MONTHS)
    ]

    return {
        "pipeline_by_stage": pipeline_by_stage,
        "lead_status": lead_status,
        "lead_sources": await repo.analytics_lead_sources(db, SOURCES),
        "top_deals": await repo.analytics_top_open_deals(db, list(OPEN_STAGES), TOP_DEALS),
        "inflow": inflow,
    }


# --- entry point --------------------------------------------------------------

async def overview(principal: ClientPrincipal) -> dict:
    db = principal.tenant_db
    out: dict = {"kpis": await _kpis(db)}
    if principal.level_for(RESOURCE) >= Level.READ:
        out.update(await _charts(db))
    return out
