"""CSV import approval workflow (docs/modules/SETTINGS.md §1.3).

The per-tab import grant comes in two strengths. A plain `import` grant lets a
role *stage* an import: the file is held and a pending request is opened for
someone holding `approve_import` to commit or reject. That approver — and anyone
who holds approve on a tab — imports directly, because approve implies import and
an approver's own import needs no second sign-off.

Approval re-reads and re-validates the staged file against data as it stands at
approve time, so it commits what is true now, not the snapshot taken when the
file was uploaded. These properties are engine-level, so they hold identically
for CRM and Inventory; the tests drive both.
"""

from __future__ import annotations

import csv
import io

from tests.integration.test_crm import _limited_client


def _csv(*rows: list[str]) -> str:
    out = io.StringIO()
    csv.writer(out, lineterminator="\r\n").writerows(rows)
    return out.getvalue()


async def _import(caller, module: str, entity: str, text: str, *,
                  mode: str = "commit", name: str = "import.csv", headers=None):
    """POST an import as `caller` — an authenticated client, or the shared client
    plus a limited role's `headers`."""
    kw = {"headers": headers} if headers is not None else {}
    return await caller.post(
        f"/api/v1/{module}/import/{entity}",
        params={"mode": mode},
        files={"file": (name, text.encode("utf-8"), "text/csv")},
        **kw,
    )


async def _importer(client, client_client, company, module, keys, who):
    """Headers for a role that may import (but not approve) `keys`, with module
    READ so the grant takes effect."""
    return await _limited_client(
        client, client_client, company, {"dashboard": 2, module: 2}, who,
        csv_access={"import": list(keys)},
    )


async def _approver(client, client_client, company, module, keys, who):
    """Headers for a role that may approve (⇒ import) `keys`."""
    return await _limited_client(
        client, client_client, company, {"dashboard": 2, module: 2}, who,
        csv_access={"approve_import": list(keys)},
    )


async def _feed(client_client, module: str, action: str) -> list[dict]:
    res = await client_client.get("/api/v1/activity", params={"module": module})
    return [a for a in res.json()["data"] if a["action"] == action]


# --- staging: a non-approver's commit becomes a request ----------------------

async def test_a_non_approver_commit_is_staged_not_written(
    client, client_client, onboarded_company
):
    """The load-bearing rule: someone who may import but not approve cannot write
    directly. Their commit opens a pending request and touches no data."""
    req = await _importer(client, client_client, onboarded_company,
                          "crm", ["crm:accounts"], "req1")
    res = await _import(client, "crm", "accounts",
                        _csv(["Name", "Status"], ["Staged Co", "prospect"]),
                        headers=req, name="new-accounts.csv")
    assert res.status_code == 200, res.text
    data = res.json()["data"]
    assert data["status"] == "pending_approval"
    assert data["request_id"]
    assert data["created"] == 1              # the dry-run preview: what WOULD land

    # nothing actually landed
    found = await client_client.get("/api/v1/crm/accounts", params={"q": "Staged"})
    assert found.json()["meta"]["total"] == 0


async def test_the_inbox_lists_a_request_and_approval_commits_it(
    client, client_client, onboarded_company
):
    req = await _importer(client, client_client, onboarded_company,
                          "crm", ["crm:accounts"], "req2")
    staged = (await _import(client, "crm", "accounts", _csv(["Name"], ["Inbox Co"]),
                            headers=req, name="q3.csv")).json()["data"]
    rid = staged["request_id"]

    # the owner is grandfathered into approve on every tab, so the pending
    # request shows up in the inbox with the requester and the preview counts
    inbox = (await client_client.get("/api/v1/crm/import-requests")).json()["data"]
    entry = next(e for e in inbox if e["id"] == rid)
    assert entry["status"] == "pending"
    assert entry["entity"] == "accounts"
    assert entry["filename"] == "q3.csv"
    assert entry["requested_by_name"] == "req2"
    assert entry["preview"]["created"] == 1

    res = await client_client.post(f"/api/v1/crm/import-requests/{rid}/approve")
    assert res.status_code == 200, res.text
    assert res.json()["data"]["status"] == "approved"

    # the row is committed now, and the request cannot be approved twice
    found = await client_client.get("/api/v1/crm/accounts", params={"q": "Inbox"})
    assert found.json()["meta"]["total"] == 1
    again = await client_client.post(f"/api/v1/crm/import-requests/{rid}/approve")
    assert again.status_code == 409


