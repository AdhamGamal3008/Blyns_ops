"""CRM Analytics/Overview endpoint (docs/PROJECT_ANALYTICS_PLAN.md §6-D).

Seeds a controlled CRM dataset (deals across stages, leads with statuses/sources,
accounts) and asserts every KPI and chart block, plus the RBAC tiering:
READ = KPIs + charts, VIEW = KPIs only, NONE = 403.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.core.db import get_db_manager


def _tenant_db(onboarded_company):
    return get_db_manager().tenant(onboarded_company["company"]["db_name"])


async def _seed(db) -> None:
    now = datetime.now(UTC)

    def deal(title, stage, amount, prob, days, deleted=False):
        return {
            "title": title, "stage": stage, "amount": amount, "probability_pct": prob,
            "pipeline": "default", "is_deleted": deleted,
            "created_at": now - timedelta(days=days),
        }

    await db.deals.insert_many([
        deal("Alpha", "new", 1000.0, 20, 30),
        deal("Bravo", "qualified", 2000.0, 50, 20),
        deal("Charlie", "proposal", 3000.0, 70, 10),
        deal("Delta", "won", 5000.0, 100, 40),
        deal("Echo", "lost", 1500.0, 0, 40),
        deal("Ghost", "new", 9999.0, 90, 5, deleted=True),  # soft-deleted
    ])

    def lead(name, status, source, days, deleted=False):
        return {
            "name": name, "status": status, "source": source, "is_deleted": deleted,
            "created_at": now - timedelta(days=days),
        }

    await db.leads.insert_many([
        lead("L1", "new", "website", 30),
        lead("L2", "contacted", "referral", 20),
        lead("L3", "qualified", "website", 10),
        lead("L4", "converted", "website", 15),
        lead("L5", "unqualified", None, 25),           # no source → Unknown
        lead("L6", "new", "website", 3, deleted=True),  # soft-deleted
    ])

    await db.crm_accounts.insert_many([
        {"name": "A1", "status": "customer", "is_deleted": False},
        {"name": "A2", "status": "customer", "is_deleted": False},
        {"name": "A3", "status": "prospect", "is_deleted": False},
        {"name": "A4", "status": "customer", "is_deleted": True},  # excluded
    ])


async def test_crm_analytics_kpis_and_charts(client_client, onboarded_company):
    await _seed(_tenant_db(onboarded_company))

    res = await client_client.get("/api/v1/crm/analytics")
    assert res.status_code == 200, res.text
    data = res.json()["data"]

    k = data["kpis"]
    assert k["open_deals"] == 3                    # new+qualified+proposal
    assert k["pipeline_value"] == 6000.0           # 1000+2000+3000
    assert k["pipeline_weighted"] == 3300.0        # 1000*.2 + 2000*.5 + 3000*.7
    assert k["win_rate"] == 50.0                    # 1 won / (1 won + 1 lost)
    assert k["open_leads"] == 3                     # new+contacted+qualified
    assert k["customers"] == 2                      # A4 is soft-deleted

    stages = {r["stage"]: r for r in data["pipeline_by_stage"]}
    assert set(stages) == {"new", "qualified", "proposal", "negotiation"}  # open only
    assert stages["proposal"]["amount"] == 3000.0
    assert stages["negotiation"]["count"] == 0

    lead_status = {r["status"]: r["count"] for r in data["lead_status"]}
    assert lead_status == {"new": 1, "contacted": 1, "qualified": 1,
                           "unqualified": 1, "converted": 1}

    sources = {r["source"]: r["count"] for r in data["lead_sources"]}
    assert sources == {"website": 3, "referral": 1, "Unknown": 1}

    top = data["top_deals"]
    assert top[0]["title"] == "Charlie" and top[0]["amount"] == 3000.0  # biggest open
    assert all(d["stage"] in {"new", "qualified", "proposal", "negotiation"} for d in top)

    assert len(data["inflow"]) == 6
    assert sum(m["leads"] for m in data["inflow"]) == 5   # L1..L5 (L6 deleted)
    assert sum(m["deals"] for m in data["inflow"]) == 5   # 5 live deals


async def _set_owner_crm_analytics(db, level: int) -> None:
    await db.roles.update_one(
        {"name": "Owner"}, {"$set": {"permissions.crm_analytics": level}}
    )


async def test_crm_analytics_rbac_tiers(client_client, onboarded_company):
    db = _tenant_db(onboarded_company)
    await _seed(db)

    res = await client_client.get("/api/v1/crm/analytics")  # Owner WRITE → full
    assert res.status_code == 200
    assert "pipeline_by_stage" in res.json()["data"]

    await _set_owner_crm_analytics(db, 1)  # VIEW → KPIs only
    data = (await client_client.get("/api/v1/crm/analytics")).json()["data"]
    assert set(data) == {"kpis"}

    await _set_owner_crm_analytics(db, 0)  # NONE → 403
    assert (await client_client.get("/api/v1/crm/analytics")).status_code == 403
