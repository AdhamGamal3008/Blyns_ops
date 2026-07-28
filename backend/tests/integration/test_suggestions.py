"""Dashboard "next step" suggestions (docs/QUICK_ACTIONS_PERSONALIZATION_PLAN.md
Phase 3): data-state rules the caller may act on, priority-ordered, capped, and
dismissible per-user (dismissal re-surfaces once its signal grows or the TTL
lapses). Permissions stay the hard gate."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from tests.integration.test_quick_actions import FULL, _user_with


async def _seed_overdue(db):
    await db.projects.insert_one({
        "name": "P", "status": "active",
        "milestone_schedule": [
            {"key": "m", "name": "Late", "due_date": datetime.now(UTC) - timedelta(days=1)},
        ],
    })


async def _seed_drafts(db, n=1):
    await db.invoices.insert_many([{"status": "draft", "number": f"DFT-{i}"} for i in range(n)])


async def _seed_unpaid(db, n=1):
    await db.invoices.insert_many([{"status": "sent", "number": f"UNP-{i}"} for i in range(n)])


async def _seed_new_leads(db, n=1):
    await db.leads.insert_many([{"status": "new", "name": f"Lead {i}"} for i in range(n)])


async def _keys(client, headers) -> list[str]:
    res = await client.get("/api/v1/dashboard/suggestions", headers=headers)
    assert res.status_code == 200, res.text
    return [s["key"] for s in res.json()["data"]]


async def _dismiss(client, headers, key):
    return await client.post(f"/api/v1/dashboard/suggestions/{key}/dismiss", headers=headers)


async def test_no_suggestions_when_nothing_needs_attention(client, onboarded_company):
    _, headers, _ = await _user_with(client, onboarded_company, "calm", FULL)
    assert await _keys(client, headers) == []


async def test_draft_invoices_raise_a_suggestion(client, onboarded_company):
    tenant_db, headers, _ = await _user_with(client, onboarded_company, "drafts", FULL)
    await _seed_drafts(tenant_db, 2)
    res = await client.get("/api/v1/dashboard/suggestions", headers=headers)
    draft = next(s for s in res.json()["data"] if s["key"] == "finance.draft_invoices")
    assert "2 draft invoices" in draft["message"]
    assert draft["target_route"] == "/app/finance/invoices"
    assert draft["cta_label"] == "Review drafts"
    assert "signal" not in draft  # internal bookkeeping stays server-side


async def test_permission_gate_blocks_a_suggestion(client, onboarded_company):
    # crm-only WRITE: even with draft invoices present, no finance suggestion
    tenant_db, headers, _ = await _user_with(
        client, onboarded_company, "crmonly", {"dashboard": 2, "crm": 3})
    await _seed_drafts(tenant_db, 3)
    assert not any(k.startswith("finance") for k in await _keys(client, headers))


async def test_suggestions_are_priority_ordered_and_capped(client, onboarded_company):
    tenant_db, headers, _ = await _user_with(client, onboarded_company, "busy", FULL)
    await _seed_overdue(tenant_db)       # priority 100
    await _seed_drafts(tenant_db, 1)     # 80
    await _seed_new_leads(tenant_db, 1)  # 70
    await _seed_unpaid(tenant_db, 1)     # 60
    # capped at 3, highest priority first; unpaid (lowest) drops off
    assert await _keys(client, headers) == [
        "projects.overdue", "finance.draft_invoices", "crm.new_leads",
    ]


async def test_dismiss_hides_a_suggestion(client, onboarded_company):
    tenant_db, headers, _ = await _user_with(client, onboarded_company, "dismisser", FULL)
    await _seed_new_leads(tenant_db, 2)
    assert "crm.new_leads" in await _keys(client, headers)
    res = await _dismiss(client, headers, "crm.new_leads")
    assert res.status_code == 200, res.text
    assert "crm.new_leads" not in [s["key"] for s in res.json()["data"]]
    assert "crm.new_leads" not in await _keys(client, headers)


async def test_dismissed_suggestion_returns_when_signal_grows(client, onboarded_company):
    tenant_db, headers, _ = await _user_with(client, onboarded_company, "growth", FULL)
    await _seed_new_leads(tenant_db, 2)
    await _dismiss(client, headers, "crm.new_leads")
    assert "crm.new_leads" not in await _keys(client, headers)  # still 2 → stays hidden
    await _seed_new_leads(tenant_db, 1)  # now 3 > the dismissed 2
    assert "crm.new_leads" in await _keys(client, headers)


async def test_dismissal_expires_after_the_ttl(client, onboarded_company):
    tenant_db, headers, actor_id = await _user_with(client, onboarded_company, "stale", FULL)
    await _seed_new_leads(tenant_db, 2)
    await _dismiss(client, headers, "crm.new_leads")
    assert "crm.new_leads" not in await _keys(client, headers)
    # age the dismissal past the TTL (default 14d) → it resurfaces even unchanged
    await tenant_db.suggestion_dismissals.update_one(
        {"actor_id": actor_id},
        {"$set": {"entries.$[e].at": datetime.now(UTC) - timedelta(days=15)}},
        array_filters=[{"e.key": "crm.new_leads"}],
    )
    assert "crm.new_leads" in await _keys(client, headers)


async def test_dismiss_rejects_an_unknown_key(client, onboarded_company):
    _, headers, _ = await _user_with(client, onboarded_company, "bogus", FULL)
    res = await _dismiss(client, headers, "not.a.suggestion")
    assert res.status_code == 422


async def test_dismiss_is_audited(client, onboarded_company):
    tenant_db, headers, actor_id = await _user_with(client, onboarded_company, "auditsug", FULL)
    await _seed_new_leads(tenant_db, 1)
    await _dismiss(client, headers, "crm.new_leads")
    logged = await tenant_db.activity_log.find_one(
        {"actor_id": actor_id, "action": "dashboard.suggestion.dismissed"})
    assert logged is not None
    assert logged["module"] == "dashboard"
    assert logged["details"]["suggestion"] == "crm.new_leads"
