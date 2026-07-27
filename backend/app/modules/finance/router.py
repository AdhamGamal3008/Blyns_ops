"""Finance API (docs/modules/FINANCE.md §3).

GET/reports → finance READ; posting and payments → finance WRITE. §3: "Finance
is the module most likely restricted to READ for many roles — enforce strictly."

Journal entries have no PATCH/DELETE: the ledger is append-only, and a mistake
is corrected by a void's reversing entry (§2).
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query

from app.modules.finance import service
from app.modules.finance.csv_schema import ENTITIES as CSV_ENTITIES
from app.modules.finance.models import (
    AccountCreate,
    AccountPatch,
    BillCreate,
    BillPatch,
    InvoiceCreate,
    InvoicePatch,
    JournalEntryCreate,
    PaymentCreate,
    VoidBody,
)
from app.shared.csv_router import csv_routes
from app.shared.enums import Level
from app.shared.schemas import PaginationParams, envelope, page_meta, to_api
from app.tenant.deps import ClientPrincipal, require

router = APIRouter(prefix="/api/v1/finance", tags=["client-finance"])

_read = require("finance", Level.READ)
_write = require("finance", Level.WRITE)


# --- chart of accounts -------------------------------------------------------

@router.get("/accounts")
async def list_accounts(
    page: PaginationParams = Depends(),
    type: str | None = None,
    is_active: bool | None = None,
    principal: ClientPrincipal = Depends(_read),
):
    docs, total = await service.list_accounts(
        principal, type, is_active, page.skip, page.page_size
    )
    return envelope(to_api(docs), page_meta(page.page, page.page_size, total))


@router.post("/accounts", status_code=201)
async def create_account(
    body: AccountCreate, principal: ClientPrincipal = Depends(_write)
):
    return envelope(to_api(await service.create_account(principal, body)))


@router.patch("/accounts/{account_id}")
async def patch_account(
    account_id: str, body: AccountPatch, principal: ClientPrincipal = Depends(_write)
):
    return envelope(to_api(await service.patch_account(principal, account_id, body)))


@router.delete("/accounts/{account_id}")
async def delete_account(account_id: str, principal: ClientPrincipal = Depends(_write)):
    await service.delete_account(principal, account_id)
    return envelope({"deleted": True})


# --- journal entries ---------------------------------------------------------

@router.get("/journal-entries")
async def list_entries(
    page: PaginationParams = Depends(),
    principal: ClientPrincipal = Depends(_read),
):
    docs, total = await service.list_entries(principal, page.skip, page.page_size)
    return envelope(to_api(docs), page_meta(page.page, page.page_size, total))


@router.post("/journal-entries", status_code=201)
async def create_entry(
    body: JournalEntryCreate, principal: ClientPrincipal = Depends(_write)
):
    return envelope(to_api(await service.create_entry(principal, body)))


@router.get("/journal-entries/{entry_id}")
async def get_entry(entry_id: str, principal: ClientPrincipal = Depends(_read)):
    return envelope(to_api(await service.get_entry(principal, entry_id)))


# --- invoices (AR) -----------------------------------------------------------

@router.get("/invoices")
async def list_invoices(
    page: PaginationParams = Depends(),
    status: str | None = None,
    principal: ClientPrincipal = Depends(_read),
):
    docs, total = await service.list_invoices(
        principal, status, page.skip, page.page_size
    )
    return envelope(to_api(docs), page_meta(page.page, page.page_size, total))


@router.post("/invoices", status_code=201)
async def create_invoice(
    body: InvoiceCreate, principal: ClientPrincipal = Depends(_write)
):
    return envelope(to_api(await service.create_invoice(principal, body)))


@router.get("/invoices/{invoice_id}")
async def get_invoice(invoice_id: str, principal: ClientPrincipal = Depends(_read)):
    return envelope(to_api(await service.get_invoice(principal, invoice_id)))


@router.patch("/invoices/{invoice_id}")
async def patch_invoice(
    invoice_id: str, body: InvoicePatch, principal: ClientPrincipal = Depends(_write)
):
    return envelope(to_api(await service.patch_invoice(principal, invoice_id, body)))


@router.delete("/invoices/{invoice_id}")
async def delete_invoice(invoice_id: str, principal: ClientPrincipal = Depends(_write)):
    await service.delete_invoice(principal, invoice_id)
    return envelope({"deleted": True})


@router.post("/invoices/{invoice_id}/send")
async def send_invoice(invoice_id: str, principal: ClientPrincipal = Depends(_write)):
    return envelope(to_api(await service.send_invoice(principal, invoice_id)))


@router.post("/invoices/{invoice_id}/void")
async def void_invoice(
    invoice_id: str, body: VoidBody, principal: ClientPrincipal = Depends(_write)
):
    return envelope(to_api(await service.void_invoice(principal, invoice_id, body.reason)))


# --- bills (AP) --------------------------------------------------------------

@router.get("/bills")
async def list_bills(
    page: PaginationParams = Depends(),
    status: str | None = None,
    principal: ClientPrincipal = Depends(_read),
):
    docs, total = await service.list_bills(principal, status, page.skip, page.page_size)
    return envelope(to_api(docs), page_meta(page.page, page.page_size, total))


@router.post("/bills", status_code=201)
async def create_bill(body: BillCreate, principal: ClientPrincipal = Depends(_write)):
    return envelope(to_api(await service.create_bill(principal, body)))


@router.patch("/bills/{bill_id}")
async def patch_bill(
    bill_id: str, body: BillPatch, principal: ClientPrincipal = Depends(_write)
):
    return envelope(to_api(await service.patch_bill(principal, bill_id, body)))


@router.post("/bills/{bill_id}/send")
async def send_bill(bill_id: str, principal: ClientPrincipal = Depends(_write)):
    return envelope(to_api(await service.send_bill(principal, bill_id)))


# --- payments ----------------------------------------------------------------

@router.get("/payments")
async def list_payments(
    page: PaginationParams = Depends(),
    ref_doc_id: str | None = None,
    principal: ClientPrincipal = Depends(_read),
):
    docs, total = await service.list_payments(
        principal, ref_doc_id, page.skip, page.page_size
    )
    return envelope(to_api(docs), page_meta(page.page, page.page_size, total))


@router.post("/payments", status_code=201)
async def create_payment(
    body: PaymentCreate, principal: ClientPrincipal = Depends(_write)
):
    return envelope(to_api(await service.create_payment(principal, body)))


# --- reports -----------------------------------------------------------------

@router.get("/reports/trial-balance")
async def trial_balance(
    start: datetime | None = None,
    end: datetime | None = None,
    principal: ClientPrincipal = Depends(_read),
):
    return envelope(to_api(await service.trial_balance(principal, start, end)))


@router.get("/reports/pnl")
async def pnl(
    start: datetime | None = None,
    end: datetime | None = None,
    principal: ClientPrincipal = Depends(_read),
):
    return envelope(to_api(await service.pnl(principal, start, end)))


@router.get("/reports/balance-sheet")
async def balance_sheet(
    end: datetime | None = None,
    principal: ClientPrincipal = Depends(_read),
):
    return envelope(to_api(await service.balance_sheet(principal, end)))


@router.get("/reports/aging")
async def aging(
    type: str = Query(default="ar", pattern="^(ar|ap)$"),
    principal: ClientPrincipal = Depends(_read),
):
    return envelope(to_api(await service.aging(principal, type)))


# --- CSV import & export (§7 parity) -----------------------------------------
# accounts import + export; invoices/bills export-only (declared in csv_schema).
# Access is the per-tab CSV grant layered on finance READ (shared/csv_access.py).
csv_routes(router, module="finance", registry=CSV_ENTITIES)
