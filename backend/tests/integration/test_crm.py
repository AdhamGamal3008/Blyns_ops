"""CRM module acceptance criteria (docs/modules/CRM.md §6): lead conversion,
the `lost` reason rule, pipeline buckets, and crm=NONE lockout."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta


async def _lead(client_client, name: str = "Hank Scorpio", **extra) -> dict:
    res = await client_client.post("/api/v1/crm/leads", json={
        "name": name, "email": "hank@globex.test", "phone": "555-0100",
        "source": "referral", **extra,
    })
    assert res.status_code == 201, res.text
    return res.json()["data"]


async def _deal(client_client, title: str, stage: str = "new", amount: float = 0) -> dict:
    res = await client_client.post("/api/v1/crm/deals", json={
        "title": title, "stage": stage, "amount": amount,
    })
    assert res.status_code == 201, res.text
    return res.json()["data"]


# --- acceptance #1: lead conversion ------------------------------------------

async def test_convert_lead_links_account_contact_deal(client_client):
    lead = await _lead(client_client)
    assert lead["status"] == "new"
    assert lead["converted_to"] == {
        "account_id": None, "contact_id": None, "deal_id": None,
    }

    close = (datetime.now(UTC) + timedelta(days=30)).isoformat()
    res = await client_client.post(f"/api/v1/crm/leads/{lead['id']}/convert", json={
        "account_name": "Globex Corp", "deal_title": "Globex rollout",
        "amount": 25000, "expected_close_date": close,
    })
    assert res.status_code == 201, res.text
    data = res.json()["data"]

    # the lead is marked converted and stamped with all three links
    assert data["lead"]["status"] == "converted"
    stamped = data["lead"]["converted_to"]
    assert stamped["account_id"] == data["account"]["id"]
    assert stamped["contact_id"] == data["contact"]["id"]
    assert stamped["deal_id"] == data["deal"]["id"]

    # and the three records are linked to each other
    assert data["account"]["name"] == "Globex Corp"
    assert data["contact"]["account_id"] == data["account"]["id"]
    assert data["contact"]["first_name"] == "Hank"
    assert data["contact"]["last_name"] == "Scorpio"
    assert data["contact"]["email"] == "hank@globex.test"
    assert data["deal"]["account_id"] == data["account"]["id"]
    assert data["deal"]["contact_id"] == data["contact"]["id"]
    assert data["deal"]["amount"] == 25000
    assert data["deal"]["stage"] == "new"

    # converting twice is rejected
    res = await client_client.post(f"/api/v1/crm/leads/{lead['id']}/convert", json={})
    assert res.status_code == 409


async def test_convert_lead_can_link_existing_account(client_client):
    res = await client_client.post("/api/v1/crm/accounts", json={"name": "Acme Existing"})
    account_id = res.json()["data"]["id"]
    lead = await _lead(client_client, name="Jane Prospect")

    res = await client_client.post(f"/api/v1/crm/leads/{lead['id']}/convert", json={
        "account_id": account_id,
    })
    assert res.status_code == 201
    data = res.json()["data"]
    assert data["account"]["id"] == account_id
    assert data["contact"]["account_id"] == account_id

    # no duplicate account was created
    res = await client_client.get("/api/v1/crm/accounts", params={"q": "Acme Existing"})
    assert res.json()["meta"]["total"] == 1


async def test_converted_lead_is_frozen(client_client):
    lead = await _lead(client_client, name="Frozen Lead")
    await client_client.post(f"/api/v1/crm/leads/{lead['id']}/convert", json={})
    res = await client_client.patch(f"/api/v1/crm/leads/{lead['id']}",
                                    json={"source": "web"})
    assert res.status_code == 409


async def test_convert_writes_activity_log(client_client):
    lead = await _lead(client_client, name="Logged Lead")
    await client_client.post(f"/api/v1/crm/leads/{lead['id']}/convert", json={})
    res = await client_client.get("/api/v1/activity", params={"module": "crm"})
    actions = [a["action"] for a in res.json()["data"]]
    assert "crm.lead.converted" in actions


# --- acceptance #2: `lost` requires a reason ---------------------------------

async def test_deal_lost_without_reason_is_rejected(client_client):
    deal = await _deal(client_client, "Big fish")

    res = await client_client.patch(f"/api/v1/crm/deals/{deal['id']}/stage",
                                    json={"stage": "lost"})
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "VALIDATION_ERROR"

    # blank reason is not a reason either
    res = await client_client.patch(f"/api/v1/crm/deals/{deal['id']}/stage",
                                    json={"stage": "lost", "lost_reason": "   "})
    assert res.status_code == 422

    # with a reason it goes through and is recorded
    res = await client_client.patch(f"/api/v1/crm/deals/{deal['id']}/stage",
                                    json={"stage": "lost", "lost_reason": "price"})
    assert res.status_code == 200
    assert res.json()["data"]["stage"] == "lost"
    assert res.json()["data"]["lost_reason"] == "price"

    res = await client_client.get("/api/v1/activity", params={"module": "crm"})
    entry = next(a for a in res.json()["data"] if a["action"] == "crm.deal.stage_changed")
    assert entry["details"]["from"] == "new"
    assert entry["details"]["to"] == "lost"


async def test_creating_a_lost_deal_needs_a_reason(client_client):
    res = await client_client.post("/api/v1/crm/deals", json={
        "title": "Born lost", "stage": "lost",
    })
    assert res.status_code == 422


async def test_terminal_stages_cannot_be_reopened(client_client):
    deal = await _deal(client_client, "Closed won")
    res = await client_client.patch(f"/api/v1/crm/deals/{deal['id']}/stage",
                                    json={"stage": "won"})
    assert res.status_code == 200
    assert res.json()["data"]["probability_pct"] == 100

    res = await client_client.patch(f"/api/v1/crm/deals/{deal['id']}/stage",
                                    json={"stage": "negotiation"})
    assert res.status_code == 409


# --- acceptance #3: pipeline buckets -----------------------------------------

async def test_pipeline_returns_stage_buckets_with_counts_and_sums(client_client):
    await _deal(client_client, "A", stage="new", amount=1000)
    await _deal(client_client, "B", stage="new", amount=2500)
    await _deal(client_client, "C", stage="proposal", amount=4000)

    res = await client_client.get("/api/v1/crm/pipeline")
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["pipeline"] == "default"

    buckets = {s["stage"]: s for s in data["stages"]}
    # every seeded stage is present, even empty ones
    assert list(buckets) == ["new", "qualified", "proposal", "negotiation", "won", "lost"]
    assert buckets["new"]["count"] == 2
    assert buckets["new"]["amount"] == 3500
    assert buckets["proposal"]["count"] == 1
    assert buckets["proposal"]["amount"] == 4000
    assert buckets["qualified"]["count"] == 0
    assert buckets["qualified"]["amount"] == 0
    assert buckets["won"]["is_terminal"] is True
    assert data["open_value"] == 7500


async def test_pipeline_counts_deals_written_without_a_pipeline_field(
    client_client, onboarded_company
):
    """A deal doc with no `pipeline` (ad-hoc/legacy insert) still belongs to the
    default pipeline. Regression: the board listed such a deal in its stage
    column while the bucket counted 0, so the totals contradicted the cards."""
    from app.core.db import get_db_manager

    tenant_db = get_db_manager().tenant(onboarded_company["company"]["db_name"])
    await tenant_db.deals.insert_one({
        "title": "Legacy bid", "stage": "proposal", "amount": 84000,
        "pipeline": None, "is_deleted": None,
    })

    res = await client_client.get("/api/v1/crm/pipeline")
    buckets = {s["stage"]: s for s in res.json()["data"]["stages"]}
    assert buckets["proposal"]["count"] == 1
    assert buckets["proposal"]["amount"] == 84000
    assert res.json()["data"]["open_value"] == 84000

    # and the deals list scoped to that pipeline returns the very same deal
    res = await client_client.get("/api/v1/crm/deals", params={"pipeline": "default"})
    assert [d["title"] for d in res.json()["data"]] == ["Legacy bid"]


async def test_pipeline_excludes_deleted_and_counts_terminal_separately(client_client):
    gone = await _deal(client_client, "Deleted", stage="new", amount=999)
    await client_client.delete(f"/api/v1/crm/deals/{gone['id']}")
    won = await _deal(client_client, "Won deal", stage="new", amount=5000)
    await client_client.patch(f"/api/v1/crm/deals/{won['id']}/stage", json={"stage": "won"})

    res = await client_client.get("/api/v1/crm/pipeline")
    buckets = {s["stage"]: s for s in res.json()["data"]["stages"]}
    assert buckets["new"]["count"] == 0          # soft-deleted deal is gone
    assert buckets["won"]["count"] == 1
    assert res.json()["data"]["open_value"] == 0  # won is not open pipeline value


# --- acceptance #4: crm=NONE is locked out -----------------------------------

async def _limited_client(
    client, client_client, onboarded_company, perms: dict, who: str,
    csv_access: dict | None = None,
):
    """Create a role with `perms` (and optional per-tab `csv_access` grants),
    attach a fresh employee, return their client."""
    body: dict = {"name": f"role-{who}", "permissions": perms}
    if csv_access is not None:
        body["csv_access"] = csv_access
    res = await client_client.post("/api/v1/settings/roles", json=body)
    role_id = res.json()["data"]["id"]
    email = f"{who}@{onboarded_company['slug']}.com"
    res = await client_client.post("/api/v1/settings/employees", json={
        "name": who, "email": email, "role_id": role_id,
    })
    temp_pw = res.json()["data"]["temp_password"]

    login = {"company": onboarded_company["slug"], "email": email}
    first = await client.post("/api/v1/auth/login", json={**login, "password": temp_pw})
    headers = {"Authorization": f"Bearer {first.json()['data']['access_token']}"}
    await client.post("/api/v1/auth/change-password", headers=headers, json={
        "current_password": temp_pw, "new_password": "LimitedPass1!",
    })
    res = await client.post("/api/v1/auth/login",
                            json={**login, "password": "LimitedPass1!"})
    return {"Authorization": f"Bearer {res.json()['data']['access_token']}"}


async def test_crm_none_denied_on_all_routes(client, client_client, onboarded_company):
    headers = await _limited_client(
        client, client_client, onboarded_company,
        {"dashboard": 2, "calendar": 2, "activity": 2}, "nocrm",
    )
    routes = [
        ("get", "/api/v1/crm/accounts"), ("get", "/api/v1/crm/contacts"),
        ("get", "/api/v1/crm/leads"), ("get", "/api/v1/crm/deals"),
        ("get", "/api/v1/crm/activities"), ("get", "/api/v1/crm/pipeline"),
    ]
    for method, path in routes:
        res = await getattr(client, method)(path, headers=headers)
        assert res.status_code == 403, f"{path} → {res.status_code}"
        assert res.json()["error"]["code"] == "PERMISSION_DENIED"

    # writes too
    res = await client.post("/api/v1/crm/leads", headers=headers, json={"name": "X"})
    assert res.status_code == 403


async def test_crm_read_cannot_write(client, client_client, onboarded_company):
    headers = await _limited_client(
        client, client_client, onboarded_company,
        {"dashboard": 2, "crm": 2}, "readcrm",
    )
    assert (await client.get("/api/v1/crm/deals", headers=headers)).status_code == 200
    res = await client.post("/api/v1/crm/leads", headers=headers, json={"name": "X"})
    assert res.status_code == 403


async def test_crm_none_sees_no_crm_calendar_or_activity(
    client, client_client, onboarded_company
):
    """Acceptance #4 second half: no CRM activity/calendar entries leak."""
    close = datetime.now(UTC) + timedelta(days=3)
    await client_client.post("/api/v1/crm/deals", json={
        "title": "Secret deal", "amount": 100,
        "expected_close_date": close.isoformat(),
    })

    headers = await _limited_client(
        client, client_client, onboarded_company,
        {"dashboard": 2, "calendar": 2, "activity": 2}, "blindcrm",
    )
    frm = (close - timedelta(days=7)).date().isoformat()
    to = (close + timedelta(days=7)).date().isoformat()

    res = await client.get("/api/v1/calendar", headers=headers,
                           params={"from": frm, "to": to})
    assert res.status_code == 200
    assert all(e["source_module"] != "crm" for e in res.json()["data"])

    res = await client.get("/api/v1/activity", headers=headers)
    assert res.status_code == 200
    assert all(a["module"] != "crm" for a in res.json()["data"])

    # the owner (crm WRITE) does see both
    res = await client_client.get("/api/v1/calendar", params={"from": frm, "to": to})
    assert any(e["source_module"] == "crm" for e in res.json()["data"])


