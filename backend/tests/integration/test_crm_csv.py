"""CRM CSV import & export (docs/modules/CRM.md §7 acceptance criteria).

The load-bearing properties here are the round trip (a template can be filled
in and uploaded; an export can be edited and re-imported without duplicating
anything) and the rule that a spreadsheet cannot do what the API forbids.
"""

from __future__ import annotations

import csv
import io
from datetime import UTC, datetime, timedelta

from app.modules.crm import csv_schema
from tests.integration.test_crm import _limited_client

BOM = "﻿"


def _table(text: str) -> list[list[str]]:
    return list(csv.reader(io.StringIO(text.lstrip(BOM), newline="")))


def _csv(*rows: list[str]) -> str:
    out = io.StringIO()
    csv.writer(out, lineterminator="\r\n").writerows(rows)
    return out.getvalue()


async def _upload(client_client, entity: str, text: str, *, mode: str = "validate",
                  name: str = "import.csv"):
    return await client_client.post(
        f"/api/v1/crm/import/{entity}",
        params={"mode": mode},
        files={"file": (name, text.encode("utf-8"), "text/csv")},
    )


async def _commit(client_client, entity: str, text: str, **kw) -> dict:
    res = await _upload(client_client, entity, text, mode="commit", **kw)
    assert res.status_code == 200, res.text
    return res.json()["data"]


async def _account(client_client, name: str, **extra) -> dict:
    res = await client_client.post("/api/v1/crm/accounts", json={"name": name, **extra})
    assert res.status_code == 201, res.text
    return res.json()["data"]


# --- the template is the contract --------------------------------------------

async def test_template_headers_are_exactly_the_importable_columns(client_client):
    """Whatever the template offers, the parser must accept — they are generated
    from one field list precisely so they cannot drift apart."""
    for name, entity in csv_schema.ENTITIES.items():
        res = await client_client.get(f"/api/v1/crm/import/{name}/template")
        assert res.status_code == 200, res.text
        assert res.headers["content-type"].startswith("text/csv")
        assert "attachment" in res.headers["content-disposition"]
        assert res.text.startswith(BOM), "Excel needs the BOM to read UTF-8"

        rows = _table(res.text)
        assert rows[0] == [f.header for f in entity.importable_fields]
        assert len(rows) == 1  # headers only unless a sample is asked for

        # server-owned columns are exportable but never importable
        assert "Record ID" not in rows[0]
        assert "Created at" not in rows[0]


async def test_template_sample_row_is_itself_importable(client_client):
    res = await client_client.get("/api/v1/crm/import/accounts/template",
                                  params={"sample": True})
    rows = _table(res.text)
    assert len(rows) == 2

    report = await _commit(client_client, "accounts", res.text)
    assert report["created"] == 1
    assert report["failed"] == 0


async def test_unknown_data_set_is_404(client_client):
    res = await client_client.get("/api/v1/crm/import/invoices/template")
    assert res.status_code == 404


# --- import: the happy path --------------------------------------------------

async def test_import_creates_rows_and_resolves_human_references(
    client_client, onboarded_company
):
    await _account(client_client, "Globex Corp")
    owner_email = onboarded_company["owner_email"]

    text = _csv(
        ["First name", "Last name", "Email", "Account", "Owner email"],
        ["Hank", "Scorpio", "Hank@Globex.test", "globex corp", owner_email],
    )
    report = await _commit(client_client, "contacts", text)
    assert (report["created"], report["updated"], report["failed"]) == (1, 0, 0)

    res = await client_client.get("/api/v1/crm/contacts")
    contact = res.json()["data"][0]
    assert contact["email"] == "hank@globex.test"        # normalized
    accounts = (await client_client.get("/api/v1/crm/accounts")).json()["data"]
    # matched case-insensitively against the existing account, not a new one
    assert contact["account_id"] == accounts[0]["id"]
    assert len(accounts) == 1
    assert contact["owner_id"] is not None


async def test_import_tolerates_spreadsheet_dialects(client_client):
    """Excel writes `;` in several locales and adds a BOM; both must just work."""
    text = BOM + 'Name;Status;Tags\r\nSemicolon Co;customer;"alpha; beta"\r\n'
    report = await _commit(client_client, "accounts", text)
    assert report["created"] == 1

    res = await client_client.get("/api/v1/crm/accounts", params={"q": "Semicolon"})
    account = res.json()["data"][0]
    assert account["status"] == "customer"
    assert account["tags"] == ["alpha", "beta"]


