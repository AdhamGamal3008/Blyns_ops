"""Production Analytics/Overview endpoint (docs/PRODUCTION_MODULE_PLAN.md §7 P5).

Seeds work orders (the shapes the service writes) and asserts every KPI and
chart, plus the RBAC tiering: READ = KPIs + charts, VIEW = KPIs only, NONE = 403.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from bson import ObjectId

from app.core.db import get_db_manager


def _tenant_db(onboarded_company):
    return get_db_manager().tenant(onboarded_company["company"]["db_name"])


async def _seed(db) -> None:
    now = datetime.now(UTC)
    s1, s2 = ObjectId(), ObjectId()
    await db.production_stations.insert_many([
        {"_id": s1, "code": "CUT", "name": "Cutting", "is_active": True},
        {"_id": s2, "code": "ASSY", "name": "Assembly", "is_active": True},
    ])

    def hist(*statuses):
        return [{"to_status": s, "at": now} for s in statuses]

    def wo(status, *, due=None, dispatched=None, station=None, history=()):
        return {
            "status": status, "due_date": due, "current_station_id": station,
            "qty": {"ordered": 10, "done": 0}, "history": list(history),
            "dispatch": {"dispatched_at": dispatched} if dispatched else None,
            "created_at": now, "is_deleted": False,
        }

    await db.work_orders.insert_many([
        # A: shipped on time; reached QC and was held on the way
        wo("dispatched", due=now, dispatched=now - timedelta(days=2),
           history=hist("qc_pending", "qc_hold", "passed")),
        # B: shipped late; reached QC, never held
        wo("dispatched", due=now - timedelta(days=10), dispatched=now - timedelta(days=2),
           history=hist("qc_pending", "passed")),
        # C: in progress (WIP) at Cutting, not yet at QC
        wo("in_progress", station=str(s1), history=hist("in_progress")),
        # D: on QC hold (WIP) at Assembly; reached QC + held
        wo("qc_hold", station=str(s2), history=hist("qc_pending", "qc_hold")),
        # E: queued (WIP), unassigned
        wo("queued", history=hist()),
    ])


async def test_production_analytics_kpis_and_charts(client_client, onboarded_company):
    await _seed(_tenant_db(onboarded_company))

    res = await client_client.get("/api/v1/production/analytics")
    assert res.status_code == 200, res.text
    data = res.json()["data"]

    k = data["kpis"]
    assert k["throughput"] == 2       # A + B shipped in the last 30 days
    assert k["on_time_pct"] == 50     # A on time, B late
    assert k["wip"] == 3              # C, D, E still open
    assert k["hold_rate"] == 67       # held A,D of QC-reaching A,B,D → 2/3

    by_status = {r["status"]: r["count"] for r in data["by_status"]}
    assert by_status == {"queued": 1, "in progress": 1, "qc hold": 1, "dispatched": 2}

    by_station = {r["station"]: r["open"] for r in data["by_station"]}
    assert by_station == {"Cutting": 1, "Assembly": 1, "Unassigned": 1}

    months = data["throughput"]
    assert len(months) == 6
    assert sum(m["dispatched"] for m in months) == 2


async def _set_owner_analytics(db, level: int) -> None:
    await db.roles.update_one(
        {"name": "Owner"}, {"$set": {"permissions.production_analytics": level}}
    )


async def test_production_analytics_rbac_tiers(client_client, onboarded_company):
    db = _tenant_db(onboarded_company)
    await _seed(db)

    res = await client_client.get("/api/v1/production/analytics")  # Owner WRITE → full
    assert res.status_code == 200
    assert "by_status" in res.json()["data"]

    await _set_owner_analytics(db, 1)  # VIEW → KPIs only
    data = (await client_client.get("/api/v1/production/analytics")).json()["data"]
    assert set(data) == {"kpis"}

    await _set_owner_analytics(db, 0)  # NONE → 403
    assert (await client_client.get("/api/v1/production/analytics")).status_code == 403