# --- calendar contribution (§5) ----------------------------------------------

async def test_deal_close_and_activity_due_feed_the_calendar(client_client):
    close = datetime.now(UTC) + timedelta(days=5)
    deal = await _deal(client_client, "Calendar deal")
    await client_client.patch(f"/api/v1/crm/deals/{deal['id']}", json={
        "expected_close_date": close.isoformat(),
    })
    res = await client_client.post("/api/v1/crm/activities", json={
        "entity_ref": {"type": "deal", "id": deal["id"]},
        "type": "task", "subject": "Send proposal",
        "due_at": close.isoformat(),
    })
    assert res.status_code == 201
    activity_id = res.json()["data"]["id"]

    frm = (close - timedelta(days=1)).date().isoformat()
    to = (close + timedelta(days=1)).date().isoformat()
    res = await client_client.get("/api/v1/calendar", params={"from": frm, "to": to})
    types = {e["type"] for e in res.json()["data"] if e["source_module"] == "crm"}
    assert {"deal_close", "task_due"} <= types

    # a soft-deleted activity drops off the calendar
    await client_client.delete(f"/api/v1/crm/activities/{activity_id}")
    res = await client_client.get("/api/v1/calendar", params={"from": frm, "to": to})
    types = {e["type"] for e in res.json()["data"] if e["source_module"] == "crm"}
    assert "task_due" not in types
    assert "deal_close" in types


