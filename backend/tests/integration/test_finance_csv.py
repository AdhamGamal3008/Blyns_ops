"""Finance CSV import & export (docs/modules/FINANCE.md §7 parity with CRM/Inventory).

The load-bearing property is that only master data is importable: the chart of
accounts upserts on its `code`, while the posted books (invoices, bills) are
export-only — a spreadsheet must never write to the double-entry ledger behind
the balance check. A fresh finance tenant is already seeded with the 8-account
starter chart (codes 1000–5000), so imports upsert on top of it.
"""

from __future__ import annotations

import csv
import io
from datetime import UTC, datetime, timedelta

from app.modules.finance import csv_schema
from tests.integration.test_crm import _limited_client

BOM = "﻿"
SEEDED = 8  # starter chart of accounts


def _table(text: str) -> list[list[str]]:
    return list(csv.reader(io.StringIO(text.lstrip(BOM), newline="")))


def _csv(*rows: list[str]) -> str:
    out = io.StringIO()
    csv.writer(out, lineterminator="\r\n").writerows(rows)
    return out.getvalue()


async def _upload(client_client, entity: str, text: str, *, mode: str = "validate",
                  name: str = "import.csv"):
    return await client_client.post(
        f"/api/v1/finance/import/{entity}",
        params={"mode": mode},
        files={"file": (name, text.encode("utf-8"), "text/csv")},
    )


async def _commit(client_client, entity: str, text: str, **kw) -> dict:
    res = await _upload(client_client, entity, text, mode="commit", **kw)
    assert res.status_code == 200, res.text
    return res.json()["data"]


async def _accounts(client_client) -> list[dict]:
    res = await client_client.get("/api/v1/finance/accounts", params={"page_size": 100})
    assert res.status_code == 200, res.text
    return res.json()["data"]


async def _by_code(client_client, code: str) -> dict:
    return next(a for a in await _accounts(client_client) if a["code"] == code)


# --- the template is the contract --------------------------------------------

async def test_account_template_is_exactly_the_importable_columns(client_client):
    res = await client_client.get("/api/v1/finance/import/accounts/template")
    assert res.status_code == 200, res.text
    assert res.text.startswith(BOM)
    rows = _table(res.text)
    assert rows[0] == [f.header for f in csv_schema.ACCOUNTS.importable_fields]
    assert len(rows) == 1
    # server-owned columns are exportable but never importable
    assert "Record ID" not in rows[0]
    assert "Created at" not in rows[0]


# --- import: the happy path --------------------------------------------------

async def test_import_creates_a_new_account(client_client):
    text = _csv(
        ["Code", "Name", "Type", "Currency", "Active"],
        ["6000", "Marketing", "expense", "USD", "yes"],
    )
    report = await _commit(client_client, "accounts", text)
    assert (report["created"], report["updated"], report["failed"]) == (1, 0, 0)

    acc = await _by_code(client_client, "6000")
    assert acc["name"] == "Marketing"
    assert acc["type"] == "expense"
    assert acc["is_active"] is True


async def test_import_resolves_a_parent_by_code(client_client):
    """A person keeps account codes, not ObjectIds, in a spreadsheet — a parent
    is named by its code and stored as the parent's id (the seeded 1000 Cash)."""
    text = _csv(
        ["Code", "Name", "Type", "Parent code"],
        ["1001", "Petty Cash", "asset", "1000"],
    )
    report = await _commit(client_client, "accounts", text)
    assert report["created"] == 1

    cash = await _by_code(client_client, "1000")
    petty = await _by_code(client_client, "1001")
    assert petty["parent_id"] == cash["id"]


async def test_import_unknown_parent_is_a_row_error(client_client):
    text = _csv(
        ["Code", "Name", "Type", "Parent code"],
        ["7000", "Orphan", "asset", "NOPE"],
    )
    report = await _commit(client_client, "accounts", text)
    assert (report["created"], report["failed"]) == (0, 1)
    assert "NOPE" in report["errors"][0]["message"]

    # the typo did not conjure an account
    codes = [a["code"] for a in await _accounts(client_client)]
    assert "7000" not in codes


# --- import: upsert semantics ------------------------------------------------

async def test_reimporting_updates_the_account_on_its_code(client_client):
    text = _csv(["Code", "Name", "Type"], ["1000", "Cash on hand", "asset"])
    report = await _commit(client_client, "accounts", text)
    assert (report["created"], report["updated"]) == (0, 1)  # updates seeded Cash
    assert (await _by_code(client_client, "1000"))["name"] == "Cash on hand"


async def test_account_code_matching_is_case_sensitive(client_client):
    """A code is an exact identifier with a unique index; folding case here would
    let `expa` silently rename `EXPA` on the next import."""
    await _commit(client_client, "accounts",
                  _csv(["Code", "Name", "Type"], ["EXPA", "Expense A", "expense"]))
    report = await _commit(client_client, "accounts",
                           _csv(["Code", "Name", "Type"], ["expa", "Expense a", "expense"]))
    assert (report["created"], report["updated"]) == (1, 0)  # a different account


# --- import: a spreadsheet cannot skip a rule --------------------------------

async def test_an_invalid_account_type_is_a_row_error(client_client):
    text = _csv(["Code", "Name", "Type"], ["8000", "Weird", "frobnicate"])
    report = await _commit(client_client, "accounts", text)
    assert report["failed"] == 1
    msg = report["errors"][0]["message"]
    assert "frobnicate" in msg
    assert "asset" in msg  # names what is allowed


