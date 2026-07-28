"""Quick-action ranking (docs/QUICK_ACTIONS_PERSONALIZATION_PLAN.md — Phase 1).

The order is a pure, deterministic function of (the caller's own recent
activity_log) + (their role) + (named constants). Permissions stay the hard
gate: ranking only reorders actions the user may already take. Cold start (no
recent activity) returns today's curated declaration order.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.core.db import get_db_manager
from app.modules.dashboard.service import QaConfig, _decay, _score
from app.shared.enums import Level
from tests.integration.test_client_dashboard import _login_headers, _make_user

# Full WRITE across every module the onboarded company enables → all nine actions.
FULL = {
    "dashboard": 2, "projects": 3, "crm": 3,
    "inventory": 3, "finance": 3, "settings": 3,
}
CURATED_ORDER = [
    "project.new", "crm.lead.new", "inventory.adjust",
    "finance.invoice.new", "employee.invite", "crm.deal.new",
    "crm.contact.new", "finance.bill.new", "inventory.product.new",
]


def _cfg(**over) -> QaConfig:
    base = dict(
        window_days=30, half_life_days=7.0, w_exact=3.0, w_module=1.0,
        role_write=2.0, role_read=0.5, tie_epsilon=0.001, event_fetch_cap=500,
    )
    base.update(over)
    return QaConfig(**base)


async def _user_with(client, onboarded_company, name: str, levels: dict):
    """Create a client user with the given role, log in, and return
    (tenant_db, auth headers, actor_id-as-stored)."""
    tenant_db = get_db_manager().tenant(onboarded_company["company"]["db_name"])
    user = await _make_user(tenant_db, onboarded_company["slug"], name, levels)
    headers = await _login_headers(
        client, onboarded_company["slug"], user["email"], user["password"]
    )
    doc = await tenant_db.users.find_one({"email": user["email"]})
    return tenant_db, headers, str(doc["_id"])


async def _emit(tenant_db, actor_id, action, module, *, age_days=0.0, n=1):
    now = datetime.now(UTC)
    await tenant_db.activity_log.insert_many([
        {
            "actor_id": actor_id, "actor_name": "tester", "action": action,
            "module": module, "entity": {}, "details": {},
            "occurred_at": now - timedelta(days=age_days),
        }
        for _ in range(n)
    ])


async def _get(client, headers) -> dict:
    res = await client.get("/api/v1/dashboard/quick-actions", headers=headers)
    assert res.status_code == 200, res.text
    return res.json()


async def _keys(client, headers) -> list[str]:
    return [a["key"] for a in (await _get(client, headers))["data"]]


async def _prefs(client, headers) -> list[dict]:
    res = await client.get("/api/v1/dashboard/quick-actions/prefs", headers=headers)
    assert res.status_code == 200, res.text
    return res.json()["data"]


async def _put_prefs(client, headers, *, pinned, hidden):
    return await client.put(
        "/api/v1/dashboard/quick-actions/prefs",
        headers=headers, json={"pinned": pinned, "hidden": hidden},
    )


# --- the pure formula (unit) -------------------------------------------------


def test_decay_halves_every_half_life():
    assert _decay(0, 7) == 1.0
    assert _decay(7, 7) == pytest.approx(0.5)
    assert _decay(14, 7) == pytest.approx(0.25)


def test_score_sums_role_exact_module_and_curated_bias():
    now = datetime(2026, 7, 28, tzinfo=UTC)
    action = {"key": "finance.invoice.new", "module": "finance"}
    # one event today that is BOTH the exact action and in-module
    events = [{"action": "finance.invoice.created", "module": "finance", "occurred_at": now}]
    s = _score(action, 3, 9, Level.WRITE, events, now, _cfg())
    # role + W_EXACT·1 (decay=1 at age 0) + W_MODULE·1 + tie·(9-3)
    assert s == pytest.approx(2.0 + 3.0 + 1.0 + 0.001 * (9 - 3))


def test_score_cold_start_is_role_plus_curated_bias_only():
    now = datetime(2026, 7, 28, tzinfo=UTC)
    first = _score({"key": "project.new", "module": "projects"}, 0, 9, Level.WRITE, [], now, _cfg())
    later = _score({"key": "crm.lead.new", "module": "crm"}, 1, 9, Level.WRITE, [], now, _cfg())
    assert first == pytest.approx(2.0 + 0.001 * 9)
    assert first > later  # earlier declaration wins the tiebreak


def test_score_exact_outranks_module_only():
    now = datetime(2026, 7, 28, tzinfo=UTC)
    # a finance.invoice.created event is exact for invoice.new, module-only for bill.new
    events = [{"action": "finance.invoice.created", "module": "finance", "occurred_at": now}]
    invoice = _score(
        {"key": "finance.invoice.new", "module": "finance"},
        3, 9, Level.WRITE, events, now, _cfg(),
    )
    bill = _score(
        {"key": "finance.bill.new", "module": "finance"},
        7, 9, Level.WRITE, events, now, _cfg(),
    )
    assert invoice > bill


def test_score_recent_event_outweighs_older_ones():
    now = datetime(2026, 7, 28, tzinfo=UTC)
    a = {"key": "crm.lead.new", "module": "crm"}
    fresh = [{"action": "crm.lead.created", "module": "crm", "occurred_at": now}]
    stale = [{"action": "crm.lead.created", "module": "crm",
              "occurred_at": now - timedelta(days=28)}]
    assert (
        _score(a, 1, 9, Level.WRITE, fresh, now, _cfg())
        > _score(a, 1, 9, Level.WRITE, stale, now, _cfg())
    )


# --- ranking through the API (integration) -----------------------------------


async def test_cold_start_returns_the_curated_order(client, onboarded_company):
    _, headers, _ = await _user_with(client, onboarded_company, "coldstart", FULL)
    assert await _keys(client, headers) == CURATED_ORDER


async def test_recent_behaviour_promotes_its_action(client, onboarded_company):
    tenant_db, headers, actor_id = await _user_with(client, onboarded_company, "invoicer", FULL)
    await _emit(tenant_db, actor_id, "finance.invoice.created", "finance", n=3)
    assert (await _keys(client, headers))[0] == "finance.invoice.new"


async def test_real_api_writes_shift_the_ranking(client_client):
    # Drive a genuine write so a crm.lead.created event accrues for this user,
    # end to end, and confirm the ranking reflects it.
    res = await client_client.post("/api/v1/crm/leads", json={"name": "Globex"})
    assert res.status_code in (200, 201), res.text
    got = await client_client.get("/api/v1/dashboard/quick-actions")
    assert [a["key"] for a in got.json()["data"]][0] == "crm.lead.new"


async def test_exact_action_beats_mere_module_presence(client, onboarded_company):
    tenant_db, headers, actor_id = await _user_with(client, onboarded_company, "biller", FULL)
    await _emit(tenant_db, actor_id, "finance.bill.created", "finance", n=3)
    keys = await _keys(client, headers)
    # bill activity is exact for bill.new, only module-engagement for invoice.new
    assert keys.index("finance.bill.new") < keys.index("finance.invoice.new")


async def test_stale_events_do_not_beat_a_recent_one(client, onboarded_company):
    tenant_db, headers, actor_id = await _user_with(client, onboarded_company, "recency", FULL)
    await _emit(tenant_db, actor_id, "crm.lead.created", "crm", age_days=25, n=5)
    await _emit(tenant_db, actor_id, "finance.invoice.created", "finance", age_days=0)
    assert (await _keys(client, headers))[0] == "finance.invoice.new"


async def test_permission_gate_holds_whatever_the_activity(client, onboarded_company):
    # WRITE crm only, yet the log is full of finance activity for this user.
    tenant_db, headers, actor_id = await _user_with(
        client, onboarded_company, "crmonly", {"dashboard": 2, "crm": 3})
    await _emit(tenant_db, actor_id, "finance.invoice.created", "finance", n=5)
    keys = set(await _keys(client, headers))
    assert keys == {"crm.lead.new", "crm.deal.new", "crm.contact.new"}
    assert not any(k.startswith("finance") for k in keys)


async def test_disabled_module_is_never_surfaced(client, onboarded_company):
    tenant_db, headers, actor_id = await _user_with(client, onboarded_company, "nofinance", FULL)
    await _emit(tenant_db, actor_id, "finance.invoice.created", "finance", n=3)
    # Disable finance company-wide (resolve_tenant re-reads this each request).
    await get_db_manager().control.companies.update_one(
        {"db_name": onboarded_company["company"]["db_name"]},
        {"$set": {"enabled_modules": ["dashboard", "settings", "projects", "crm", "inventory"]}},
    )
    keys = await _keys(client, headers)
    assert not any(k.startswith("finance") for k in keys)


async def test_ranking_is_deterministic(client, onboarded_company):
    tenant_db, headers, actor_id = await _user_with(client, onboarded_company, "determ", FULL)
    await _emit(tenant_db, actor_id, "crm.deal.created", "crm", n=2)
    await _emit(tenant_db, actor_id, "inventory.receipt", "inventory", n=1)
    assert await _keys(client, headers) == await _keys(client, headers)


# --- personalization: pins & hides (Phase 2) ---------------------------------


async def test_pins_lead_in_pin_order(client, onboarded_company):
    _, headers, _ = await _user_with(client, onboarded_company, "pinner", FULL)
    res = await _put_prefs(
        client, headers, pinned=["finance.bill.new", "crm.contact.new"], hidden=[]
    )
    assert res.status_code == 200, res.text
    data = (await _get(client, headers))["data"]
    # pinned first, in the order given — ahead of the curated/ranked rest
    assert [a["key"] for a in data[:2]] == ["finance.bill.new", "crm.contact.new"]
    assert data[0]["pinned"] is True and data[1]["pinned"] is True
    assert data[2]["pinned"] is False


async def test_hidden_actions_are_dropped(client, onboarded_company):
    _, headers, _ = await _user_with(client, onboarded_company, "hider", FULL)
    await _put_prefs(client, headers, pinned=[], hidden=["employee.invite", "inventory.adjust"])
    keys = await _keys(client, headers)
    assert "employee.invite" not in keys and "inventory.adjust" not in keys
    assert len(keys) == len(CURATED_ORDER) - 2


async def test_pins_beat_behaviour_ranking(client, onboarded_company):
    tenant_db, headers, actor_id = await _user_with(client, onboarded_company, "pinbeat", FULL)
    # heavy invoice behavior alone would rank finance.invoice.new first…
    await _emit(tenant_db, actor_id, "finance.invoice.created", "finance", n=5)
    # …but an explicit pin outranks it
    await _put_prefs(client, headers, pinned=["crm.contact.new"], hidden=[])
    assert (await _keys(client, headers))[0] == "crm.contact.new"


async def test_customize_lists_permitted_with_state(client, onboarded_company):
    _, headers, _ = await _user_with(client, onboarded_company, "customizer", FULL)
    await _put_prefs(client, headers, pinned=["crm.deal.new"], hidden=["finance.bill.new"])
    rows = await _prefs(client, headers)
    # the dialog sees ALL permitted actions, including the hidden one
    assert {r["key"] for r in rows} == set(CURATED_ORDER)
    by_key = {r["key"]: r for r in rows}
    assert by_key["crm.deal.new"]["pinned"] is True
    assert by_key["finance.bill.new"]["hidden"] is True


async def test_cannot_customize_a_forbidden_action(client, onboarded_company):
    # crm-only WRITE: a finance action is not permitted, so it can't be pinned
    _, headers, _ = await _user_with(
        client, onboarded_company, "limited", {"dashboard": 2, "crm": 3})
    res = await _put_prefs(client, headers, pinned=["finance.invoice.new"], hidden=[])
    assert res.status_code == 422


async def test_cannot_pin_and_hide_the_same_action(client, onboarded_company):
    _, headers, _ = await _user_with(client, onboarded_company, "conflict", FULL)
    res = await _put_prefs(client, headers, pinned=["crm.lead.new"], hidden=["crm.lead.new"])
    assert res.status_code == 422


async def test_customize_entry_survives_hiding_everything(client, onboarded_company):
    _, headers, _ = await _user_with(client, onboarded_company, "allhidden", FULL)
    await _put_prefs(client, headers, pinned=[], hidden=list(CURATED_ORDER))
    body = await _get(client, headers)
    assert body["data"] == []                      # nothing shows inline…
    assert body["meta"]["customizable"] is True    # …but Customize stays reachable


async def test_customizing_is_audited(client, onboarded_company):
    tenant_db, headers, actor_id = await _user_with(client, onboarded_company, "audited", FULL)
    await _put_prefs(client, headers, pinned=["crm.lead.new"], hidden=["employee.invite"])
    logged = await tenant_db.activity_log.find_one(
        {"actor_id": actor_id, "action": "dashboard.quick_actions.customized"})
    assert logged is not None
    assert logged["module"] == "dashboard"
    assert logged["details"] == {"pinned": ["crm.lead.new"], "hidden": ["employee.invite"]}
