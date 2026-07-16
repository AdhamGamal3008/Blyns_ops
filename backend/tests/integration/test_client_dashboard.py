"""Client Dashboard acceptance criteria (docs/modules/CLIENT_DASHBOARD.md §6):
quick actions = exactly the role's WRITE set; calendar merges READ-permitted
modules only; activity respects module read permissions."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.core.db import get_db_manager
from app.core.security import hash_password
from app.modules.settings.seed import CLIENT_RESOURCES


async def _login_headers(client, slug: str, email: str, password: str) -> dict:
    res = await client.post("/api/v1/auth/login", json={
        "company": slug, "email": email, "password": password,
    })
    assert res.status_code == 200, res.text
    return {"Authorization": f"Bearer {res.json()['data']['access_token']}"}


async def _make_user(tenant_db, slug: str, name: str, levels: dict[str, int]) -> dict:
    now = datetime.now(UTC)
    role_id = (await tenant_db.roles.insert_one({
        "name": f"{name}-role",
        "permissions": {r: levels.get(r, 0) for r in CLIENT_RESOURCES},
        "created_at": now, "updated_at": now,
    })).inserted_id
    email = f"{name}@{slug}.com"
    await tenant_db.users.insert_one({
        "email": email, "password_hash": hash_password("DashPass123!"),
        "name": name, "role_id": role_id,
        "is_blocked": False, "failed_attempts": 0, "locked_until": None,
        "must_reset_password": False, "last_login_at": None, "refresh_jtis": [],
        "created_at": now, "updated_at": now,
    })
    return {"email": email, "password": "DashPass123!", "role_id": role_id}


async def test_quick_actions_match_write_permissions(client, client_client, onboarded_company):
    # Owner (WRITE everything): all five actions
    res = await client_client.get("/api/v1/dashboard/quick-actions")
    assert res.status_code == 200
    assert {a["key"] for a in res.json()["data"]} == {
        "project.new", "crm.lead.new", "inventory.adjust",
        "finance.invoice.new", "employee.invite",
    }

    # custom role: WRITE crm only, READ dashboard
    tenant_db = get_db_manager().tenant(onboarded_company["company"]["db_name"])
    user = await _make_user(tenant_db, onboarded_company["slug"], "crmwriter",
                            {"dashboard": 2, "crm": 3})
    headers = await _login_headers(
        client, onboarded_company["slug"], user["email"], user["password"]
    )
    res = await client.get("/api/v1/dashboard/quick-actions", headers=headers)
    assert {a["key"] for a in res.json()["data"]} == {"crm.lead.new"}


async def test_kpis_respect_module_read_and_report_values(client, client_client, onboarded_company):
    tenant_db = get_db_manager().tenant(onboarded_company["company"]["db_name"])
    now = datetime.now(UTC)

    # seed data across modules
    await tenant_db.projects.insert_one({
        "name": "P1", "status": "active",
        "milestone_schedule": [
            {"key": "m1", "name": "Late milestone", "due_date": now - timedelta(days=2)},
        ],
    })
    await tenant_db.deals.insert_many([
        {"title": "D1", "stage": "proposal"},
        {"title": "D2", "stage": "won"},
    ])
    product_id = (await tenant_db.products.insert_one({
        "sku": "SKU-1", "name": "Panel", "is_active": True, "reorder_point": 5,
    })).inserted_id
    await tenant_db.stock_levels.insert_one({
        "product_id": product_id, "warehouse_id": None, "on_hand": 3,
    })
    await tenant_db.invoices.insert_one({
        "number": "INV-0001", "status": "sent", "total": 250.0, "paid_amount": 100.0,
        "due_date": now + timedelta(days=10),
    })

    # Owner: all KPIs present with the right values
    res = await client_client.get("/api/v1/dashboard/kpis")
    data = res.json()["data"]
    assert data["open_projects"] == 1
    assert data["overdue_tasks"] == 1
    assert data["open_deals"] == 1          # 'won' excluded
    assert data["low_stock_items"] == 1     # 3 <= reorder 5
    assert data["unpaid_invoices_total"] == 150.0

    # crm-only READ user: only open_deals
    user = await _make_user(tenant_db, onboarded_company["slug"], "kpicrm",
                            {"dashboard": 2, "crm": 2})
    headers = await _login_headers(
        client, onboarded_company["slug"], user["email"], user["password"]
    )
    res = await client.get("/api/v1/dashboard/kpis", headers=headers)
    assert res.json()["data"] == {"open_deals": 1}


async def test_calendar_merges_read_modules_and_excludes_others(
    client, client_client, onboarded_company
):
    tenant_db = get_db_manager().tenant(onboarded_company["company"]["db_name"])
    now = datetime.now(UTC)
    in_range = now + timedelta(days=5)

    await tenant_db.projects.insert_one({
        "name": "P2", "status": "active",
        "milestone_schedule": [{"key": "kick", "name": "Kickoff", "due_date": in_range}],
    })
    await tenant_db.deals.insert_one({
        "title": "Big deal", "stage": "negotiation", "expected_close_date": in_range,
    })
    await tenant_db.invoices.insert_one({
        "number": "INV-0002", "status": "sent", "total": 10.0, "paid_amount": 0.0,
        "due_date": in_range,
    })
    await tenant_db.calendar_events.insert_one({
        "title": "All-hands", "start": in_range, "end": None, "all_day": True,
        "visibility": "company", "created_by": "someone",
    })

    frm = now.date().isoformat()
    to = (now + timedelta(days=20)).date().isoformat()

    # Owner READs everything → union of all four sources
    res = await client_client.get(f"/api/v1/calendar?from={frm}&to={to}")
    types = {e["type"] for e in res.json()["data"]}
    assert {"milestone", "deal_close", "invoice_due", "company_event"} <= types
    ev = res.json()["data"][0]
    assert set(ev) >= {"id", "source_module", "type", "title", "start",
                       "all_day", "entity_ref", "color_key"}

    # crm-READ-only user: deal_close only — no projects/finance/settings leak
    user = await _make_user(tenant_db, onboarded_company["slug"], "calcrm",
                            {"dashboard": 2, "calendar": 2, "crm": 2})
    headers = await _login_headers(
        client, onboarded_company["slug"], user["email"], user["password"]
    )
    res = await client.get(f"/api/v1/calendar?from={frm}&to={to}", headers=headers)
    assert {e["source_module"] for e in res.json()["data"]} == {"crm"}

    # window cap
    far = (now + timedelta(days=200)).date().isoformat()
    res = await client_client.get(f"/api/v1/calendar?from={frm}&to={far}")
    assert res.status_code == 422


async def test_activity_feed_respects_permissions_and_reflects_actions(
    client, client_client, onboarded_company
):
    tenant_db = get_db_manager().tenant(onboarded_company["company"]["db_name"])
    now = datetime.now(UTC)
    await tenant_db.activity_log.insert_many([
        {"actor_id": "u1", "actor_name": "A", "action": "crm.deal.created",
         "module": "crm", "entity": {"type": "deal", "id": "x", "label": "D"},
         "occurred_at": now, "details": {}},
        {"actor_id": "u1", "actor_name": "A", "action": "finance.invoice.sent",
         "module": "finance", "entity": {"type": "invoice", "id": "y", "label": "I"},
         "occurred_at": now, "details": {}},
    ])

    # Owner sees both modules + their own auth.login (just-performed action)
    res = await client_client.get("/api/v1/activity?page_size=50")
    actions = [e["action"] for e in res.json()["data"]]
    assert "crm.deal.created" in actions
    assert "finance.invoice.sent" in actions
    assert "auth.login" in actions  # acceptance #3: reflected within a poll

    # activity READ but crm=NONE → no CRM entries, finance still visible
    user = await _make_user(tenant_db, onboarded_company["slug"], "nofinance",
                            {"dashboard": 2, "activity": 2, "finance": 2})
    headers = await _login_headers(
        client, onboarded_company["slug"], user["email"], user["password"]
    )
    res = await client.get("/api/v1/activity?page_size=50", headers=headers)
    actions = [e["action"] for e in res.json()["data"]]
    assert "finance.invoice.sent" in actions
    assert "crm.deal.created" not in actions

    # explicit module filter for a NONE module returns nothing
    res = await client.get("/api/v1/activity?module=crm", headers=headers)
    assert res.json()["data"] == []

    # Viewer role (no activity permission) is denied outright
    viewer = await _make_user(tenant_db, onboarded_company["slug"], "viewer2",
                              {"dashboard": 2, "calendar": 2})
    headers = await _login_headers(
        client, onboarded_company["slug"], viewer["email"], viewer["password"]
    )
    res = await client.get("/api/v1/activity", headers=headers)
    assert res.status_code == 403


async def test_activity_cursor_pagination(client_client, onboarded_company):
    tenant_db = get_db_manager().tenant(onboarded_company["company"]["db_name"])
    now = datetime.now(UTC)
    await tenant_db.activity_log.insert_many([
        {"actor_id": "u", "actor_name": "A", "action": f"projects.item.{i}",
         "module": "projects", "entity": {}, "occurred_at": now, "details": {}}
        for i in range(7)
    ])
    res = await client_client.get("/api/v1/activity?page_size=5")
    body = res.json()
    assert len(body["data"]) == 5
    cursor = body["meta"]["next_cursor"]
    assert cursor
    res = await client_client.get(f"/api/v1/activity?page_size=5&cursor={cursor}")
    ids_page2 = {e["id"] for e in res.json()["data"]}
    assert ids_page2.isdisjoint({e["id"] for e in body["data"]})
