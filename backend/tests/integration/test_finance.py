"""Finance module acceptance criteria (docs/modules/FINANCE.md §6): balanced
entries, invoice → payment → paid, trial balance / balance sheet, void
reversal, and the inventory_issue link."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest


def _due(days: int = 30) -> str:
    return (datetime.now(UTC) + timedelta(days=days)).isoformat()


async def _accounts(client_client) -> dict[str, str]:
    """code → id for the seeded starter chart (§4)."""
    res = await client_client.get("/api/v1/finance/accounts")
    return {a["code"]: a["id"] for a in res.json()["data"]}


async def _invoice(client_client, amount=1000, tax_rate=0, **extra) -> dict:
    res = await client_client.post("/api/v1/finance/invoices", json={
        "customer_ref": {"name": "Northwind Traders"},
        "due_date": _due(),
        "lines": [{
            "description": "Consulting", "qty": 1,
            "unit_price": amount, "tax_rate": tax_rate,
        }],
        **extra,
    })
    assert res.status_code == 201, res.text
    return res.json()["data"]


async def _send(client_client, invoice_id: str):
    return await client_client.post(f"/api/v1/finance/invoices/{invoice_id}/send")


async def _pay(client_client, invoice_id: str, amount: float, method="bank"):
    return await client_client.post("/api/v1/finance/payments", json={
        "type": "customer_payment", "ref_doc_type": "invoice",
        "ref_doc_id": invoice_id, "amount": amount, "method": method,
    })


# --- acceptance #1: every posted entry balances ------------------------------

async def test_unbalanced_manual_entry_is_rejected(client_client):
    codes = await _accounts(client_client)
    res = await client_client.post("/api/v1/finance/journal-entries", json={
        "memo": "wonky", "lines": [
            {"account_id": codes["1000"], "debit": 100},
            {"account_id": codes["4000"], "credit": 60},
        ],
    })
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "UNBALANCED_ENTRY"
    assert res.json()["error"]["details"] == {"debit_total": 100, "credit_total": 60}

    # nothing was written
    res = await client_client.get("/api/v1/finance/journal-entries")
    assert res.json()["meta"]["total"] == 0


async def test_balanced_manual_entry_posts(client_client):
    codes = await _accounts(client_client)
    res = await client_client.post("/api/v1/finance/journal-entries", json={
        "memo": "Owner funds the bank", "lines": [
            {"account_id": codes["1010"], "debit": 5000, "description": "seed capital"},
            {"account_id": codes["3000"], "credit": 5000},
        ],
    })
    assert res.status_code == 201, res.text
    entry = res.json()["data"]
    assert entry["posted"] is True
    assert sum(line["debit"] for line in entry["lines"]) == 5000
    assert sum(line["credit"] for line in entry["lines"]) == 5000


async def test_a_line_cannot_be_both_debit_and_credit(client_client):
    codes = await _accounts(client_client)
    res = await client_client.post("/api/v1/finance/journal-entries", json={
        "memo": "both sides", "lines": [
            {"account_id": codes["1000"], "debit": 50, "credit": 50},
            {"account_id": codes["4000"], "credit": 50, "debit": 50},
        ],
    })
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "UNBALANCED_ENTRY"


async def test_zero_value_entry_is_rejected(client_client):
    codes = await _accounts(client_client)
    res = await client_client.post("/api/v1/finance/journal-entries", json={
        "memo": "nothing", "lines": [
            {"account_id": codes["1000"], "debit": 0},
            {"account_id": codes["4000"], "credit": 0},
        ],
    })
    assert res.status_code == 422


# --- acceptance #2: send + full payment → paid, two balanced entries ---------

async def test_send_then_full_payment_marks_paid_with_two_entries(client_client):
    codes = await _accounts(client_client)
    invoice = await _invoice(client_client, amount=1000)
    assert invoice["status"] == "draft"
    assert invoice["number"] is None  # §2: no number burned until it posts

    res = await _send(client_client, invoice["id"])
    assert res.status_code == 200, res.text
    sent = res.json()["data"]
    assert sent["status"] == "sent"
    assert sent["number"] == "INV-0001"

    # entry 1: Dr AR / Cr Income
    entries = (await client_client.get("/api/v1/finance/journal-entries")).json()["data"]
    assert len(entries) == 1
    ar_line = next(x for x in entries[0]["lines"] if x["account_id"] == codes["1100"])
    income_line = next(x for x in entries[0]["lines"] if x["account_id"] == codes["4000"])
    assert ar_line["debit"] == 1000
    assert income_line["credit"] == 1000

    res = await _pay(client_client, invoice["id"], 1000)
    assert res.status_code == 201, res.text

    paid = (await client_client.get(f"/api/v1/finance/invoices/{invoice['id']}")).json()["data"]
    assert paid["status"] == "paid"
    assert paid["paid_amount"] == 1000

    # entry 2: Dr Bank / Cr AR — two entries, both balanced
    entries = (await client_client.get("/api/v1/finance/journal-entries")).json()["data"]
    assert len(entries) == 2
    for entry in entries:
        assert sum(x["debit"] for x in entry["lines"]) == sum(x["credit"] for x in entry["lines"])
    pay_entry = next(e for e in entries if e["source"]["module"] == "payment")
    bank = next(x for x in pay_entry["lines"] if x["account_id"] == codes["1010"])
    ar = next(x for x in pay_entry["lines"] if x["account_id"] == codes["1100"])
    assert bank["debit"] == 1000
    assert ar["credit"] == 1000

    # AR nets to zero once settled
    tb = (await client_client.get("/api/v1/finance/reports/trial-balance")).json()["data"]
    ar_row = next(r for r in tb["rows"] if r["code"] == "1100")
    assert ar_row["balance"] == 0


async def test_partial_payment_is_partly_paid(client_client):
    invoice = await _invoice(client_client, amount=1000)
    await _send(client_client, invoice["id"])

    await _pay(client_client, invoice["id"], 400)
    doc = (await client_client.get(f"/api/v1/finance/invoices/{invoice['id']}")).json()["data"]
    assert doc["status"] == "partly_paid"
    assert doc["paid_amount"] == 400

    await _pay(client_client, invoice["id"], 600)
    doc = (await client_client.get(f"/api/v1/finance/invoices/{invoice['id']}")).json()["data"]
    assert doc["status"] == "paid"
    assert doc["paid_amount"] == 1000


async def test_overpayment_is_rejected(client_client):
    invoice = await _invoice(client_client, amount=500)
    await _send(client_client, invoice["id"])
    res = await _pay(client_client, invoice["id"], 501)
    assert res.status_code == 422
    assert res.json()["error"]["details"]["outstanding"] == 500


async def test_payment_needs_a_posted_document(client_client):
    invoice = await _invoice(client_client)
    res = await _pay(client_client, invoice["id"], 10)  # still a draft
    assert res.status_code == 409


async def test_tax_is_credited_to_the_tax_account(client_client):
    codes = await _accounts(client_client)
    invoice = await _invoice(client_client, amount=1000, tax_rate=10)
    assert invoice["subtotal"] == 1000
    assert invoice["tax_total"] == 100
    assert invoice["total"] == 1100

    await _send(client_client, invoice["id"])
    entry = (await client_client.get("/api/v1/finance/journal-entries")).json()["data"][0]
    tax = next(x for x in entry["lines"] if x["account_id"] == codes["2100"])
    assert tax["credit"] == 100
    assert sum(x["debit"] for x in entry["lines"]) == 1100
    assert sum(x["credit"] for x in entry["lines"]) == 1100


async def test_invoice_numbers_are_sequential_and_gapless(client_client):
    """§2: numbers come from the counter at post time, so an abandoned draft
    burns none."""
    a = await _invoice(client_client, amount=10)
    await _send(client_client, a["id"])
    abandoned = await _invoice(client_client, amount=10)  # never sent
    b = await _invoice(client_client, amount=10)
    await _send(client_client, b["id"])

    numbers = [
        i["number"] for i in
        (await client_client.get("/api/v1/finance/invoices")).json()["data"]
        if i["number"]
    ]
    assert sorted(numbers) == ["INV-0001", "INV-0002"]
    doc = (await client_client.get(
        f"/api/v1/finance/invoices/{abandoned['id']}")).json()["data"]
    assert doc["number"] is None


async def test_many_drafts_coexist_but_numbers_stay_unique(
    client_client, onboarded_company
):
    """The `number` index is partial for a reason: every draft carries
    `number: null`, and Mongo treats all nulls as one value — a plain unique
    index would reject the second draft. Posted numbers must still be unique,
    which a hand-written number (import/migration) would otherwise violate."""
    from pymongo.errors import DuplicateKeyError

    from app.core.db import get_db_manager

    # several drafts at once — all number: null
    for _ in range(3):
        await _invoice(client_client, amount=10)
    assert (await client_client.get(
        "/api/v1/finance/invoices")).json()["meta"]["total"] == 3

    inv = await _invoice(client_client, amount=10)
    await _send(client_client, inv["id"])

    tenant_db = get_db_manager().tenant(onboarded_company["company"]["db_name"])
    with pytest.raises(DuplicateKeyError):
        await tenant_db.invoices.insert_one({
            "number": "INV-0001", "total": 1, "status": "sent",
        })


async def test_posted_invoice_cannot_be_edited_or_deleted(client_client):
    invoice = await _invoice(client_client)
    await _send(client_client, invoice["id"])
    res = await client_client.patch(f"/api/v1/finance/invoices/{invoice['id']}",
                                    json={"notes": "sneaky"})
    assert res.status_code == 409
    res = await client_client.delete(f"/api/v1/finance/invoices/{invoice['id']}")
    assert res.status_code == 409


# --- acceptance #3: trial balance nets to zero, balance sheet balances -------

async def test_trial_balance_nets_to_zero_and_balance_sheet_balances(client_client):
    inv = await _invoice(client_client, amount=2000, tax_rate=10)
    await _send(client_client, inv["id"])
    await _pay(client_client, inv["id"], 1100)

    res = await client_client.post("/api/v1/finance/bills", json={
        "vendor_ref": {"name": "Timber Supply Co"},
        "due_date": _due(15),
        "lines": [{"description": "Oak", "qty": 10, "unit_price": 50, "tax_rate": 10}],
    })
    bill = res.json()["data"]
    await client_client.post(f"/api/v1/finance/bills/{bill['id']}/send")

    tb = (await client_client.get("/api/v1/finance/reports/trial-balance")).json()["data"]
    assert tb["balanced"] is True
    assert tb["debit_total"] == tb["credit_total"]

    bs = (await client_client.get("/api/v1/finance/reports/balance-sheet")).json()["data"]
    assert bs["balanced"] is True
    assert bs["assets_total"] == bs["liabilities_and_equity_total"]


async def test_pnl_is_income_minus_expense(client_client):
    inv = await _invoice(client_client, amount=3000)
    await _send(client_client, inv["id"])
    res = await client_client.post("/api/v1/finance/bills", json={
        "vendor_ref": {"name": "Supplier"},
        "due_date": _due(),
        "lines": [{"description": "Materials", "qty": 1, "unit_price": 1200}],
    })
    await client_client.post(f"/api/v1/finance/bills/{res.json()['data']['id']}/send")

    pnl = (await client_client.get("/api/v1/finance/reports/pnl")).json()["data"]
    assert pnl["income_total"] == 3000
    assert pnl["expense_total"] == 1200
    assert pnl["net_profit"] == 1800


async def test_aging_buckets_open_documents_by_due_date(client_client):
    overdue = await _invoice(client_client, amount=100)
    await client_client.patch(f"/api/v1/finance/invoices/{overdue['id']}",
                              json={"due_date": _due(-45)})
    await _send(client_client, overdue["id"])

    current = await _invoice(client_client, amount=200)
    await _send(client_client, current["id"])

    aging = (await client_client.get(
        "/api/v1/finance/reports/aging", params={"type": "ar"})).json()["data"]
    assert aging["type"] == "ar"
    assert aging["total"] == 300
    assert aging["buckets"]["31-60"]["total"] == 100
    assert aging["buckets"]["current"]["total"] == 200
    overdue_item = next(i for i in aging["items"] if i["outstanding"] == 100)
    assert overdue_item["days_overdue"] >= 44


async def test_paid_invoices_leave_the_aging_report(client_client):
    inv = await _invoice(client_client, amount=100)
    await _send(client_client, inv["id"])
    assert (await client_client.get(
        "/api/v1/finance/reports/aging", params={"type": "ar"})).json()["data"]["total"] == 100
    await _pay(client_client, inv["id"], 100)
    assert (await client_client.get(
        "/api/v1/finance/reports/aging", params={"type": "ar"})).json()["data"]["total"] == 0


# --- acceptance #4: void reverses, never removes -----------------------------

async def test_void_writes_a_reversing_entry_and_keeps_the_original(client_client):
    invoice = await _invoice(client_client, amount=750)
    await _send(client_client, invoice["id"])
    original = (await client_client.get("/api/v1/finance/journal-entries")).json()["data"][0]

    res = await client_client.post(f"/api/v1/finance/invoices/{invoice['id']}/void",
                                   json={"reason": "duplicate"})
    assert res.status_code == 200, res.text
    assert res.json()["data"]["status"] == "void"
    assert res.json()["data"]["void_reason"] == "duplicate"

    entries = (await client_client.get("/api/v1/finance/journal-entries")).json()["data"]
    assert len(entries) == 2  # the original still exists
    assert any(e["id"] == original["id"] for e in entries)

    reversal = next(e for e in entries if e.get("reverses"))
    assert reversal["reverses"] == original["id"]
    # every line is mirrored
    for line in original["lines"]:
        mirror = next(
            x for x in reversal["lines"] if x["account_id"] == line["account_id"]
        )
        assert mirror["debit"] == line["credit"]
        assert mirror["credit"] == line["debit"]

    # and the books are flat again
    tb = (await client_client.get("/api/v1/finance/reports/trial-balance")).json()["data"]
    assert tb["balanced"] is True
    assert all(r["balance"] == 0 for r in tb["rows"])


async def test_void_is_refused_once_paid(client_client):
    invoice = await _invoice(client_client, amount=100)
    await _send(client_client, invoice["id"])
    await _pay(client_client, invoice["id"], 100)
    res = await client_client.post(f"/api/v1/finance/invoices/{invoice['id']}/void",
                                   json={"reason": "oops"})
    assert res.status_code == 409


async def test_a_draft_cannot_be_voided(client_client):
    invoice = await _invoice(client_client)
    res = await client_client.post(f"/api/v1/finance/invoices/{invoice['id']}/void",
                                   json={"reason": "never posted"})
    assert res.status_code == 409


# --- acceptance #5: inventory_issue reduces on-hand --------------------------

async def _stocked_product(client_client, sku="FIN-SKU", qty=50) -> tuple[dict, dict]:
    res = await client_client.post("/api/v1/inventory/products", json={
        "sku": sku, "name": "Oak panel", "unit": "pcs",
    })
    product = res.json()["data"]
    wh = next(
        w for w in (await client_client.get("/api/v1/inventory/warehouses")).json()["data"]
        if w["code"] == "WH1"
    )
    await client_client.post("/api/v1/inventory/movements", json={
        "product_id": product["id"], "warehouse_id": wh["id"],
        "type": "receipt", "qty": qty,
    })
    return product, wh


async def _on_hand(client_client, product, wh) -> float:
    res = await client_client.get("/api/v1/inventory/stock-levels", params={
        "product_id": product["id"], "warehouse_id": wh["id"]})
    rows = res.json()["data"]
    return rows[0]["on_hand"] if rows else 0.0


async def test_inventory_issue_reduces_on_hand_when_posted(client_client):
    product, wh = await _stocked_product(client_client)
    assert await _on_hand(client_client, product, wh) == 50

    res = await client_client.post("/api/v1/finance/invoices", json={
        "customer_ref": {"name": "Buyer"},
        "due_date": _due(),
        "inventory_issue": True,
        "warehouse_id": wh["id"],
        "lines": [{
            "description": "Oak panel", "qty": 12, "unit_price": 78,
            "product_id": product["id"],
        }],
    })
    assert res.status_code == 201, res.text
    invoice = res.json()["data"]

    # a draft has not shipped anything yet
    assert await _on_hand(client_client, product, wh) == 50

    res = await _send(client_client, invoice["id"])
    assert res.status_code == 200, res.text
    assert await _on_hand(client_client, product, wh) == 38

    # the movement points back at the invoice (INVENTORY.md §5: explicit link)
    movements = (await client_client.get("/api/v1/inventory/movements", params={
        "product_id": product["id"], "type": "issue"})).json()["data"]
    assert len(movements) == 1
    assert movements[0]["qty"] == -12
    assert movements[0]["ref"]["module"] == "finance"
    assert movements[0]["ref"]["doc_id"] == invoice["id"]

    # and the stock cache still equals the ledger
    assert (await client_client.get(
        "/api/v1/inventory/reconcile")).json()["data"]["consistent"] is True


async def test_inventory_issue_needs_a_product_on_every_line(client_client):
    res = await client_client.post("/api/v1/finance/invoices", json={
        "customer_ref": {"name": "Buyer"},
        "due_date": _due(),
        "inventory_issue": True,
        "lines": [{"description": "Mystery item", "qty": 1, "unit_price": 10}],
    })
    assert res.status_code == 422


async def test_send_fails_and_posts_nothing_when_stock_is_short(client_client):
    """An out-of-stock send must leave no accounting trace and no number gap."""
    product, wh = await _stocked_product(client_client, sku="FIN-SHORT", qty=5)

    res = await client_client.post("/api/v1/finance/invoices", json={
        "customer_ref": {"name": "Buyer"},
        "due_date": _due(),
        "inventory_issue": True,
        "warehouse_id": wh["id"],
        "lines": [{
            "description": "Oak panel", "qty": 9, "unit_price": 78,
            "product_id": product["id"],
        }],
    })
    invoice = res.json()["data"]

    res = await _send(client_client, invoice["id"])
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "INSUFFICIENT_STOCK"

    # invoice untouched, no journal entry, stock untouched
    doc = (await client_client.get(f"/api/v1/finance/invoices/{invoice['id']}")).json()["data"]
    assert doc["status"] == "draft"
    assert doc["number"] is None
    assert (await client_client.get(
        "/api/v1/finance/journal-entries")).json()["meta"]["total"] == 0
    assert await _on_hand(client_client, product, wh) == 5


async def test_multi_line_issue_unwinds_when_a_later_line_is_short(client_client):
    """The first line ships, the second cannot — neither may remain issued."""
    ok, wh = await _stocked_product(client_client, sku="FIN-OK", qty=50)
    short, _ = await _stocked_product(client_client, sku="FIN-LOW", qty=1)

    res = await client_client.post("/api/v1/finance/invoices", json={
        "customer_ref": {"name": "Buyer"},
        "due_date": _due(),
        "inventory_issue": True,
        "warehouse_id": wh["id"],
        "lines": [
            {"description": "A", "qty": 5, "unit_price": 10, "product_id": ok["id"]},
            {"description": "B", "qty": 4, "unit_price": 10, "product_id": short["id"]},
        ],
    })
    invoice = res.json()["data"]

    res = await _send(client_client, invoice["id"])
    assert res.status_code == 409

    # the first line's issue was rolled back
    assert await _on_hand(client_client, ok, wh) == 50
    assert await _on_hand(client_client, short, wh) == 1
    assert (await client_client.get(
        "/api/v1/inventory/reconcile")).json()["data"]["consistent"] is True


# --- dashboard integration ---------------------------------------------------

async def test_unpaid_invoice_total_feeds_the_dashboard_kpi(client_client):
    before = (await client_client.get("/api/v1/dashboard/kpis")).json()["data"]
    assert before["unpaid_invoices_total"] == 0

    inv = await _invoice(client_client, amount=900)
    await _send(client_client, inv["id"])
    after = (await client_client.get("/api/v1/dashboard/kpis")).json()["data"]
    assert after["unpaid_invoices_total"] == 900

    await _pay(client_client, inv["id"], 400)
    after = (await client_client.get("/api/v1/dashboard/kpis")).json()["data"]
    assert after["unpaid_invoices_total"] == 500  # only what is still outstanding

    await _pay(client_client, inv["id"], 500)
    after = (await client_client.get("/api/v1/dashboard/kpis")).json()["data"]
    assert after["unpaid_invoices_total"] == 0


async def test_due_dates_feed_the_calendar(client_client):
    due = datetime.now(UTC) + timedelta(days=6)
    inv = await _invoice(client_client, amount=100)
    await client_client.patch(f"/api/v1/finance/invoices/{inv['id']}",
                              json={"due_date": due.isoformat()})
    await _send(client_client, inv["id"])

    res = await client_client.post("/api/v1/finance/bills", json={
        "vendor_ref": {"name": "Supplier"}, "due_date": due.isoformat(),
        "lines": [{"description": "Stuff", "qty": 1, "unit_price": 50}],
    })
    await client_client.post(f"/api/v1/finance/bills/{res.json()['data']['id']}/send")

    frm = (due - timedelta(days=2)).date().isoformat()
    to = (due + timedelta(days=2)).date().isoformat()
    events = (await client_client.get("/api/v1/calendar", params={
        "from": frm, "to": to})).json()["data"]
    types = {e["type"] for e in events if e["source_module"] == "finance"}
    assert {"invoice_due", "bill_due"} <= types


# --- RBAC (§3: enforce strictly) ---------------------------------------------

async def _limited_client(client, client_client, onboarded_company, perms, who):
    res = await client_client.post("/api/v1/settings/roles", json={
        "name": f"role-{who}", "permissions": perms,
    })
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


@pytest.mark.parametrize("path", [
    "/api/v1/finance/accounts", "/api/v1/finance/journal-entries",
    "/api/v1/finance/invoices", "/api/v1/finance/bills",
    "/api/v1/finance/reports/trial-balance", "/api/v1/finance/reports/pnl",
    "/api/v1/finance/reports/balance-sheet", "/api/v1/finance/reports/aging",
])
async def test_finance_none_is_denied_everywhere(
    client, client_client, onboarded_company, path
):
    headers = await _limited_client(
        client, client_client, onboarded_company, {"dashboard": 2}, "nofin",
    )
    res = await client.get(path, headers=headers)
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "PERMISSION_DENIED"


async def test_finance_read_can_report_but_not_post(
    client, client_client, onboarded_company
):
    """§3: many roles get READ finance — they must not be able to move money."""
    headers = await _limited_client(
        client, client_client, onboarded_company,
        {"dashboard": 2, "finance": 2}, "readfin",
    )
    assert (await client.get(
        "/api/v1/finance/reports/trial-balance", headers=headers)).status_code == 200

    res = await client.post("/api/v1/finance/invoices", headers=headers, json={
        "customer_ref": {"name": "X"}, "due_date": _due(),
        "lines": [{"description": "x", "qty": 1, "unit_price": 1}],
    })
    assert res.status_code == 403
    res = await client.post("/api/v1/finance/payments", headers=headers, json={
        "type": "customer_payment", "ref_doc_type": "invoice",
        "ref_doc_id": "6a57fc000ea6cf67cc8c211a", "amount": 1,
    })
    assert res.status_code == 403


async def test_finance_none_sees_no_finance_kpi_or_calendar(
    client, client_client, onboarded_company
):
    inv = await _invoice(client_client, amount=100)
    await _send(client_client, inv["id"])

    headers = await _limited_client(
        client, client_client, onboarded_company,
        {"dashboard": 2, "calendar": 2}, "blindfin",
    )
    kpis = (await client.get("/api/v1/dashboard/kpis", headers=headers)).json()["data"]
    assert "unpaid_invoices_total" not in kpis

    # the calendar window is capped at 90 days, so stay inside it
    frm = (datetime.now(UTC) - timedelta(days=10)).date().isoformat()
    to = (datetime.now(UTC) + timedelta(days=60)).date().isoformat()
    res = await client.get("/api/v1/calendar", headers=headers,
                           params={"from": frm, "to": to})
    assert res.status_code == 200, res.text
    assert all(e["source_module"] != "finance" for e in res.json()["data"])

    # the owner, with finance READ, does see the invoice due
    res = await client_client.get("/api/v1/calendar", params={"from": frm, "to": to})
    assert any(e["source_module"] == "finance" for e in res.json()["data"])


# --- chart of accounts -------------------------------------------------------

async def test_starter_chart_is_seeded(client_client):
    codes = await _accounts(client_client)
    assert set(codes) == {"1000", "1010", "1100", "2000", "2100", "3000", "4000", "5000"}


async def test_duplicate_account_code_is_rejected(client_client):
    res = await client_client.post("/api/v1/finance/accounts", json={
        "code": "1000", "name": "Petty cash", "type": "asset",
    })
    assert res.status_code == 409


async def test_account_with_ledger_history_cannot_be_deleted(client_client):
    codes = await _accounts(client_client)
    inv = await _invoice(client_client, amount=100)
    await _send(client_client, inv["id"])

    res = await client_client.delete(f"/api/v1/finance/accounts/{codes['1100']}")
    assert res.status_code == 409

    # an untouched account may still go
    res = await client_client.post("/api/v1/finance/accounts", json={
        "code": "9999", "name": "Scratch", "type": "expense",
    })
    assert (await client_client.delete(
        f"/api/v1/finance/accounts/{res.json()['data']['id']}")).status_code == 200


async def test_posting_fails_clearly_if_a_required_account_is_missing(client_client):
    """Deleting a posting account before it has history is allowed, so posting
    must say what is wrong rather than fail obscurely."""
    codes = await _accounts(client_client)
    await client_client.delete(f"/api/v1/finance/accounts/{codes['4000']}")

    inv = await _invoice(client_client, amount=100)
    res = await _send(client_client, inv["id"])
    assert res.status_code == 409
    assert "4000" in res.json()["error"]["message"]