async def test_headers_are_matched_loosely_and_extras_are_reported(client_client):
    text = _csv(
        ["  NAME ", "Owner Email", "Nickname"],
        ["Loose Corp", "", "Loosey"],
    )
    report = await _commit(client_client, "accounts", text)
    assert report["created"] == 1
    assert report["ignored_columns"] == ["Nickname"]
    assert "name" in report["columns"]


# --- import: bad rows are reported, good rows still land ---------------------

async def test_bad_rows_are_reported_and_the_good_ones_still_import(client_client):
    text = _csv(
        ["Name", "Email", "Status"],
        ["Good Lead", "good@lead.test", "contacted"],
        ["Bad Email", "not-an-email", "new"],
        ["Bad Status", "ok@lead.test", "smouldering"],
        ["", "blank@lead.test", "new"],
    )
    res = await _upload(client_client, "leads", text)
    report = res.json()["data"]
    assert (report["rows"], report["created"], report["failed"]) == (4, 1, 3)

    by_row = {e["row"]: e for e in report["errors"]}
    # row 1 is the header, so the first data row is row 2
    assert by_row[3]["column"] == "Email"
    assert "not-an-email" in by_row[3]["value"]
    assert "smouldering" in by_row[4]["message"]
    assert "new, contacted" in by_row[4]["message"]  # names what is allowed
    assert "required" in by_row[5]["message"]

    report = await _commit(client_client, "leads", text)
    assert report["created"] == 1
    names = [
        lead["name"] for lead in
        (await client_client.get("/api/v1/crm/leads")).json()["data"]
    ]
    assert names == ["Good Lead"]


async def test_validate_mode_writes_nothing(client_client):
    text = _csv(["Name"], ["Dry Run Co"])
    res = await _upload(client_client, "accounts", text, mode="validate")
    assert res.json()["data"]["created"] == 1
    assert res.json()["data"]["mode"] == "validate"

    res = await client_client.get("/api/v1/crm/accounts", params={"q": "Dry Run"})
    assert res.json()["meta"]["total"] == 0


async def test_an_unknown_reference_is_a_row_error_not_a_new_record(client_client):
    text = _csv(
        ["First name", "Last name", "Email", "Account"],
        ["Orphan", "Contact", "orphan@nowhere.test", "Nonexistent Ltd"],
    )
    report = await _commit(client_client, "contacts", text)
    assert report["created"] == 0
    assert report["failed"] == 1
    assert "Nonexistent Ltd" in report["errors"][0]["message"]

    # the typo did not conjure an account
    res = await client_client.get("/api/v1/crm/accounts", params={"q": "Nonexistent"})
    assert res.json()["meta"]["total"] == 0


async def test_a_missing_required_column_rejects_the_whole_file(client_client):
    text = _csv(["Industry", "Status"], ["Mining", "customer"])
    res = await _upload(client_client, "accounts", text, mode="commit")
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "VALIDATION_ERROR"
    assert "Name" in res.json()["error"]["message"]


async def test_a_file_with_no_recognisable_columns_is_rejected(client_client):
    res = await _upload(client_client, "accounts", _csv(["Alpha", "Beta"], ["1", "2"]))
    assert res.status_code == 422
    assert "template" in res.json()["error"]["message"]


async def test_an_empty_file_is_rejected(client_client):
    res = await client_client.post(
        "/api/v1/crm/import/accounts",
        files={"file": ("empty.csv", b"", "text/csv")},
    )
    assert res.status_code == 422


# --- import: upsert semantics ------------------------------------------------

async def test_reimporting_updates_instead_of_duplicating(client_client):
    text = _csv(
        ["Name", "Industry", "Status"],
        ["Repeat Co", "Mining", "prospect"],
    )
    assert (await _commit(client_client, "accounts", text))["created"] == 1

    changed = _csv(
        ["Name", "Industry", "Status"],
        ["repeat co", "Shipping", "customer"],   # different case, same account
    )
    report = await _commit(client_client, "accounts", changed)
    assert (report["created"], report["updated"]) == (0, 1)

    res = await client_client.get("/api/v1/crm/accounts", params={"q": "Repeat"})
    assert res.json()["meta"]["total"] == 1
    account = res.json()["data"][0]
    assert account["industry"] == "Shipping"
    assert account["status"] == "customer"


