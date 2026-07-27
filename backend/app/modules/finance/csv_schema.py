"""Finance's CSV column specs (docs/modules/FINANCE.md §1, §7 parity with CRM/
Inventory).

Finance is a **double-entry ledger**, so only master data is safe to import; the
posted books are export-only:

* **accounts** — the chart of accounts is plain master data, upserted on its
  `code` (a stable, unique handle the posting engine already resolves by, and the
  same value a person keeps in a spreadsheet). `key_fold=False`: a code is an
  exact identifier backed by a unique index, so folding case on re-import could
  silently rename one. A parent account is referenced by its code, not its id.
  No `writer` is needed — creating an account is a plain insert with no posting
  side effects, so the CSV path produces exactly the document `create_account`
  would (same base fields, `parent_id` stored as an ObjectId).

* **invoices / bills** — **export-only**. A posted AR/AP document is the outcome
  of a balanced journal entry, carries a gap-free sequential number, and has a
  variable-length line array — none of which a spreadsheet row can safely
  round-trip. Editing them by CSV would let a file post to the ledger behind the
  balance check. Export gives a header-level register (number, party, dates,
  amounts, status) for reporting; create/edit stays in the app.

Journal entries and payments are intentionally omitted: they *are* the ledger, and
the trial-balance / P&L / aging report endpoints are their proper export surface.
"""

from __future__ import annotations

from app.modules.finance import repository as repo
from app.modules.finance.permissions import ACCOUNT_TYPES, INVOICE_STATUSES
from app.shared.csv_io import CsvField
from app.shared.csv_spec import CsvEntity, CsvRef

# --- references --------------------------------------------------------------

# A parent account is named by its code, and stored as the parent's ObjectId —
# exactly what create_account writes. Codes are exact, so never fold case.
ACCOUNT_PARENT_REF = CsvRef(
    key="parent_code", doc_key="parent_id", collection=repo.ACCOUNTS,
    match_field="code", label="Parent account", fold_case=False,
)


def _record_fields() -> tuple[CsvField, ...]:
    """Export-only provenance columns the database owns."""
    return (
        CsvField(key="id", header="Record ID", importable=False),
        CsvField(key="created_at", header="Created at", kind="datetime",
                 importable=False),
        CsvField(key="updated_at", header="Updated at", kind="datetime",
                 importable=False),
    )


# --- accounts (chart of accounts — import & export) --------------------------

ACCOUNTS = CsvEntity(
    name="accounts",
    label="Chart of accounts",
    collection=repo.ACCOUNTS,
    natural_key=("code",),
    key_fold=False,
    status_field="is_active",
    status_choices=("yes", "no"),
    search_fields=("code", "name"),
    default_sort=("code", 1),
    refs=(ACCOUNT_PARENT_REF,),
    # Mirror AccountCreate's Pydantic defaults so a CSV-written account is shaped
    # exactly like a POST-written one.
    create_defaults={"is_active": True, "currency": "USD", "parent_id": None},
    fields=(
        CsvField(key="code", header="Code", required=True, example="1000",
                 hint="Identifies the account — a matching code updates it "
                      "instead of adding a second one. Case-sensitive."),
        CsvField(key="name", header="Name", required=True, example="Cash"),
        CsvField(key="type", header="Type", kind="enum",
                 choices=tuple(ACCOUNT_TYPES), required=True, example="asset"),
        CsvField(key="parent_code", header="Parent code", example="1000",
                 hint="Code of the parent account, if any. It must already "
                      "exist — import parents first."),
        CsvField(key="currency", header="Currency", example="USD"),
        CsvField(key="is_active", header="Active", kind="bool", example="yes"),
        *_record_fields(),
    ),
)


# --- invoices (AR — export only) ---------------------------------------------

INVOICES = CsvEntity(
    name="invoices",
    label="Customer invoices",
    collection=repo.INVOICES,
    importable=False,
    status_field="status",
    status_choices=tuple(INVOICE_STATUSES),
    search_fields=("number", "customer_ref.name"),
    date_fields=("issue_date", "due_date", "created_at", "updated_at"),
    default_sort=("issue_date", -1),
    fields=(
        CsvField(key="number", header="Number", importable=False),
        CsvField(key="customer_ref.name", header="Customer", importable=False),
        CsvField(key="issue_date", header="Issue date", kind="datetime",
                 importable=False),
        CsvField(key="due_date", header="Due date", kind="datetime",
                 importable=False),
        CsvField(key="subtotal", header="Subtotal", kind="float", importable=False),
        CsvField(key="tax_total", header="Tax", kind="float", importable=False),
        CsvField(key="total", header="Total", kind="float", importable=False),
        CsvField(key="paid_amount", header="Paid", kind="float", importable=False),
        CsvField(key="status", header="Status", importable=False),
        CsvField(key="currency", header="Currency", importable=False),
        CsvField(key="id", header="Record ID", importable=False),
    ),
)


# --- bills (AP — export only; the mirror of invoices) ------------------------

BILLS = CsvEntity(
    name="bills",
    label="Vendor bills",
    collection=repo.BILLS,
    importable=False,
    status_field="status",
    status_choices=tuple(INVOICE_STATUSES),
    search_fields=("number", "vendor_ref.name"),
    date_fields=("issue_date", "due_date", "created_at", "updated_at"),
    default_sort=("issue_date", -1),
    fields=(
        CsvField(key="number", header="Number", importable=False),
        CsvField(key="vendor_ref.name", header="Vendor", importable=False),
        CsvField(key="issue_date", header="Issue date", kind="datetime",
                 importable=False),
        CsvField(key="due_date", header="Due date", kind="datetime",
                 importable=False),
        CsvField(key="subtotal", header="Subtotal", kind="float", importable=False),
        CsvField(key="tax_total", header="Tax", kind="float", importable=False),
        CsvField(key="total", header="Total", kind="float", importable=False),
        CsvField(key="paid_amount", header="Paid", kind="float", importable=False),
        CsvField(key="status", header="Status", importable=False),
        CsvField(key="currency", header="Currency", importable=False),
        CsvField(key="id", header="Record ID", importable=False),
    ),
)


ENTITIES: dict[str, CsvEntity] = {e.name: e for e in (ACCOUNTS, INVOICES, BILLS)}
