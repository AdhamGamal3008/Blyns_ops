"""Projects Analytics/Overview endpoint (docs/PROJECT_ANALYTICS_PLAN.md, Phase B).

Seeds a controlled portfolio straight into the tenant DB (the exact shapes the
projects service writes) and asserts every KPI and chart block, plus the RBAC
tiering: READ = KPIs + charts, VIEW = KPIs only, NONE = 403.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from bson import ObjectId

from app.core.db import get_db_manager


def _tenant_db(onboarded_company):
    return get_db_manager().tenant(onboarded_company["company"]["db_name"])


async def _seed_portfolio(db) -> None:
    """Five projects exercising every metric; one soft-deleted to prove _LIVE."""
    now = datetime.now(UTC)
    a, b, c, d, e = (ObjectId() for _ in range(5))

    def project(_id, code, status, order, planned, actual, **extra):
        doc = {
            "_id": _id, "code": code, "name": f"Project {code}", "status": status,
            "current_stage_order": order, "current_stage_key": f"stage_{order}",
            "budget": {"planned": planned, "committed": 0.0, "actual": actual,
                       "currency": "USD"},
            "schedule": {}, "is_deleted": False,
            "created_at": now - timedelta(days=30),
        }
        doc.update(extra)
        return doc

    await db.projects.insert_many([
        # active, in stage 3 for 10 days, on budget, delivery in the future
        project(a, "PRJ-A", "active", 3, 1000.0, 200.0,
                schedule={"delivery_date": now + timedelta(days=30)},
                created_at=now - timedelta(days=60)),
        # active but its current stage is WAITING (stalled) + delivery is overdue
        project(b, "PRJ-B", "active", 3, 500.0, 100.0,
                schedule={"delivery_date": now - timedelta(days=5)},
                created_at=now - timedelta(days=45)),
        # on_hold → counts toward on_hold_blocked via project status
        project(c, "PRJ-C", "on_hold", 5, 2000.0, 1500.0,
                created_at=now - timedelta(days=40)),
        # completed last month → throughput completed; still in budget totals
        project(d, "PRJ-D", "completed", 9, 800.0, 850.0,
                completed_at=now - timedelta(days=20),
                created_at=now - timedelta(days=90)),
        # soft-deleted → must be excluded from every metric
        project(e, "PRJ-E", "active", 3, 9999.0, 9999.0, is_deleted=True),
    ])

    await db.stage_instances.insert_many([
        {"project_id": a, "stage_order": 3, "stage_key": "stage_3",
         "status": "in_progress", "entered_at": now - timedelta(days=10)},
        {"project_id": b, "stage_order": 3, "stage_key": "stage_3",
         "status": "waiting", "entered_at": now - timedelta(days=20)},
        {"project_id": c, "stage_order": 5, "stage_key": "stage_5",
         "status": "on_hold", "entered_at": now - timedelta(days=8)},
    ])

    await db.reports.insert_many([
        {"project_id": a, "type": "ncr", "status": "open", "is_deleted": False,
         "created_at": now},
        {"project_id": b, "type": "rfi", "status": "in_progress",
         "is_deleted": False, "created_at": now},
        {"project_id": a, "type": "issue", "status": "resolved",  # excluded
         "is_deleted": False, "created_at": now},
    ])

    await db.job_costs.insert_many([
        {"project_id": a, "cost_type": "labor", "amount": 100.0, "is_deleted": False},
        {"project_id": a, "cost_type": "material", "amount": 50.0, "is_deleted": False},
    ])


async def test_analytics_kpis_and_charts(client_client, onboarded_company):
    await _seed_portfolio(_tenant_db(onboarded_company))

    res = await client_client.get("/api/v1/projects/analytics")
    assert res.status_code == 200, res.text
    data = res.json()["data"]

    # --- KPI row -------------------------------------------------------------
    k = data["kpis"]
    assert k["active"] == 2                       # A, B (C on_hold, D done, E deleted)
    assert k["on_hold_blocked"] == 2              # B (stage waiting) + C (status)
    assert k["overdue"] == 1                       # B only (past delivery, still live)
    assert k["open_exceptions"] == 2              # ncr open + rfi in_progress
    assert k["budget"]["planned"] == 4300.0       # 1000+500+2000+800 (E excluded)
    assert k["budget"]["actual"] == 2650.0        # 200+100+1500+850
    assert k["budget"]["variance"] == -1650.0

    # --- charts (present at READ; owner is WRITE) ----------------------------
    by_stage = {row["order"]: row for row in data["by_stage"]}
    assert len(data["by_stage"]) == 9             # a full funnel, zeros included
    assert by_stage[3]["count"] == 2              # A, B are the only actives
    assert by_stage[5]["count"] == 0              # C is on_hold, not active
    assert all("label" in row for row in data["by_stage"])

    tis = {row["order"]: row for row in data["time_in_stage"]}
    assert set(tis) == {3}                         # only stage 3 holds actives
    assert tis[3]["count"] == 2
    assert abs(tis[3]["avg_days"] - 15.0) < 0.3   # (10 + 20) / 2

    cost = {row["cost_type"]: row["amount"] for row in data["budget"]["cost_by_type"]}
    assert cost == {"labor": 100.0, "material": 50.0,
                    "subcontractor": 0.0, "machine": 0.0}
    top = data["budget"]["top_projects"]
    assert top[0]["code"] == "PRJ-C" and top[0]["planned"] == 2000.0  # biggest planned

    exc = data["exceptions"]
    assert exc == [
        {"type": "ncr", "open": 1, "in_progress": 0, "total": 1},
        {"type": "rfi", "open": 0, "in_progress": 1, "total": 1},
    ]

    assert len(data["throughput"]) == 6
    assert sum(m["started"] for m in data["throughput"]) == 4   # A,B,C,D (E deleted)
    assert sum(m["completed"] for m in data["throughput"]) == 1  # D


async def _set_owner_analytics(db, level: int) -> None:
    await db.roles.update_one(
        {"name": "Owner"}, {"$set": {"permissions.projects_analytics": level}}
    )


async def test_analytics_rbac_tiers(client_client, onboarded_company):
    """Role is re-evaluated per request, so flipping the Owner's level changes the
    payload live: READ→full, VIEW→KPIs only, NONE→403."""
    db = _tenant_db(onboarded_company)
    await _seed_portfolio(db)

    # Owner default is WRITE (>= READ) → full payload.
    res = await client_client.get("/api/v1/projects/analytics")
    assert res.status_code == 200
    assert "by_stage" in res.json()["data"]

    # VIEW → KPI row only, every chart block absent (not null).
    await _set_owner_analytics(db, 1)
    data = (await client_client.get("/api/v1/projects/analytics")).json()["data"]
    assert set(data) == {"kpis"}
    assert "budget" in data["kpis"]  # budget variance is a KPI, still present

    # NONE → the endpoint guard rejects before any work.
    await _set_owner_analytics(db, 0)
    res = await client_client.get("/api/v1/projects/analytics")
    assert res.status_code == 403