async def test_reject_discards_the_file_and_writes_nothing(
    client, client_client, onboarded_company
):
    req = await _importer(client, client_client, onboarded_company,
                          "crm", ["crm:accounts"], "req3")
    rid = (await _import(client, "crm", "accounts", _csv(["Name"], ["Rejected Co"]),
                         headers=req)).json()["data"]["request_id"]

    res = await client_client.post(f"/api/v1/crm/import-requests/{rid}/reject",
                                   json={"reason": "Not this quarter"})
    assert res.status_code == 200, res.text
    assert res.json()["data"]["status"] == "rejected"

    found = await client_client.get("/api/v1/crm/accounts", params={"q": "Rejected"})
    assert found.json()["meta"]["total"] == 0

    # the requester sees their own request, now rejected, with the reason
    mine = (await client.get("/api/v1/crm/import-requests", params={"mine": True},
                             headers=req)).json()["data"]
    entry = next(e for e in mine if e["id"] == rid)
    assert entry["status"] == "rejected"
    assert entry["reject_reason"] == "Not this quarter"

    # the staged file is gone: it can be neither downloaded nor re-approved
    assert (await client_client.get(
        f"/api/v1/crm/import-requests/{rid}/file")).status_code == 404
    assert (await client_client.post(
        f"/api/v1/crm/import-requests/{rid}/approve")).status_code == 409


# --- approve implies import --------------------------------------------------

async def test_an_approver_imports_directly_with_no_request(
    client, client_client, onboarded_company
):
    """Holding only `approve_import` still lets a role import — and because it may
    approve, its own import commits at once and opens no request."""
    appr = await _approver(client, client_client, onboarded_company,
                           "crm", ["crm:accounts"], "appr4")

    # approve ⇒ import: the import-only template surface is available
    assert (await client.get("/api/v1/crm/import/accounts/template",
                             headers=appr)).status_code == 200

    res = await _import(client, "crm", "accounts", _csv(["Name"], ["Direct Co"]),
                        headers=appr)
    assert res.status_code == 200, res.text
    data = res.json()["data"]
    assert data["status"] == "committed"     # committed, not pending_approval
    assert data["created"] == 1

    found = await client_client.get("/api/v1/crm/accounts", params={"q": "Direct"})
    assert found.json()["meta"]["total"] == 1
    # a direct commit opens no approval request
    inbox = (await client.get("/api/v1/crm/import-requests", headers=appr)).json()["data"]
    assert inbox == []


async def test_requests_are_scoped_to_the_tabs_you_can_approve(
    client, client_client, onboarded_company
):
    """An approver sees and acts on only the tabs it holds approve for; a request
    for any other tab is neither listed nor approvable by it."""
    req = await _importer(client, client_client, onboarded_company,
                          "crm", ["crm:accounts", "crm:leads"], "req5")
    acc_rid = (await _import(client, "crm", "accounts", _csv(["Name"], ["Scope Acc"]),
                             headers=req)).json()["data"]["request_id"]
    lead_rid = (await _import(client, "crm", "leads",
                              _csv(["Name", "Email"], ["Scope Lead", "s@l.test"]),
                              headers=req)).json()["data"]["request_id"]

    appr = await _approver(client, client_client, onboarded_company,
                           "crm", ["crm:accounts"], "appr5")
    inbox = (await client.get("/api/v1/crm/import-requests", headers=appr)).json()["data"]
    ids = {e["id"] for e in inbox}
    assert acc_rid in ids
    assert lead_rid not in ids               # leads is out of this approver's scope

    # the out-of-scope request cannot be approved even by id
    res = await client.post(f"/api/v1/crm/import-requests/{lead_rid}/approve",
                            headers=appr)
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "PERMISSION_DENIED"
    # the in-scope one can
    res = await client.post(f"/api/v1/crm/import-requests/{acc_rid}/approve",
                            headers=appr)
    assert res.status_code == 200, res.text


# --- re-validation at approve time -------------------------------------------

