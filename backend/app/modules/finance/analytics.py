"""Finance Analytics / Overview (docs/PROJECT_ANALYTICS_PLAN.md §6-D).

Same role-tiered contract as the other modules: VIEW = headline KPI row, READ =
+ chart blocks, absent-not-null below READ. Reads are not audited; every
aggregation filters soft-deletes.
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.modules.finance import repository as repo
from app.modules.finance.permissions import INVOICE_STATUSES, OPEN_STATUSES
from app.shared.enums import Level
from app.shared.timebuckets import month_buckets, window_start
from app.tenant.deps import ClientPrincipal

RESOURCE = "finance_analytics"

# Issued (recognized) documents — excludes draft and void.
ISSUED_STATUSES = ["sent", "partly_paid", "paid"]
TOP_OVERDUE = 8
TREND_MONTHS = 6
AGING_ORDER = ["Current", "1–30", "31–60", "61–90", "90+"]


def _aware(dt: datetime) -> datetime:
    """Mongo hands back naive UTC; make it comparable to an aware `now`."""
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def _title(s: str) -> str:
    return s.replace("_", " ").capitalize()


def _bucket(days: int) -> str:
    if days <= 0:
        return "Current"
    if days <= 30:
        return "1–30"
    if days <= 60:
        return "31–60"
    if days <= 90:
        return "61–90"
    return "90+"


# --- KPI row (VIEW+) ----------------------------------------------------------

async def _kpis(db) -> dict:
    now = datetime.now(UTC)
    inv = await repo.analytics_status_totals(db, repo.INVOICES)
    bill = await repo.analytics_status_totals(db, repo.BILLS)
    ar = await repo.aging_rows(db, repo.INVOICES, OPEN_STATUSES)
    ap = await repo.aging_rows(db, repo.BILLS, OPEN_STATUSES)
    return {
        "revenue": sum(inv.get(s, {}).get("total", 0.0) for s in ISSUED_STATUSES),
        "expenses": sum(bill.get(s, {}).get("total", 0.0) for s in ISSUED_STATUSES),
        "ar_outstanding": sum(r["outstanding"] for r in ar),
        "ap_outstanding": sum(r["outstanding"] for r in ap),
        "overdue_ar": sum(
            r["outstanding"] for r in ar if _aware(r["due_date"]) < now
        ),
    }


# --- chart blocks (READ) ------------------------------------------------------

def _by_status(totals: dict[str, dict]) -> list[dict]:
    return [
        {"status": _title(s),
         "amount": totals.get(s, {}).get("total", 0.0),
         "count": totals.get(s, {}).get("count", 0)}
        for s in INVOICE_STATUSES
    ]


async def _charts(db) -> dict:
    now = datetime.now(UTC)
    invoices_by_status = _by_status(await repo.analytics_status_totals(db, repo.INVOICES))
    bills_by_status = _by_status(await repo.analytics_status_totals(db, repo.BILLS))

    ar = await repo.aging_rows(db, repo.INVOICES, OPEN_STATUSES)
    buckets = {b: 0.0 for b in AGING_ORDER}
    for r in ar:
        buckets[_bucket((now - _aware(r["due_date"])).days)] += r["outstanding"]
    ar_aging = [{"bucket": b, "amount": buckets[b]} for b in AGING_ORDER]

    overdue = sorted(
        (r for r in ar if _aware(r["due_date"]) < now),
        key=lambda r: -r["outstanding"],
    )[:TOP_OVERDUE]
    top_overdue = [
        {"number": r.get("number") or "—", "outstanding": r["outstanding"],
         "days": (now - _aware(r["due_date"])).days}
        for r in overdue
    ]

    since = window_start(now, TREND_MONTHS)
    rev = await repo.analytics_monthly_totals(db, repo.INVOICES, ISSUED_STATUSES, since)
    exp = await repo.analytics_monthly_totals(db, repo.BILLS, ISSUED_STATUSES, since)
    cashflow = [
        {"month": m, "revenue": rev.get(m, 0.0), "expenses": exp.get(m, 0.0)}
        for m in month_buckets(now, TREND_MONTHS)
    ]

    return {
        "invoices_by_status": invoices_by_status,
        "bills_by_status": bills_by_status,
        "ar_aging": ar_aging,
        "top_overdue": top_overdue,
        "cashflow": cashflow,
    }


# --- entry point --------------------------------------------------------------

async def overview(principal: ClientPrincipal) -> dict:
    db = principal.tenant_db
    out: dict = {"kpis": await _kpis(db)}
    if principal.level_for(RESOURCE) >= Level.READ:
        out.update(await _charts(db))
    return out
