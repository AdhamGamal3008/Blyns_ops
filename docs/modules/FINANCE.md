# MODULE: Accounting & Finance

RBAC resource: `finance`. Routes under `/api/v1/finance`. Tenant-bound.
Double-entry ledger at the core; invoices/bills/payments post journal entries.
Depends on `INVENTORY.md` for goods-related invoices (optional coupling).

---

## 1. Entities

### Account (chart of accounts)
```json
{ "_id":"…","code":"1000","name":"Cash","type":"asset|liability|equity|income|expense",
  "parent_id":"… | null","is_active":true,"currency":"USD" }
```

### Journal Entry (double-entry; must balance)
```json
{ "_id":"…","date":"…","memo":"…","source":{"module":"invoice|bill|payment|manual","doc_id":"…"},
  "lines":[
    {"account_id":"…","debit":100,"credit":0,"description":"…"},
    {"account_id":"…","debit":0,"credit":100,"description":"…"}
  ],
  "posted":true,"created_by":"…","created_at":"…" }
```
Invariant: `sum(debit) == sum(credit)` per entry, else `UNBALANCED_ENTRY`.

### Customer Invoice (AR)
```json
{ "_id":"…","number":"INV-0001","customer_ref":{"crm_account_id":"… | null","name":"…"},
  "issue_date":"…","due_date":"…",
  "lines":[{"description":"…","qty":1,"unit_price":100,"tax_rate":0,"amount":100}],
  "subtotal":0,"tax_total":0,"total":0,"paid_amount":0,
  "status":"draft|sent|partly_paid|paid|void","currency":"USD",
  "inventory_issue":false }
```

### Vendor Bill (AP) — mirror of invoice for payables.

### Payment
```json
{ "_id":"…","type":"customer_payment|vendor_payment",
  "ref_doc":{"type":"invoice|bill","id":"…"},"amount":0,"date":"…",
  "method":"cash|bank|other","account_id":"…","created_by":"…" }
```

---

## 2. Behavior

- **Numbering:** invoices/bills get sequential per-tenant numbers
  (`INV-%04d`, `BILL-%04d`) from a counter doc; gaps not allowed on post.
- **Posting:** sending an invoice posts a balanced journal entry (Dr AR / Cr
  Income + tax). Recording a payment posts Dr Cash/Bank / Cr AR and updates
  `paid_amount`/`status`. Same pattern (mirrored) for bills.
- **Status math:** `paid_amount == 0` → sent; `0 < paid < total` → partly_paid;
  `paid >= total` → paid. Voiding reverses the journal entry (never deletes it).
- **Inventory link:** if `inventory_issue=true`, posting the invoice creates an
  inventory `issue` movement (`INVENTORY.md` §5).
- **Reports:**
  - Trial balance (sum debits/credits by account).
  - P&L (income − expense over a period).
  - Balance sheet (assets = liabilities + equity).
  - AR/AP aging (buckets by due date).
- **Due dates** feed the calendar; unpaid invoice total feeds dashboard KPI.
- All mutations write `activity_log` (`finance.invoice.sent`, etc.).

---

## 3. API surface

```
GET/POST/PATCH/DELETE   /api/v1/finance/accounts[/{id}]        # chart of accounts
GET/POST                /api/v1/finance/journal-entries        # manual entries (must balance)
GET                     /api/v1/finance/journal-entries/{id}
GET/POST/PATCH          /api/v1/finance/invoices[/{id}]
POST                    /api/v1/finance/invoices/{id}/send
POST                    /api/v1/finance/invoices/{id}/void
GET/POST/PATCH          /api/v1/finance/bills[/{id}]
POST                    /api/v1/finance/payments
GET                     /api/v1/finance/reports/trial-balance
GET                     /api/v1/finance/reports/pnl
GET                     /api/v1/finance/reports/balance-sheet
GET                     /api/v1/finance/reports/aging?type=ar|ap
```
Guarded: READ for GET/reports, WRITE for posting/payments. Finance is the module
most likely restricted to READ for many roles — enforce strictly.

## 4. Seed (`modules/finance/seed.py`)
Indexes: `accounts.code` (unique), `journal_entries.date`,
`journal_entries.source.doc_id`, `invoices.status`, `invoices.due_date`,
`bills.due_date`, `payments.ref_doc.id`.
Default: a starter chart of accounts (Cash, Bank, AR, AP, Sales Income, COGS,
Tax Payable, Owner Equity) + numbering counters.

## 5. Calendar contribution
`invoice_due` (invoices.due_date), `bill_due` (bills.due_date).

## 6. Acceptance criteria
- Every posted journal entry balances; unbalanced posts are rejected.
- Sending an invoice and recording full payment moves it to `paid` and produces
  two balanced journal entries.
- Trial balance nets to zero; balance sheet balances.
- Voiding produces a reversing entry and never removes the original.
- With `inventory_issue=true`, posting reduces on-hand by the invoiced quantity.