async def test_a_missing_required_column_rejects_the_whole_file(client_client):
    # Type is required — omitting the column entirely rejects the file
    res = await _upload(client_client, "accounts",
                        _csv(["Code", "Name"], ["9000", "No type"]), mode="commit")
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "VALIDATION_ERROR"
    assert "Type" in res.json()["error"]["message"]


# --- export ------------------------------------------------------------------

async def test_export_returns_the_seeded_chart(client_client):
    res = await client_client.get("/api/v1/finance/export/accounts")
    assert res.status_code == 200
    assert "finance-accounts-export-" in res.headers["content-disposition"]
    rows = _table(res.text)
    assert rows[0] == [f.header for f in csv_schema.ACCOUNTS.exportable]
    codes = {r[0] for r in rows[1:]}
    assert {"1000", "1100", "4000", "5000"} <= codes
    assert len(rows) - 1 >= SEEDED


async def test_export_filters_by_active_flag(client_client):
    await _commit(client_client, "accounts",
                  _csv(["Code", "Name", "Type", "Active"],
                       ["6200", "Retired", "expense", "no"]))
    res = await client_client.get("/api/v1/finance/export/accounts",
                                  params={"status": "no", "fields": "code,name"})
    codes = [r[0] for r in _table(res.text)[1:]]
    assert "6200" in codes
    assert "1000" not in codes  # the seeded chart is active


async def test_export_then_import_is_a_no_op(client_client):
    """The round trip that makes bulk editing safe: export the chart, change
    nothing, upload it back — every row matches its own account."""
    exported = (await client_client.get("/api/v1/finance/export/accounts")).text
    report = await _commit(client_client, "accounts", exported)
    assert report["created"] == 0
    assert report["failed"] == 0
    assert report["updated"] >= SEEDED


# --- invoices & bills are export-only ----------------------------------------

async def test_invoices_and_bills_cannot_be_imported(client_client):
    """A posted AR/AP document is the outcome of a balanced journal entry with a
    sequential number — never handwritten rows."""
    for entity in ("invoices", "bills"):
        res = await client_client.get(f"/api/v1/finance/import/{entity}/template")
        assert res.status_code == 422, entity
        assert "derived" in res.json()["error"]["message"]

        res = await _upload(client_client, entity,
                            _csv(["Number"], ["X"]), mode="commit")
        assert res.status_code == 422, entity


async def test_invoice_export_shows_the_header_row(client_client):
    due = (datetime.now(UTC) + timedelta(days=30)).isoformat()
    res = await client_client.post("/api/v1/finance/invoices", json={
        "customer_ref": {"name": "Globex Ltd"},
        "due_date": due,
        "lines": [{"description": "Cladding", "qty": 2, "unit_price": 100}],
    })
    assert res.status_code == 201, res.text

    res = await client_client.get("/api/v1/finance/export/invoices")
    rows = _table(res.text)
    assert rows[0] == [f.header for f in csv_schema.INVOICES.exportable]
    # headers: Number, Customer, Issue date, Due date, Subtotal, Tax, Total,
    #          Paid, Status, Currency, Record ID
    row = next(r for r in rows[1:] if r[1] == "Globex Ltd")
    assert row[6] == "200"      # total: 2 × 100, no tax
    assert row[7] == "0"        # nothing paid
    assert row[8] == "draft"    # not yet sent


# --- RBAC: per-tab CSV grants, layered on finance READ (SETTINGS.md §1.3) -----

async def test_finance_module_read_alone_opens_no_csv_route(
    client, client_client, onboarded_company
):
    headers = await _limited_client(
        client, client_client, onboarded_company,
        {"dashboard": 2, "finance": 2}, "fincsvnone",
    )
    for path in (
        "/api/v1/finance/export/accounts",
        "/api/v1/finance/export/accounts/fields",
        "/api/v1/finance/import/accounts/template",
    ):
        res = await client.get(path, headers=headers)
        assert res.status_code == 403, f"{path} → {res.status_code}"
        assert res.json()["error"]["code"] == "PERMISSION_DENIED"

    res = await client.post(
        "/api/v1/finance/import/accounts", headers=headers,
        files={"file": ("x.csv",
                        _csv(["Code", "Name", "Type"], ["Z1", "Z", "asset"]).encode(),
                        "text/csv")},
    )
    assert res.status_code == 403


async def test_finance_export_grant_exports_but_does_not_import(
    client, client_client, onboarded_company
):
    headers = await _limited_client(
        client, client_client, onboarded_company,
        {"dashboard": 2, "finance": 2}, "fincsvexport",
        csv_access={"export": ["finance:accounts", "finance:invoices"]},
    )
    # granted exports (accounts and the derived invoices register) work
    assert (await client.get("/api/v1/finance/export/accounts",
                             headers=headers)).status_code == 200
    assert (await client.get("/api/v1/finance/export/invoices",
                             headers=headers)).status_code == 200

    # no import grant: neither the template nor a commit is allowed
    assert (await client.get("/api/v1/finance/import/accounts/template",
                             headers=headers)).status_code == 403
    res = await client.post(
        "/api/v1/finance/import/accounts", headers=headers,
        files={"file": ("x.csv",
                        _csv(["Code", "Name", "Type"], ["Z2", "Z", "asset"]).encode(),
                        "text/csv")},
    )
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "PERMISSION_DENIED"
