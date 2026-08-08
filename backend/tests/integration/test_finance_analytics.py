"""Finance Analytics/Overview endpoint (docs/PROJECT_ANALYTICS_PLAN.md §6-D).

Seeds invoices (AR) + bills (AP) with the exact fields the service writes and
asserts every KPI and chart, plus the RBAC tiering.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.core.db import get_db_manager


def _tenant_db(onboarded_company):
    return get_db_manager().tenant(onboarded_company["company"]["db_name"])


async def _seed(db) -> None:
    now = datetime.now(UTC)

    def doc(number, status, total, paid, issue_days, due_days):
        return {
            "number": number, "status": status, "total": total,
            "paid_amount": paid, "is_deleted": False,
            "issue_date": now - timedelta(days=issue_days),
            "due_date": now + timedelta(days=due_days),
        }

    await db.invoices.insert_many([
        doc("INV-1", "sent", 1000.0, 0.0, 40, -10),        # overdue → 1–30
        doc("INV-2", "partly_paid", 2000.0, 500.0, 20, 20),  # current, outstanding 1500
        doc("INV-3", "paid", 3000.0, 3000.0, 30, -5),       # outstanding 0
        doc("INV-4", "draft", 500.0, 0.0, 5, 30),           # not issued
        doc("INV-5", "void", 9999.0, 0.0, 5, 30),           # not revenue
    ])

    await db.bills.insert_many([
        doc("BILL-1", "sent", 400.0, 0.0, 15, -5),   # AP outstanding 400
        doc("BILL-2", "paid", 600.0, 600.0, 10, -2),  # outstanding 0
        doc("BILL-3", "draft", 100.0, 0.0, 5, 20),    # not an expense
    ])


async def test_finance_analytics_kpis_and_charts(client_client, onboarded_company):
    await _seed(_tenant_db(onboarded_company))

    res = await client_client.get("/api/v1/finance/analytics")
    assert res.status_code == 200, res.text
    data = res.json()["data"]

    k = data["kpis"]
    assert k["revenue"] == 6000.0        # sent 1000 + partly 2000 + paid 3000
    assert k["expenses"] == 1000.0       # sent 400 + paid 600 (draft excluded)
    assert k["ar_outstanding"] == 2500.0  # 1000 + 1500 (paid has none)
    assert k["ap_outstanding"] == 400.0
    assert k["overdue_ar"] == 1000.0     # INV-1 only (INV-2 not yet due)

    inv = {r["status"]: r["amount"] for r in data["invoices_by_status"]}
    assert len(data["invoices_by_status"]) == 5
    assert inv["Sent"] == 1000.0 and inv["Void"] == 9999.0
    assert inv["Partly paid"] == 2000.0

    bills = {r["status"]: r["amount"] for r in data["bills_by_status"]}
    assert bills["Sent"] == 400.0 and bills["Paid"] == 600.0

    aging = {r["bucket"]: r["amount"] for r in data["ar_aging"]}
    assert aging["Current"] == 1500.0   # INV-2 (future due)
    assert aging["1–30"] == 1000.0      # INV-1 (10 days overdue)
    assert [r["bucket"] for r in data["ar_aging"]] == \
        ["Current", "1–30", "31–60", "61–90", "90+"]

    assert len(data["top_overdue"]) == 1
    assert data["top_overdue"][0]["number"] == "INV-1"
    assert data["top_overdue"][0]["outstanding"] == 1000.0

    assert len(data["cashflow"]) == 6
    assert sum(m["revenue"] for m in data["cashflow"]) == 6000.0
    assert sum(m["expenses"] for m in data["cashflow"]) == 1000.0


async def _set_owner_fin_analytics(db, level: int) -> None:
    await db.roles.update_one(
        {"name": "Owner"}, {"$set": {"permissions.finance_analytics": level}}
    )


async def test_finance_analytics_rbac_tiers(client_client, onboarded_company):
    db = _tenant_db(onboarded_company)
    await _seed(db)

    res = await client_client.get("/api/v1/finance/analytics")  # Owner WRITE → full
    assert res.status_code == 200
    assert "invoices_by_status" in res.json()["data"]

    await _set_owner_fin_analytics(db, 1)  # VIEW → KPIs only
    data = (await client_client.get("/api/v1/finance/analytics")).json()["data"]
    assert set(data) == {"kpis"}

    await _set_owner_fin_analytics(db, 0)  # NONE → 403
    assert (await client_client.get("/api/v1/finance/analytics")).status_code == 403