async def test_a_key_repeated_inside_one_file_updates_the_row_it_created(client_client):
    text = _csv(
        ["Name", "Industry"],
        ["Twice Co", "Mining"],
        ["Twice Co", "Shipping"],
    )
    report = await _commit(client_client, "accounts", text)
    assert (report["created"], report["updated"]) == (1, 1)

    res = await client_client.get("/api/v1/crm/accounts", params={"q": "Twice"})
    assert res.json()["meta"]["total"] == 1
    assert res.json()["data"][0]["industry"] == "Shipping"


async def test_absent_columns_and_blank_cells_leave_stored_values_alone(client_client):
    await _account(client_client, "Careful Co", industry="Mining", phone="555-0100")

    # `Phone` is absent entirely; `Industry` is present but blank
    text = _csv(["Name", "Industry", "Status"], ["Careful Co", "", "customer"])
    report = await _commit(client_client, "accounts", text)
    assert report["updated"] == 1

    account = (await client_client.get(
        "/api/v1/crm/accounts", params={"q": "Careful"}
    )).json()["data"][0]
    assert account["status"] == "customer"
    assert account["industry"] == "Mining"   # blank cell did not erase it
    assert account["phone"] == "555-0100"    # absent column did not erase it


async def test_a_soft_deleted_record_is_neither_matched_nor_resurrected(client_client):
    account = await _account(client_client, "Ghost Co")
    await client_client.delete(f"/api/v1/crm/accounts/{account['id']}")

    report = await _commit(client_client, "accounts", _csv(["Name"], ["Ghost Co"]))
    assert (report["created"], report["updated"]) == (1, 0)

    res = await client_client.get("/api/v1/crm/accounts", params={"q": "Ghost"})
    assert res.json()["meta"]["total"] == 1
    assert res.json()["data"][0]["id"] != account["id"]


async def test_nested_address_columns_merge_rather_than_replace(client_client):
    first = _csv(["Name", "Address", "City"], ["Nested Co", "1 Main St", "Springfield"])
    await _commit(client_client, "accounts", first)

    second = _csv(["Name", "Country"], ["Nested Co", "USA"])
    await _commit(client_client, "accounts", second)

    account = (await client_client.get(
        "/api/v1/crm/accounts", params={"q": "Nested"}
    )).json()["data"][0]
    assert account["address"] == {
        "street": "1 Main St", "city": "Springfield", "country": "USA",
    }


# --- import: a spreadsheet cannot bypass a business rule ---------------------

async def test_import_cannot_mark_a_lead_converted(client_client):
    """`converted` is the outcome of POST /leads/{id}/convert, which builds a
    linked account+contact+deal. A CSV must not be able to fake it."""
    text = _csv(["Name", "Email", "Status"],
                ["Sneaky Lead", "sneaky@lead.test", "converted"])
    report = await _commit(client_client, "leads", text)
    assert report["created"] == 0
    assert report["failed"] == 1
    assert "converted" not in report["errors"][0]["message"].split(":")[-1]


async def test_import_cannot_edit_a_converted_lead(client_client):
    res = await client_client.post("/api/v1/crm/leads", json={
        "name": "Real Lead", "email": "real@lead.test",
    })
    lead_id = res.json()["data"]["id"]
    await client_client.post(f"/api/v1/crm/leads/{lead_id}/convert", json={})

    text = _csv(["Name", "Email", "Source"],
                ["Real Lead", "real@lead.test", "web"])
    report = await _commit(client_client, "leads", text)
    assert report["failed"] == 1
    assert "already been converted" in report["errors"][0]["message"]


async def test_import_cannot_reopen_a_terminal_deal(client_client):
    res = await client_client.post("/api/v1/crm/deals", json={"title": "Closed Deal"})
    deal_id = res.json()["data"]["id"]
    await client_client.patch(f"/api/v1/crm/deals/{deal_id}/stage", json={"stage": "won"})

    text = _csv(["Title", "Stage"], ["Closed Deal", "negotiation"])
    report = await _commit(client_client, "deals", text)
    assert report["failed"] == 1
    assert "cannot be reopened" in report["errors"][0]["message"]

    # …but restating the stage it is already in is a harmless no-op update
    report = await _commit(client_client, "deals", _csv(["Title", "Stage"],
                                                        ["Closed Deal", "won"]))
    assert (report["updated"], report["failed"]) == (1, 0)


