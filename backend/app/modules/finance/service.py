"""Finance business logic (docs/modules/FINANCE.md §2).

Double-entry is the invariant everything else defends: no entry is written
unless sum(debit) == sum(credit). Posted documents are never edited or deleted
— a mistake is corrected by voiding, which writes a reversing entry and leaves
the original in the ledger. Every mutation writes the tenant activity_log.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from bson import ObjectId

from app.core.audit import write_activity
from app.core.errors import (
    TENANT_NOT_FOUND,
    UNBALANCED_ENTRY,
    VALIDATION_ERROR,
    DomainError,
)
from app.modules.finance import repository as repo
from app.modules.finance.models import (
    AccountCreate,
    AccountPatch,
    BillCreate,
    BillPatch,
    DocLine,
    InvoiceCreate,
    InvoicePatch,
    JournalEntryCreate,
    PaymentCreate,
)
from app.modules.finance.permissions import (
    ACCOUNT_AP,
    ACCOUNT_AR,
    ACCOUNT_COGS,
    ACCOUNT_INCOME,
    ACCOUNT_TAX,
    AGING_BUCKETS,
    CREDIT_NORMAL_TYPES,
    METHOD_ACCOUNTS,
    OPEN_STATUSES,
)
from app.tenant.deps import ClientPrincipal

# money is rounded to cents at every boundary so a float artefact can never
# make an entry fail the balance check
_CENTS = 2


def money(value: float) -> float:
    return round(float(value) + 0.0, _CENTS)


async def _log(
    principal: ClientPrincipal, action: str, entity: dict,
    details: dict | None = None,
) -> None:
    await write_activity(
        principal.tenant_db,
        actor_id=str(principal.user["_id"]),
        action=action,
        entity=entity,
        details=details or {},
        actor_name=principal.user["name"],
        module="finance",
    )


def _oid(value: str, what: str) -> ObjectId:
    try:
        return ObjectId(value)
    except Exception as exc:
        raise DomainError(TENANT_NOT_FOUND, f"{what} not found.", 404) from exc


async def _require(
    principal: ClientPrincipal, coll: str, oid: ObjectId, what: str
) -> dict:
    doc = await repo.get(principal.tenant_db, coll, oid)
    if doc is None:
        raise DomainError(TENANT_NOT_FOUND, f"{what} not found.", 404)
    return doc


async def _account(principal: ClientPrincipal, code: str) -> dict:
    """Resolve a posting account by its stable chart code."""
    acc = await repo.account_by_code(principal.tenant_db, code)
    if acc is None:
        raise DomainError(
            VALIDATION_ERROR,
            f"Chart of accounts is missing the account with code '{code}'; "
            "restore it before posting.",
            http_status=409,
        )
    return acc


# --- line maths --------------------------------------------------------------

def _priced_lines(lines: list[DocLine]) -> tuple[list[dict], float, float, float]:
    """Compute per-line amounts and the document totals (§1)."""
    out: list[dict] = []
    subtotal = tax_total = 0.0
    for line in lines:
        amount = money(line.qty * line.unit_price)
        tax = money(amount * line.tax_rate / 100)
        subtotal = money(subtotal + amount)
        tax_total = money(tax_total + tax)
        out.append({
            "description": line.description,
            "qty": line.qty,
            "unit_price": money(line.unit_price),
            "tax_rate": line.tax_rate,
            "amount": amount,
            "tax_amount": tax,
            "product_id": line.product_id,
        })
    return out, subtotal, tax_total, money(subtotal + tax_total)


def _status_for(paid: float, total: float) -> str:
    """§2 status math: 0 → sent; 0 < paid < total → partly_paid; >= → paid."""
    if paid <= 0:
        return "sent"
    if paid < total:
        return "partly_paid"
    return "paid"


# --- the double-entry core ---------------------------------------------------

async def _post_entry(
    principal: ClientPrincipal, date: datetime, memo: str,
    source: dict, lines: list[dict],
) -> dict:
    """Write one balanced journal entry, or refuse.

    This is the only path that writes to `journal_entries`; the balance check
    lives here so no caller can bypass it (§1 invariant, acceptance #1).
    """
    debit = money(sum(line.get("debit", 0) or 0 for line in lines))
    credit = money(sum(line.get("credit", 0) or 0 for line in lines))
    if debit != credit:
        raise DomainError(
            UNBALANCED_ENTRY,
            f"Entry does not balance: debits {debit:.2f} vs credits {credit:.2f}.",
            http_status=422,
            details={"debit_total": debit, "credit_total": credit},
        )
    if debit == 0:
        raise DomainError(
            UNBALANCED_ENTRY, "Entry has no value to post.", http_status=422
        )
    for line in lines:
        if (line.get("debit") or 0) > 0 and (line.get("credit") or 0) > 0:
            raise DomainError(
                UNBALANCED_ENTRY,
                "A line may carry a debit or a credit, not both.",
                http_status=422,
            )
    return await repo.insert(principal.tenant_db, repo.JOURNAL, {
        "date": date,
        "memo": memo,
        "source": source,
        "lines": lines,
        "posted": True,
        "created_by": str(principal.user["_id"]),
    })


def _line(account: dict, debit: float = 0, credit: float = 0,
          description: str | None = None) -> dict:
    return {
        "account_id": account["_id"],
        "debit": money(debit),
        "credit": money(credit),
        "description": description,
    }


# --- 1. chart of accounts ----------------------------------------------------

async def list_accounts(
    principal: ClientPrincipal, type_: str | None, is_active: bool | None,
    skip: int, limit: int,
) -> tuple[list[dict], int]:
    query: dict[str, Any] = {}
    if type_:
        query["type"] = type_
    if is_active is not None:
        query["is_active"] = is_active
    return await repo.list_docs(
        principal.tenant_db, repo.ACCOUNTS, query, skip, limit, sort=[("code", 1)]
    )


async def create_account(principal: ClientPrincipal, payload: AccountCreate) -> dict:
    db = principal.tenant_db
    if await db[repo.ACCOUNTS].find_one({"code": payload.code}):
        raise DomainError(
            VALIDATION_ERROR, f"Account code '{payload.code}' already exists.", 409
        )
    doc = payload.model_dump()
    if doc.get("parent_id"):
        parent = await _require(
            principal, repo.ACCOUNTS, _oid(doc["parent_id"], "Account"), "Parent account"
        )
        doc["parent_id"] = parent["_id"]
    doc["created_by"] = str(principal.user["_id"])
    doc = await repo.insert(db, repo.ACCOUNTS, doc)
    await _log(principal, "finance.account.created",
               {"type": "account", "id": str(doc["_id"]), "label": doc["name"]},
               {"code": doc["code"], "type": doc["type"]})
    return doc


async def patch_account(
    principal: ClientPrincipal, account_id: str, patch: AccountPatch
) -> dict:
    oid = _oid(account_id, "Account")
    account = await _require(principal, repo.ACCOUNTS, oid, "Account")
    fields = {k: v for k, v in patch.model_dump(exclude_unset=True).items() if v is not None}
    if "code" in fields and fields["code"] != account["code"]:
        if await principal.tenant_db[repo.ACCOUNTS].find_one({"code": fields["code"]}):
            raise DomainError(
                VALIDATION_ERROR, f"Account code '{fields['code']}' already exists.", 409
            )
    if "parent_id" in fields:
        fields["parent_id"] = _oid(fields["parent_id"], "Account")
    if not fields:
        return account
    fields["updated_by"] = str(principal.user["_id"])
    updated = await repo.update(principal.tenant_db, repo.ACCOUNTS, oid, fields)
    assert updated is not None
    await _log(principal, "finance.account.updated",
               {"type": "account", "id": account_id, "label": updated["name"]},
               {"fields": [k for k in fields if k != "updated_by"]})
    return updated


async def delete_account(principal: ClientPrincipal, account_id: str) -> None:
    """An account carrying ledger history can never be removed — the trial
    balance would stop reconciling. Deactivate it instead."""
    oid = _oid(account_id, "Account")
    account = await _require(principal, repo.ACCOUNTS, oid, "Account")
    used = await principal.tenant_db[repo.JOURNAL].count_documents(
        {"lines.account_id": oid}
    )
    if used:
        raise DomainError(
            VALIDATION_ERROR,
            f"Account is used by {used} journal entr{'y' if used == 1 else 'ies'}; "
            "deactivate it instead of deleting.",
            http_status=409,
        )
    await repo.soft_delete(
        principal.tenant_db, repo.ACCOUNTS, oid, str(principal.user["_id"])
    )
    await _log(principal, "finance.account.deleted",
               {"type": "account", "id": account_id, "label": account["name"]})


# --- 2. manual journal entries -----------------------------------------------

async def list_entries(
    principal: ClientPrincipal, skip: int, limit: int
) -> tuple[list[dict], int]:
    return await repo.list_docs(
        principal.tenant_db, repo.JOURNAL, {}, skip, limit, sort=[("date", -1)]
    )


async def get_entry(principal: ClientPrincipal, entry_id: str) -> dict:
    return await _require(
        principal, repo.JOURNAL, _oid(entry_id, "Journal entry"), "Journal entry"
    )


async def create_entry(
    principal: ClientPrincipal, payload: JournalEntryCreate
) -> dict:
    lines: list[dict] = []
    for line in payload.lines:
        account = await _require(
            principal, repo.ACCOUNTS, _oid(line.account_id, "Account"), "Account"
        )
        lines.append(_line(account, line.debit, line.credit, line.description))
    entry = await _post_entry(
        principal, payload.date or datetime.now(UTC), payload.memo or "Manual entry",
        {"module": "manual", "doc_id": None}, lines,
    )
    await _log(principal, "finance.journal_entry.posted",
               {"type": "journal_entry", "id": str(entry["_id"]),
                "label": entry["memo"]},
               {"lines": len(lines)})
    return entry


# --- 3. invoices (AR) --------------------------------------------------------

async def list_invoices(
    principal: ClientPrincipal, status: str | None, skip: int, limit: int
) -> tuple[list[dict], int]:
    query: dict[str, Any] = {}
    if status:
        query["status"] = status
    return await repo.list_docs(
        principal.tenant_db, repo.INVOICES, query, skip, limit,
        sort=[("issue_date", -1), ("created_at", -1)],
    )


async def get_invoice(principal: ClientPrincipal, invoice_id: str) -> dict:
    return await _require(
        principal, repo.INVOICES, _oid(invoice_id, "Invoice"), "Invoice"
    )


async def create_invoice(principal: ClientPrincipal, payload: InvoiceCreate) -> dict:
    """Creates a DRAFT. §2 says numbers must have no gaps on post, so the number
    is claimed at send time — a draft that is never sent burns no number."""
    lines, subtotal, tax_total, total = _priced_lines(payload.lines)
    if payload.inventory_issue:
        await _validate_issue_lines(principal, lines, payload.warehouse_id)
    doc = {
        "number": None,  # assigned on send
        "customer_ref": payload.customer_ref.model_dump(),
        "issue_date": payload.issue_date or datetime.now(UTC),
        "due_date": payload.due_date,
        "lines": lines,
        "subtotal": subtotal,
        "tax_total": tax_total,
        "total": total,
        "paid_amount": 0.0,
        "status": "draft",
        "currency": payload.currency,
        "inventory_issue": payload.inventory_issue,
        "warehouse_id": payload.warehouse_id,
        "notes": payload.notes,
        "created_by": str(principal.user["_id"]),
    }
    doc = await repo.insert(principal.tenant_db, repo.INVOICES, doc)
    await _log(principal, "finance.invoice.created",
               {"type": "invoice", "id": str(doc["_id"]),
                "label": payload.customer_ref.name},
               {"total": total, "status": "draft"})
    return doc


async def patch_invoice(
    principal: ClientPrincipal, invoice_id: str, patch: InvoicePatch
) -> dict:
    oid = _oid(invoice_id, "Invoice")
    invoice = await _require(principal, repo.INVOICES, oid, "Invoice")
    if invoice["status"] != "draft":
        raise DomainError(
            VALIDATION_ERROR,
            f"Invoice is {invoice['status']}; a posted document is corrected by "
            "voiding it, not by editing.",
            http_status=409,
        )
    fields = {k: v for k, v in patch.model_dump(exclude_unset=True).items() if v is not None}
    if "lines" in fields:
        lines, subtotal, tax_total, total = _priced_lines(patch.lines or [])
        fields.update({
            "lines": lines, "subtotal": subtotal,
            "tax_total": tax_total, "total": total,
        })
    if not fields:
        return invoice
    fields["updated_by"] = str(principal.user["_id"])
    updated = await repo.update(principal.tenant_db, repo.INVOICES, oid, fields)
    assert updated is not None
    await _log(principal, "finance.invoice.updated",
               {"type": "invoice", "id": invoice_id,
                "label": updated["customer_ref"]["name"]},
               {"fields": [k for k in fields if k != "updated_by"]})
    return updated


async def _validate_issue_lines(
    principal: ClientPrincipal, lines: list[dict], warehouse_id: str | None
) -> None:
    from app.modules.inventory import repository as inv_repo

    missing = [
        line["description"] for line in lines if not line.get("product_id")
    ]
    if missing:
        raise DomainError(
            VALIDATION_ERROR,
            "An inventory_issue invoice needs a product on every line; missing "
            f"on: {', '.join(missing)}.",
            http_status=422,
        )
    db = principal.tenant_db
    for line in lines:
        await _require(
            principal, inv_repo.PRODUCTS, _oid(line["product_id"], "Product"), "Product"
        )
    if warehouse_id:
        await _require(
            principal, inv_repo.WAREHOUSES, _oid(warehouse_id, "Warehouse"), "Warehouse"
        )
    elif not await db[inv_repo.WAREHOUSES].find_one({"is_deleted": {"$ne": True}}):
        raise DomainError(
            VALIDATION_ERROR, "No warehouse to issue stock from.", 409
        )


async def _issue_stock_for(principal: ClientPrincipal, invoice: dict) -> list[str]:
    """§2 inventory link + INVENTORY.md §5: one-way and explicit, referencing
    the invoice. Goes through the Inventory service so the INSUFFICIENT_STOCK
    guard and the ledger/cache invariant apply exactly as they do anywhere else.
    """
    from app.modules.inventory import repository as inv_repo
    from app.modules.inventory import service as inv_service
    from app.modules.inventory.models import MovementCreate

    db = principal.tenant_db
    warehouse_id = invoice.get("warehouse_id")
    if not warehouse_id:
        main = await db[inv_repo.WAREHOUSES].find_one(
            {"is_deleted": {"$ne": True}}, sort=[("code", 1)]
        )
        # `_validate_issue_lines` checks this first, but don't let a future
        # caller turn a missing warehouse into a None-deref 500
        if main is None:
            raise DomainError(
                VALIDATION_ERROR, "No warehouse to issue stock from.", 409
            )
        warehouse_id = str(main["_id"])

    posted: list[str] = []
    try:
        for line in invoice["lines"]:
            movement = await inv_service.create_movement(principal, MovementCreate(
                product_id=str(line["product_id"]),
                warehouse_id=warehouse_id,
                type="issue",
                qty=line["qty"],
                note=f"Invoice {invoice['number']}",
                ref_module="finance",
                ref_doc_id=str(invoice["_id"]),
            ))
            posted.append(str(movement["_id"]))
    except Exception:
        # unwind what shipped so a failed send never half-issues stock
        for movement_id in posted:
            await _reverse_issue(principal, movement_id)
        raise
    return posted


async def _reverse_issue(principal: ClientPrincipal, movement_id: str) -> None:
    """Compensate one posted issue by returning the stock and dropping the row.

    Only used to unwind a send that failed part-way — a movement that was never
    part of a completed document is not ledger history worth keeping.
    """
    from app.modules.inventory import repository as inv_repo

    db = principal.tenant_db
    movement = await db[inv_repo.MOVEMENTS].find_one({"_id": ObjectId(movement_id)})
    if movement is None:
        return
    await inv_repo.release_stock(
        db, movement["product_id"], movement["warehouse_id"], movement["qty"]
    )
    await db[inv_repo.MOVEMENTS].delete_one({"_id": movement["_id"]})


async def send_invoice(principal: ClientPrincipal, invoice_id: str) -> dict:
    """§2: sending posts Dr AR / Cr Income + Cr Tax, claims the number, and — if
    inventory_issue — issues the stock.

    Stock is issued BEFORE the journal entry: an out-of-stock send must fail
    without leaving an accounting trace behind. If the entry then fails, the
    issue is unwound.
    """
    oid = _oid(invoice_id, "Invoice")
    invoice = await _require(principal, repo.INVOICES, oid, "Invoice")
    if invoice["status"] != "draft":
        raise DomainError(
            VALIDATION_ERROR, f"Invoice is already {invoice['status']}.", 409
        )
    if money(invoice["total"]) <= 0:
        raise DomainError(VALIDATION_ERROR, "Cannot send a zero-value invoice.", 422)

    db = principal.tenant_db
    number = await repo.next_number(db, "invoice", "INV")
    invoice["number"] = number

    movements: list[str] = []
    if invoice.get("inventory_issue"):
        await _validate_issue_lines(
            principal, invoice["lines"], invoice.get("warehouse_id")
        )
        movements = await _issue_stock_for(principal, invoice)

    try:
        ar = await _account(principal, ACCOUNT_AR)
        income = await _account(principal, ACCOUNT_INCOME)
        lines = [
            _line(ar, debit=invoice["total"], description=f"Invoice {number}"),
            _line(income, credit=invoice["subtotal"], description=f"Invoice {number}"),
        ]
        if money(invoice["tax_total"]) > 0:
            tax = await _account(principal, ACCOUNT_TAX)
            lines.append(
                _line(tax, credit=invoice["tax_total"], description=f"Tax on {number}")
            )
        entry = await _post_entry(
            principal, invoice["issue_date"], f"Invoice {number}",
            {"module": "invoice", "doc_id": str(oid)}, lines,
        )
    except Exception:
        for movement_id in movements:
            await _reverse_issue(principal, movement_id)
        raise

    updated = await repo.update(db, repo.INVOICES, oid, {
        "number": number, "status": "sent",
        "journal_entry_id": entry["_id"],
        "inventory_movement_ids": movements,
        "updated_by": str(principal.user["_id"]),
    })
    assert updated is not None
    await _log(principal, "finance.invoice.sent",
               {"type": "invoice", "id": invoice_id, "label": number},
               {"total": invoice["total"], "customer": invoice["customer_ref"]["name"],
                "stock_issued": bool(movements)})
    return updated


async def void_invoice(
    principal: ClientPrincipal, invoice_id: str, reason: str
) -> dict:
    """§2: voiding reverses the journal entry — never deletes it (acceptance #4)."""
    oid = _oid(invoice_id, "Invoice")
    invoice = await _require(principal, repo.INVOICES, oid, "Invoice")
    if invoice["status"] == "void":
        raise DomainError(VALIDATION_ERROR, "Invoice is already void.", 409)
    if invoice["status"] == "draft":
        raise DomainError(
            VALIDATION_ERROR, "A draft was never posted; delete it instead.", 409
        )
    if money(invoice.get("paid_amount", 0)) > 0:
        raise DomainError(
            VALIDATION_ERROR,
            "Invoice has payments against it; reverse the payments before voiding.",
            http_status=409,
        )

    entry = await principal.tenant_db[repo.JOURNAL].find_one({
        "source.module": "invoice", "source.doc_id": str(oid), "reverses": None,
    })
    if entry is None:
        entry = await principal.tenant_db[repo.JOURNAL].find_one(
            {"_id": invoice.get("journal_entry_id")}
        )
    if entry is None:
        raise DomainError(
            VALIDATION_ERROR, "No posted entry found to reverse.", 409
        )

    reversal = await _post_entry(
        principal, datetime.now(UTC), f"Void {invoice['number']} — {reason}",
        {"module": "invoice", "doc_id": str(oid)},
        [
            {
                "account_id": line["account_id"],
                "debit": line["credit"],
                "credit": line["debit"],
                "description": f"Reversal: {line.get('description') or ''}".strip(),
            }
            for line in entry["lines"]
        ],
    )
    await principal.tenant_db[repo.JOURNAL].update_one(
        {"_id": reversal["_id"]}, {"$set": {"reverses": entry["_id"]}}
    )

    updated = await repo.update(principal.tenant_db, repo.INVOICES, oid, {
        "status": "void", "void_reason": reason,
        "voided_at": datetime.now(UTC),
        "reversal_entry_id": reversal["_id"],
        "updated_by": str(principal.user["_id"]),
    })
    assert updated is not None
    await _log(principal, "finance.invoice.voided",
               {"type": "invoice", "id": invoice_id, "label": invoice["number"]},
               {"reason": reason})
    return updated


async def delete_invoice(principal: ClientPrincipal, invoice_id: str) -> None:
    oid = _oid(invoice_id, "Invoice")
    invoice = await _require(principal, repo.INVOICES, oid, "Invoice")
    if invoice["status"] != "draft":
        raise DomainError(
            VALIDATION_ERROR,
            f"Invoice is {invoice['status']}; void it instead of deleting.", 409,
        )
    await repo.soft_delete(
        principal.tenant_db, repo.INVOICES, oid, str(principal.user["_id"])
    )
    await _log(principal, "finance.invoice.deleted",
               {"type": "invoice", "id": invoice_id,
                "label": invoice["customer_ref"]["name"]})


# --- 4. bills (AP) — the mirror of invoices (§1) ------------------------------

async def list_bills(
    principal: ClientPrincipal, status: str | None, skip: int, limit: int
) -> tuple[list[dict], int]:
    query: dict[str, Any] = {}
    if status:
        query["status"] = status
    return await repo.list_docs(
        principal.tenant_db, repo.BILLS, query, skip, limit,
        sort=[("issue_date", -1), ("created_at", -1)],
    )


async def create_bill(principal: ClientPrincipal, payload: BillCreate) -> dict:
    lines, subtotal, tax_total, total = _priced_lines(payload.lines)
    doc = {
        "number": None,
        "vendor_ref": payload.vendor_ref.model_dump(),
        "issue_date": payload.issue_date or datetime.now(UTC),
        "due_date": payload.due_date,
        "lines": lines,
        "subtotal": subtotal,
        "tax_total": tax_total,
        "total": total,
        "paid_amount": 0.0,
        "status": "draft",
        "currency": payload.currency,
        "notes": payload.notes,
        "created_by": str(principal.user["_id"]),
    }
    doc = await repo.insert(principal.tenant_db, repo.BILLS, doc)
    await _log(principal, "finance.bill.created",
               {"type": "bill", "id": str(doc["_id"]),
                "label": payload.vendor_ref.name},
               {"total": total})
    return doc


async def patch_bill(
    principal: ClientPrincipal, bill_id: str, patch: BillPatch
) -> dict:
    oid = _oid(bill_id, "Bill")
    bill = await _require(principal, repo.BILLS, oid, "Bill")
    if bill["status"] != "draft":
        raise DomainError(
            VALIDATION_ERROR, f"Bill is {bill['status']}; void it instead.", 409
        )
    fields = {k: v for k, v in patch.model_dump(exclude_unset=True).items() if v is not None}
    if "lines" in fields:
        lines, subtotal, tax_total, total = _priced_lines(patch.lines or [])
        fields.update({
            "lines": lines, "subtotal": subtotal,
            "tax_total": tax_total, "total": total,
        })
    if not fields:
        return bill
    fields["updated_by"] = str(principal.user["_id"])
    updated = await repo.update(principal.tenant_db, repo.BILLS, oid, fields)
    assert updated is not None
    await _log(principal, "finance.bill.updated",
               {"type": "bill", "id": bill_id, "label": updated["vendor_ref"]["name"]},
               {"fields": [k for k in fields if k != "updated_by"]})
    return updated


async def send_bill(principal: ClientPrincipal, bill_id: str) -> dict:
    """The mirror of an invoice: Dr COGS + Dr Tax / Cr AP.

    Input tax is debited to the same Tax Payable account the sale credits, so
    the account carries the net liability — the starter chart (§4) has one tax
    account, not separate input/output ones.
    """
    oid = _oid(bill_id, "Bill")
    bill = await _require(principal, repo.BILLS, oid, "Bill")
    if bill["status"] != "draft":
        raise DomainError(VALIDATION_ERROR, f"Bill is already {bill['status']}.", 409)
    if money(bill["total"]) <= 0:
        raise DomainError(VALIDATION_ERROR, "Cannot post a zero-value bill.", 422)

    number = await repo.next_number(principal.tenant_db, "bill", "BILL")
    cogs = await _account(principal, ACCOUNT_COGS)
    ap = await _account(principal, ACCOUNT_AP)
    lines = [_line(cogs, debit=bill["subtotal"], description=f"Bill {number}")]
    if money(bill["tax_total"]) > 0:
        tax = await _account(principal, ACCOUNT_TAX)
        lines.append(_line(tax, debit=bill["tax_total"], description=f"Tax on {number}"))
    lines.append(_line(ap, credit=bill["total"], description=f"Bill {number}"))

    entry = await _post_entry(
        principal, bill["issue_date"], f"Bill {number}",
        {"module": "bill", "doc_id": str(oid)}, lines,
    )
    updated = await repo.update(principal.tenant_db, repo.BILLS, oid, {
        "number": number, "status": "sent", "journal_entry_id": entry["_id"],
        "updated_by": str(principal.user["_id"]),
    })
    assert updated is not None
    await _log(principal, "finance.bill.sent",
               {"type": "bill", "id": bill_id, "label": number},
               {"total": bill["total"], "vendor": bill["vendor_ref"]["name"]})
    return updated


# --- 5. payments -------------------------------------------------------------

async def create_payment(principal: ClientPrincipal, payload: PaymentCreate) -> dict:
    """§2: a customer payment posts Dr Cash/Bank / Cr AR and updates
    paid_amount/status. A vendor payment mirrors it: Dr AP / Cr Cash/Bank."""
    coll = repo.INVOICES if payload.ref_doc_type == "invoice" else repo.BILLS
    what = "Invoice" if payload.ref_doc_type == "invoice" else "Bill"
    oid = _oid(payload.ref_doc_id, what)
    doc = await _require(principal, coll, oid, what)

    expected = "customer_payment" if payload.ref_doc_type == "invoice" else "vendor_payment"
    if payload.type != expected:
        raise DomainError(
            VALIDATION_ERROR,
            f"A {payload.ref_doc_type} takes a {expected}, not a {payload.type}.",
            http_status=422,
        )
    if doc["status"] in ("draft", "void"):
        raise DomainError(
            VALIDATION_ERROR,
            f"{what} is {doc['status']}; it cannot take a payment.", 409,
        )

    paid = money(doc.get("paid_amount", 0))
    total = money(doc["total"])
    outstanding = money(total - paid)
    amount = money(payload.amount)
    if amount > outstanding:
        raise DomainError(
            VALIDATION_ERROR,
            f"Payment {amount:.2f} exceeds the {outstanding:.2f} outstanding.",
            http_status=422,
            details={"outstanding": outstanding, "requested": amount},
        )

    cash = await _account(principal, METHOD_ACCOUNTS[payload.method])
    date = payload.date or datetime.now(UTC)
    label = doc.get("number") or str(oid)
    if payload.type == "customer_payment":
        ar = await _account(principal, ACCOUNT_AR)
        lines = [
            _line(cash, debit=amount, description=f"Payment for {label}"),
            _line(ar, credit=amount, description=f"Payment for {label}"),
        ]
    else:
        ap = await _account(principal, ACCOUNT_AP)
        lines = [
            _line(ap, debit=amount, description=f"Payment for {label}"),
            _line(cash, credit=amount, description=f"Payment for {label}"),
        ]
    entry = await _post_entry(
        principal, date, f"Payment for {label}",
        {"module": "payment", "doc_id": str(oid)}, lines,
    )

    payment = await repo.insert(principal.tenant_db, repo.PAYMENTS, {
        "type": payload.type,
        "ref_doc": {"type": payload.ref_doc_type, "id": str(oid)},
        "amount": amount,
        "date": date,
        "method": payload.method,
        "account_id": cash["_id"],
        "journal_entry_id": entry["_id"],
        "note": payload.note,
        "created_by": str(principal.user["_id"]),
    })

    new_paid = money(paid + amount)
    await repo.update(principal.tenant_db, coll, oid, {
        "paid_amount": new_paid,
        "status": _status_for(new_paid, total),
        "updated_by": str(principal.user["_id"]),
    })
    await _log(principal, "finance.payment.recorded",
               {"type": payload.ref_doc_type, "id": str(oid), "label": label},
               {"amount": amount, "method": payload.method,
                "paid_amount": new_paid, "status": _status_for(new_paid, total)})
    return payment


async def list_payments(
    principal: ClientPrincipal, ref_doc_id: str | None, skip: int, limit: int
) -> tuple[list[dict], int]:
    query: dict[str, Any] = {}
    if ref_doc_id:
        query["ref_doc.id"] = ref_doc_id
    return await repo.list_docs(
        principal.tenant_db, repo.PAYMENTS, query, skip, limit, sort=[("date", -1)]
    )


# --- 6. reports (§2) ---------------------------------------------------------

async def trial_balance(
    principal: ClientPrincipal, start: datetime | None, end: datetime | None
) -> dict:
    """Acceptance #3: the trial balance nets to zero."""
    rows = await repo.trial_balance(principal.tenant_db, start, end)
    out = []
    debit_total = credit_total = 0.0
    for row in rows:
        debit = money(row["debit"])
        credit = money(row["credit"])
        debit_total = money(debit_total + debit)
        credit_total = money(credit_total + credit)
        out.append({
            "account_id": str(row["_id"]),
            "code": row["account"]["code"],
            "name": row["account"]["name"],
            "type": row["account"]["type"],
            "debit": debit,
            "credit": credit,
            "balance": money(debit - credit),
        })
    return {
        "rows": out,
        "debit_total": debit_total,
        "credit_total": credit_total,
        "balanced": debit_total == credit_total,
    }


async def pnl(
    principal: ClientPrincipal, start: datetime | None, end: datetime | None
) -> dict:
    """Income − expense over a period."""
    tb = await trial_balance(principal, start, end)
    income = [r for r in tb["rows"] if r["type"] == "income"]
    expense = [r for r in tb["rows"] if r["type"] == "expense"]
    # income is credit-normal, so its balance is negative in debit-minus-credit terms
    income_total = money(-sum(r["balance"] for r in income))
    expense_total = money(sum(r["balance"] for r in expense))
    return {
        "income": [{**r, "amount": money(-r["balance"])} for r in income],
        "expense": [{**r, "amount": r["balance"]} for r in expense],
        "income_total": income_total,
        "expense_total": expense_total,
        "net_profit": money(income_total - expense_total),
        "period": {"start": start, "end": end},
    }


async def balance_sheet(principal: ClientPrincipal, end: datetime | None) -> dict:
    """Acceptance #3: assets = liabilities + equity.

    Profit for the period is not yet closed into equity, so retained earnings
    are carried explicitly — without it a live book never balances.
    """
    tb = await trial_balance(principal, None, end)

    def _sum(kind: str) -> float:
        rows = [r for r in tb["rows"] if r["type"] == kind]
        total = sum(r["balance"] for r in rows)
        return money(total if kind not in CREDIT_NORMAL_TYPES else -total)

    assets = _sum("asset")
    liabilities = _sum("liability")
    equity = _sum("equity")
    income = _sum("income")
    expense = _sum("expense")
    retained = money(income - expense)
    return {
        "assets": [r for r in tb["rows"] if r["type"] == "asset"],
        "liabilities": [r for r in tb["rows"] if r["type"] == "liability"],
        "equity": [r for r in tb["rows"] if r["type"] == "equity"],
        "assets_total": assets,
        "liabilities_total": liabilities,
        "equity_total": equity,
        "retained_earnings": retained,
        "liabilities_and_equity_total": money(liabilities + equity + retained),
        "balanced": assets == money(liabilities + equity + retained),
        "as_of": end,
    }


async def aging(principal: ClientPrincipal, kind: str) -> dict:
    """AR/AP aging: buckets by how overdue each open document is."""
    coll = repo.INVOICES if kind == "ar" else repo.BILLS
    rows = await repo.aging_rows(principal.tenant_db, coll, OPEN_STATUSES)
    now = datetime.now(UTC)

    labels = [f"{lo}-{hi}" for lo, hi in AGING_BUCKETS] + ["90+"]
    buckets: dict[str, dict] = {
        label: {"total": 0.0, "count": 0} for label in ["current", *labels]
    }
    items = []
    for row in rows:
        due = row["due_date"]
        if due.tzinfo is None:
            due = due.replace(tzinfo=UTC)
        days = (now - due).days
        if days <= 0:
            label = "current"
        else:
            label = "90+"
            for lo, hi in AGING_BUCKETS:
                if lo <= days <= hi:
                    label = f"{lo}-{hi}"
                    break
        outstanding = money(row["outstanding"])
        buckets[label]["total"] = money(buckets[label]["total"] + outstanding)
        buckets[label]["count"] += 1
        party = row.get("customer_ref") or row.get("vendor_ref") or {}
        items.append({
            "id": str(row["_id"]),
            "number": row.get("number"),
            "party": party.get("name"),
            "due_date": row["due_date"],
            "days_overdue": max(days, 0),
            "outstanding": outstanding,
            "bucket": label,
        })
    return {
        "type": kind,
        "buckets": buckets,
        "items": items,
        "total": money(sum(b["total"] for b in buckets.values())),
    }
