"""Production Analytics / Overview (docs/PRODUCTION_MODULE_PLAN.md §7 Phase 5).

Same role-tiered contract as the other modules' analytics: VIEW = headline KPI
row, READ = + chart blocks, absent-not-null below READ. Reads are not audited.
Everything is computed from the live work orders in one pass (no cost — plan D3).
"""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime, timedelta

from app.modules.production import repository as repo
from app.modules.production.permissions import WO_STATUSES
from app.shared.enums import Level
from app.shared.timebuckets import month_buckets, window_start
from app.tenant.deps import ClientPrincipal

RESOURCE = "production_analytics"

DONE = "dispatched"          # the terminal status — a WO that has shipped
THROUGHPUT_DAYS = 30         # the "throughput" KPI window
THROUGHPUT_MONTHS = 6        # the throughput trend chart window


def _naive(d: datetime) -> datetime:
    """Normalise to naive so tz-aware inputs and naive Mongo datetimes compare."""
    return d.replace(tzinfo=None) if d.tzinfo else d


def _dispatched_at(wo: dict) -> datetime | None:
    d = (wo.get("dispatch") or {}).get("dispatched_at")
    return d if isinstance(d, datetime) else None


# --- KPI row (VIEW+) ----------------------------------------------------------

def _kpis(wos: list[dict], now: datetime) -> dict:
    dispatched = [w for w in wos if w.get("status") == DONE]

    horizon = _naive(now - timedelta(days=THROUGHPUT_DAYS))
    throughput = sum(
        1 for w in dispatched
        if (da := _dispatched_at(w)) and _naive(da) >= horizon
    )

    # on-time %: of dispatched WOs that had a due date, the share shipped by it
    with_due = [(w, _dispatched_at(w)) for w in dispatched if w.get("due_date")]
    on_time = sum(
        1 for w, da in with_due if da and _naive(da) <= _naive(w["due_date"])
    )
    on_time_pct = round(100 * on_time / len(with_due)) if with_due else None

    # WIP: open work orders (anything not yet shipped)
    wip = sum(1 for w in wos if w.get("status") != DONE)

    # hold rate: of the WOs that reached QC, the share that were ever held
    reached = held = 0
    for w in wos:
        seen = {h.get("to_status") for h in (w.get("history") or [])}
        if seen & {"qc_pending", "qc_hold", "passed"}:
            reached += 1
            if "qc_hold" in seen:
                held += 1
    hold_rate = round(100 * held / reached) if reached else None

    return {
        "throughput": throughput,
        "on_time_pct": on_time_pct,
        "wip": wip,
        "hold_rate": hold_rate,
    }


# --- chart blocks (READ) ------------------------------------------------------

def _charts(wos: list[dict], stations: dict[str, dict], now: datetime) -> dict:
    status_counts = Counter(w.get("status") for w in wos)
    by_status = [
        {"status": s.replace("_", " "), "count": status_counts[s]}
        for s in WO_STATUSES if status_counts.get(s)
    ]

    open_wos = [w for w in wos if w.get("status") != DONE]
    station_counts: Counter = Counter()
    unassigned = 0
    for w in open_wos:
        sid = w.get("current_station_id")
        if sid:
            station_counts[sid] += 1
        else:
            unassigned += 1
    by_station = [
        {"station": (stations.get(sid) or {}).get("name") or "—", "open": count}
        for sid, count in station_counts.most_common()
    ]
    if unassigned:
        by_station.append({"station": "Unassigned", "open": unassigned})

    start = _naive(window_start(now, THROUGHPUT_MONTHS))
    monthly: Counter = Counter()
    for w in wos:
        if w.get("status") == DONE and (da := _dispatched_at(w)) and _naive(da) >= start:
            monthly[_naive(da).strftime("%Y-%m")] += 1
    throughput = [
        {"month": m, "dispatched": monthly.get(m, 0)}
        for m in month_buckets(now, THROUGHPUT_MONTHS)
    ]

    return {"by_status": by_status, "by_station": by_station, "throughput": throughput}


# --- entry point --------------------------------------------------------------

async def overview(principal: ClientPrincipal) -> dict:
    db = principal.tenant_db
    now = datetime.now(UTC)
    wos = await repo.analytics_work_orders(db)
    out: dict = {"kpis": _kpis(wos, now)}
    if principal.level_for(RESOURCE) >= Level.READ:
        stations = await repo.stations_map(db)
        out.update(_charts(wos, stations, now))
    return out
