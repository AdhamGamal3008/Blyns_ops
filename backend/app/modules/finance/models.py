"""Finance module payloads (docs/modules/FINANCE.md §1)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

AccountType = Literal["asset", "liability", "equity", "income", "expense"]
PaymentMethod = Literal["cash", "bank", "other"]
PaymentType = Literal["customer_payment", "vendor_payment"]
RefDocType = Literal["invoice", "bill"]


class AccountCreate(BaseModel):
    code: str = Field(min_length=1, max_length=16)
    name: str = Field(min_length=1)
    type: AccountType
    parent_id: str | None = None
    is_active: bool = True
    currency: str = Field(default="USD", min_length=3, max_length=3)


class AccountPatch(BaseModel):
    code: str | None = Field(default=None, min_length=1, max_length=16)
    name: str | None = Field(default=None, min_length=1)
    type: AccountType | None = None
    parent_id: str | None = None
    is_active: bool | None = None
    currency: str | None = Field(default=None, min_length=3, max_length=3)


class JournalLine(BaseModel):
    account_id: str
    debit: float = Field(default=0, ge=0)
    credit: float = Field(default=0, ge=0)
    description: str | None = None


class JournalEntryCreate(BaseModel):
    """A manual entry. Must balance (§1 invariant) — the service enforces it."""

    date: datetime | None = None
    memo: str | None = None
    lines: list[JournalLine] = Field(min_length=2)


class DocLine(BaseModel):
    """An invoice/bill line.

    `product_id` is not in the spec's §1 line shape, but acceptance #5 requires
    posting an `inventory_issue=true` invoice to reduce on-hand "by the invoiced
    quantity" — which is impossible without knowing which product. It stays
    optional: a service line simply has none.
    """

    description: str = Field(min_length=1)
    qty: float = Field(default=1, gt=0)
    unit_price: float = Field(default=0, ge=0)
    tax_rate: float = Field(default=0, ge=0, le=100)
    product_id: str | None = None


class CustomerRef(BaseModel):
    crm_account_id: str | None = None  # FINANCE.md §1 — CRM's `crm_accounts`
    name: str = Field(min_length=1)


class InvoiceCreate(BaseModel):
    customer_ref: CustomerRef
    issue_date: datetime | None = None
    due_date: datetime
    lines: list[DocLine] = Field(min_length=1)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    inventory_issue: bool = False
    # which warehouse an inventory_issue draws from; defaults to the seeded Main WH
    warehouse_id: str | None = None
    notes: str | None = None


class InvoicePatch(BaseModel):
    """Drafts only — a posted document is corrected by voiding it (§2)."""

    customer_ref: CustomerRef | None = None
    issue_date: datetime | None = None
    due_date: datetime | None = None
    lines: list[DocLine] | None = None
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    inventory_issue: bool | None = None
    warehouse_id: str | None = None
    notes: str | None = None


class VendorRef(BaseModel):
    crm_account_id: str | None = None
    name: str = Field(min_length=1)


class BillCreate(BaseModel):
    vendor_ref: VendorRef
    issue_date: datetime | None = None
    due_date: datetime
    lines: list[DocLine] = Field(min_length=1)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    notes: str | None = None


class BillPatch(BaseModel):
    vendor_ref: VendorRef | None = None
    issue_date: datetime | None = None
    due_date: datetime | None = None
    lines: list[DocLine] | None = None
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    notes: str | None = None


class PaymentCreate(BaseModel):
    type: PaymentType
    ref_doc_type: RefDocType
    ref_doc_id: str
    amount: float = Field(gt=0)
    date: datetime | None = None
    method: PaymentMethod = "bank"
    note: str | None = None


class VoidBody(BaseModel):
    reason: str = Field(min_length=1)