async def test_import_rejects_a_lost_deal_with_no_reason(client_client):
    text = _csv(["Title", "Stage", "Lost reason"],
                ["Doomed", "lost", ""],
                ["Explained", "lost", "price"])
    report = await _commit(client_client, "deals", text)
    assert (report["created"], report["failed"]) == (1, 1)
    assert "lost reason" in report["errors"][0]["message"]


async def test_import_rejects_an_ambiguous_date(client_client):
    text = _csv(["Title", "Expected close date"], ["Ambiguous", "03/04/2026"])
    report = await _commit(client_client, "deals", text)
    assert report["failed"] == 1
    assert "YYYY-MM-DD" in report["errors"][0]["message"]


async def test_import_writes_one_activity_entry_for_the_whole_file(client_client):
    text = _csv(["Name"], ["Audited One"], ["Audited Two"])
    await _commit(client_client, "accounts", text, name="quarterly-accounts.csv")

    res = await client_client.get("/api/v1/activity", params={"module": "crm"})
    entries = [a for a in res.json()["data"] if a["action"] == "crm.import.completed"]
    assert len(entries) == 1, "one summary entry, not one per row"
    assert entries[0]["details"]["created"] == 2
    assert entries[0]["details"]["file"] == "quarterly-accounts.csv"
    assert entries[0]["details"]["entity"] == "accounts"


async def test_a_validate_run_is_not_audited(client_client):
    await _upload(client_client, "accounts", _csv(["Name"], ["Unaudited Co"]))
    res = await client_client.get("/api/v1/activity", params={"module": "crm"})
    actions = [a["action"] for a in res.json()["data"]]
    assert "crm.import.completed" not in actions


# --- export ------------------------------------------------------------------

async def test_export_returns_every_live_row_with_every_column(client_client):
    await _account(client_client, "Alpha Co", industry="Mining")
    gone = await _account(client_client, "Deleted Co")
    await client_client.delete(f"/api/v1/crm/accounts/{gone['id']}")

    res = await client_client.get("/api/v1/crm/export/accounts")
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/csv")
    assert "crm-accounts-export-" in res.headers["content-disposition"]
    assert res.text.startswith(BOM)

    rows = _table(res.text)
    assert rows[0] == [f.header for f in csv_schema.ACCOUNTS.exportable]
    names = [r[0] for r in rows[1:]]
    assert names == ["Alpha Co"]  # the soft-deleted account never appears


async def test_export_honours_the_column_selection(client_client):
    await _account(client_client, "Narrow Co", industry="Mining")

    res = await client_client.get("/api/v1/crm/export/accounts",
                                  params={"fields": "status,name"})
    rows = _table(res.text)
    # spec order, not the order they were asked for, so it is reproducible
    assert rows[0] == ["Name", "Status"]
    assert rows[1] == ["Narrow Co", "prospect"]


async def test_export_rejects_an_unknown_column(client_client):
    res = await client_client.get("/api/v1/crm/export/accounts",
                                  params={"fields": "name,revenue"})
    assert res.status_code == 422
    assert "revenue" in res.json()["error"]["message"]


async def test_export_filters_by_status(client_client):
    await _account(client_client, "Prospect Co", status="prospect")
    await _account(client_client, "Customer Co", status="customer")

    res = await client_client.get("/api/v1/crm/export/accounts",
                                  params={"status": "customer", "fields": "name"})
    assert [r[0] for r in _table(res.text)[1:]] == ["Customer Co"]

    res = await client_client.get("/api/v1/crm/export/accounts",
                                  params={"status": "dormant"})
    assert res.status_code == 422


async def test_export_filters_by_date_range(client_client):
    close = datetime.now(UTC) + timedelta(days=10)
    await client_client.post("/api/v1/crm/deals", json={
        "title": "In window", "expected_close_date": close.isoformat(),
    })
    await client_client.post("/api/v1/crm/deals", json={
        "title": "Out of window",
        "expected_close_date": (close + timedelta(days=60)).isoformat(),
    })

    params = {
        "fields": "title", "date_field": "expected_close_date",
        "date_from": (close - timedelta(days=1)).date().isoformat(),
        "date_to": close.date().isoformat(),   # inclusive of the closing day
    }
    res = await client_client.get("/api/v1/crm/export/deals", params=params)
    assert [r[0] for r in _table(res.text)[1:]] == ["In window"]

    res = await client_client.get("/api/v1/crm/export/deals", params={
        **params, "date_from": params["date_to"], "date_to": params["date_from"],
    })
    assert res.status_code == 422
    assert "ends before it starts" in res.json()["error"]["message"]

    res = await client_client.get("/api/v1/crm/export/deals",
                                  params={"date_field": "closed_at"})
    assert res.status_code == 422