async def test_approval_revalidates_against_current_data(
    client, client_client, onboarded_company
):
    """Approval validates the file against data as it stands now. A reference that
    vanished between request and approval turns a once-valid row into a failed one
    — approval never commits a stale snapshot."""
    account = (await client_client.post(
        "/api/v1/crm/accounts", json={"name": "Vanishing Co"})).json()["data"]

    req = await _importer(client, client_client, onboarded_company,
                          "crm", ["crm:contacts"], "req6")
    staged = (await _import(
        client, "crm", "contacts",
        _csv(["First name", "Last name", "Email", "Account"],
             ["Vera", "Nish", "vera@vanishing.test", "Vanishing Co"]),
        headers=req)).json()["data"]
    assert (staged["created"], staged["failed"]) == (1, 0)   # valid when staged
    rid = staged["request_id"]

    # the referenced account is removed before the approver acts
    await client_client.delete(f"/api/v1/crm/accounts/{account['id']}")

    report = (await client_client.post(
        f"/api/v1/crm/import-requests/{rid}/approve")).json()["data"]
    assert (report["created"], report["failed"]) == (0, 1)
    assert "Vanishing Co" in report["errors"][0]["message"]

    # and no orphaned contact was written
    found = await client_client.get("/api/v1/crm/contacts", params={"q": "Vera"})
    assert found.json()["meta"]["total"] == 0


async def test_inventory_approval_catches_an_over_issue_at_approve_time(
    client, client_client, onboarded_company
):
    """The staged file is re-run through create_movement at approve time, so an
    issue that stock covered when requested but not when approved is refused. The
    ledger's negative-stock guard is not bypassable via the approval queue."""
    product = (await client_client.post(
        "/api/v1/inventory/products",
        json={"sku": "APVR-1", "name": "Approve item"})).json()["data"]
    warehouse = (await client_client.post(
        "/api/v1/inventory/warehouses",
        json={"code": "APWH", "name": "Approve WH"})).json()["data"]

    async def move(mtype: str, qty: float):
        res = await client_client.post("/api/v1/inventory/movements", json={
            "product_id": product["id"], "warehouse_id": warehouse["id"],
            "type": mtype, "qty": qty,
        })
        assert res.status_code == 201, res.text

    await move("receipt", 100)               # on hand: 100

    # a requester stages an issue of 80 — coverable now (a dry run never claims
    # stock; sufficiency is only decided when the movement is written)
    req = await _importer(client, client_client, onboarded_company,
                          "inventory", ["inventory:movements"], "invreq")
    rid = (await _import(client, "inventory", "movements",
                         _csv(["SKU", "Warehouse", "Type", "Qty"],
                              ["APVR-1", "APWH", "issue", "80"]),
                         headers=req)).json()["data"]["request_id"]

    await move("issue", 70)                   # meanwhile drops on hand to 30

    # approving the staged 80-issue now over-issues → refused at approve time
    report = (await client_client.post(
        f"/api/v1/inventory/import-requests/{rid}/approve")).json()["data"]
    assert (report["created"], report["failed"]) == (0, 1)
    assert "on hand" in report["errors"][0]["message"]

    # on hand is untouched by the refused approval and the ledger stays consistent
    levels = (await client_client.get(
        "/api/v1/inventory/stock-levels",
        params={"product_id": product["id"]})).json()["data"]
    assert sum(float(r["on_hand"]) for r in levels) == 30
    assert (await client_client.get(
        "/api/v1/inventory/reconcile")).json()["data"]["consistent"] is True


# --- audit -------------------------------------------------------------------

async def test_each_workflow_step_is_audited_once(
    client, client_client, onboarded_company
):
    """One activity entry per decision: a request when staged, an approval when
    committed — and never a direct-commit entry for a staged file."""
    req = await _importer(client, client_client, onboarded_company,
                          "crm", ["crm:accounts"], "req7")
    rid = (await _import(client, "crm", "accounts", _csv(["Name"], ["Audit Co"]),
                         headers=req, name="audit.csv")).json()["data"]["request_id"]

    requested = await _feed(client_client, "crm", "crm.import.requested")
    assert len(requested) == 1
    assert requested[0]["details"]["file"] == "audit.csv"
    assert requested[0]["details"]["request_id"] == rid
    assert await _feed(client_client, "crm", "crm.import.completed") == []

    await client_client.post(f"/api/v1/crm/import-requests/{rid}/approve")
    approved = await _feed(client_client, "crm", "crm.import.approved")
    assert len(approved) == 1
    assert approved[0]["details"]["created"] == 1
    assert approved[0]["details"]["request_id"] == rid
    # still exactly one request entry, and staging never logged a direct commit
    assert len(await _feed(client_client, "crm", "crm.import.requested")) == 1
    assert await _feed(client_client, "crm", "crm.import.completed") == []