async def test_open_deals_kpi_reflects_crm(client_client):
    before = (await client_client.get("/api/v1/dashboard/kpis")).json()["data"]
    open_before = before["open_deals"]

    deal = await _deal(client_client, "KPI deal")
    after = (await client_client.get("/api/v1/dashboard/kpis")).json()["data"]
    assert after["open_deals"] == open_before + 1

    # won is no longer open pipeline
    await client_client.patch(f"/api/v1/crm/deals/{deal['id']}/stage", json={"stage": "won"})
    after = (await client_client.get("/api/v1/dashboard/kpis")).json()["data"]
    assert after["open_deals"] == open_before


async def test_open_deals_kpi_hidden_from_crm_none(client, client_client, onboarded_company):
    headers = await _limited_client(
        client, client_client, onboarded_company, {"dashboard": 2}, "nokpi",
    )
    res = await client.get("/api/v1/dashboard/kpis", headers=headers)
    assert res.status_code == 200
    assert "open_deals" not in res.json()["data"]
    assert "open_deals" in (await client_client.get("/api/v1/dashboard/kpis")).json()["data"]


# --- entity integrity --------------------------------------------------------

async def test_activity_requires_a_live_parent_entity(client_client):
    res = await client_client.post("/api/v1/crm/activities", json={
        "entity_ref": {"type": "deal", "id": "6a57fc000ea6cf67cc8c211a"},
        "type": "note", "subject": "orphan",
    })
    assert res.status_code == 404