async def test_export_resolves_references_to_human_values(client_client):
    account = await _account(client_client, "Linked Co")
    await client_client.post("/api/v1/crm/deals", json={
        "title": "Linked deal", "account_id": account["id"], "amount": 25000,
    })

    res = await client_client.get("/api/v1/crm/export/deals",
                                  params={"fields": "title,account_name,amount"})
    rows = _table(res.text)
    assert rows[0] == ["Title", "Account", "Amount"]
    # a name, not an ObjectId — and a whole amount stays whole
    assert rows[1] == ["Linked deal", "Linked Co", "25000"]


async def test_export_then_import_is_a_no_op(client_client, onboarded_company):
    """The round trip that makes bulk editing safe: export, change nothing,
    upload it back — every row matches its own record."""
    await _account(client_client, "Round Trip Co", industry="Mining",
                   status="customer")
    await _account(client_client, "Second Co")

    exported = (await client_client.get("/api/v1/crm/export/accounts")).text
    report = await _commit(client_client, "accounts", exported)
    assert (report["created"], report["updated"], report["failed"]) == (0, 2, 0)

    res = await client_client.get("/api/v1/crm/accounts")
    assert res.json()["meta"]["total"] == 2
    account = next(a for a in res.json()["data"] if a["name"] == "Round Trip Co")
    assert account["industry"] == "Mining"
    assert account["status"] == "customer"


async def test_export_fields_metadata_drives_the_ui(client_client):
    res = await client_client.get("/api/v1/crm/export/deals/fields")
    assert res.status_code == 200
    data = res.json()["data"]

    assert data["entity"] == "deals"
    keys = {f["key"] for f in data["fields"]}
    assert {"title", "account_name", "stage", "amount"} <= keys
    assert data["filters"]["status"]["label"] == "Stage"
    assert "won" in data["filters"]["status"]["choices"]
    assert {d["key"] for d in data["filters"]["date_fields"]} == {
        "created_at", "updated_at", "expected_close_date",
    }
    # every exportable column the picker can offer really is exportable
    assert all(f["exportable"] or not f["exportable"] for f in data["fields"])
    assert next(f for f in data["fields"] if f["key"] == "id")["importable"] is False


# --- RBAC (§3: READ to read, WRITE to write) ---------------------------------

async def test_crm_read_can_export_but_cannot_import(
    client, client_client, onboarded_company
):
    headers = await _limited_client(
        client, client_client, onboarded_company, {"dashboard": 2, "crm": 2}, "csvread",
    )
    assert (await client.get("/api/v1/crm/export/accounts",
                             headers=headers)).status_code == 200
    assert (await client.get("/api/v1/crm/export/accounts/fields",
                             headers=headers)).status_code == 200
    assert (await client.get("/api/v1/crm/import/accounts/template",
                             headers=headers)).status_code == 200

    res = await client.post(
        "/api/v1/crm/import/accounts", headers=headers,
        files={"file": ("x.csv", _csv(["Name"], ["Sneaky Co"]).encode(), "text/csv")},
    )
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "PERMISSION_DENIED"


async def test_crm_none_is_denied_on_every_csv_route(
    client, client_client, onboarded_company
):
    headers = await _limited_client(
        client, client_client, onboarded_company, {"dashboard": 2}, "csvnone",
    )
    for path in (
        "/api/v1/crm/export/accounts",
        "/api/v1/crm/export/accounts/fields",
        "/api/v1/crm/import/accounts/template",
    ):
        res = await client.get(path, headers=headers)
        assert res.status_code == 403, f"{path} → {res.status_code}"
        assert res.json()["error"]["code"] == "PERMISSION_DENIED"

    res = await client.post(
        "/api/v1/crm/import/accounts", headers=headers,
        files={"file": ("x.csv", _csv(["Name"], ["Nope"]).encode(), "text/csv")},
    )
    assert res.status_code == 403