async def test_account_with_open_deals_cannot_be_deleted(client_client):
    res = await client_client.post("/api/v1/crm/accounts", json={"name": "Busy Co"})
    account_id = res.json()["data"]["id"]
    res = await client_client.post("/api/v1/crm/deals", json={
        "title": "Open one", "account_id": account_id,
    })
    deal_id = res.json()["data"]["id"]

    res = await client_client.delete(f"/api/v1/crm/accounts/{account_id}")
    assert res.status_code == 409

    await client_client.patch(f"/api/v1/crm/deals/{deal_id}/stage",
                              json={"stage": "lost", "lost_reason": "budget"})
    assert (await client_client.delete(f"/api/v1/crm/accounts/{account_id}")).status_code == 200


async def test_crm_accounts_do_not_collide_with_the_finance_chart(
    client_client, onboarded_company
):
    """CRM's Account (customer) and Finance's Account (chart of accounts) are
    different entities. Regression: both were seeded into `accounts`, whose
    unique `code` index then 500'd the second code-less CRM account, and the
    CRM list rendered ledger rows (Cash, COGS…) as customers."""
    from app.core.db import get_db_manager

    # more than one CRM account in a tenant is fine (they carry no `code`)
    for name in ("Northwind Traders", "Contoso Ltd", "Initech"):
        res = await client_client.post("/api/v1/crm/accounts", json={"name": name})
        assert res.status_code == 201, res.text

    res = await client_client.get("/api/v1/crm/accounts")
    names = {a["name"] for a in res.json()["data"]}
    assert names == {"Northwind Traders", "Contoso Ltd", "Initech"}
    # the ledger never leaks into the CRM list
    assert not names & {"Cash", "Bank", "COGS", "Accounts Receivable"}

    # …and the finance starter chart is untouched in its own collection
    tenant_db = get_db_manager().tenant(onboarded_company["company"]["db_name"])
    assert await tenant_db.accounts.count_documents({}) == 8
    assert await tenant_db.crm_accounts.count_documents({}) == 3


async def test_mine_vs_all_owner_filter(client_client):
    await _deal(client_client, "Mine")
    res = await client_client.get("/api/v1/crm/deals", params={"owner": "mine"})
    assert res.json()["meta"]["total"] >= 1
    all_total = (await client_client.get("/api/v1/crm/deals")).json()["meta"]["total"]
    assert all_total >= res.json()["meta"]["total"]
