# MODULE: CRM

RBAC resource: `crm`. Routes under `/api/v1/crm`. Tenant-bound.

---

## 1. Entities

### Account (company/customer)
```json
{ "_id":"…","name":"Globex","industry":"…","website":"…",
  "owner_id":"user…","address":{},"phone":"…",
  "status":"prospect|customer|inactive","tags":["…"],
  "created_at":"…","updated_at":"…","created_by":"…","is_deleted":false }
```

### Contact (person, optionally linked to an account)
```json
{ "_id":"…","account_id":"… | null","first_name":"…","last_name":"…",
  "email":"…","phone":"…","title":"…","owner_id":"…","tags":["…"] }
```

### Lead (unqualified)
```json
{ "_id":"…","name":"…","email":"…","phone":"…","source":"…",
  "status":"new|contacted|qualified|unqualified|converted",
  "owner_id":"…","converted_to":{"account_id":null,"contact_id":null,"deal_id":null} }
```

### Deal / Opportunity
```json
{ "_id":"…","title":"…","account_id":"…","contact_id":"…",
  "pipeline":"default","stage":"new|qualified|proposal|negotiation|won|lost",
  "amount":0,"currency":"USD","probability_pct":0,
  "expected_close_date":"…","owner_id":"…","lost_reason":null,
  "created_at":"…","updated_at":"…","created_by":"…","is_deleted":false }
```

### Activity (call/meeting/note/task on any CRM entity)
```json
{ "_id":"…","entity_ref":{"type":"account|contact|lead|deal","id":"…"},
  "type":"call|email|meeting|note|task","subject":"…","body":"…",
  "due_at":"… | null","done":false,"owner_id":"…","created_at":"…" }
```

---

## 2. Behavior

- **Pipeline:** deals move through ordered `stage`s; store stage-change history in
  activity/audit. `won`/`lost` are terminal; `lost` requires `lost_reason`.
- **Lead conversion:** converting a lead creates/links account + contact + deal
  atomically and stamps `converted_to`.
- **Ownership:** every record has an `owner_id`; list views support "mine vs all"
  filters. (Row-level restriction by owner is optional and configured in
  Settings; default is tenant-wide visibility for READ users.)
- **KPIs:** open deals count + pipeline value feed dashboard.
- Scheduled `activity.due_at` and deal `expected_close_date` feed the calendar.
- All mutations write `activity_log` (`crm.deal.stage_changed`, etc.).

---

## 3. API surface

```
GET/POST/PATCH/DELETE   /api/v1/crm/accounts[/{id}]
GET/POST/PATCH/DELETE   /api/v1/crm/contacts[/{id}]
GET/POST/PATCH/DELETE   /api/v1/crm/leads[/{id}]
POST                    /api/v1/crm/leads/{id}/convert
GET/POST/PATCH/DELETE   /api/v1/crm/deals[/{id}]
PATCH                   /api/v1/crm/deals/{id}/stage
GET/POST/PATCH/DELETE   /api/v1/crm/activities[/{id}]
GET                     /api/v1/crm/pipeline          # deals grouped by stage w/ totals

GET   /api/v1/crm/export/{entity}/fields    # columns + filters (drives the UI)
GET   /api/v1/crm/export/{entity}           # text/csv, column- and filter-scoped
GET   /api/v1/crm/import/{entity}/template  # text/csv, headers to fill in
POST  /api/v1/crm/import/{entity}           # multipart; mode=validate|commit
```
Guarded: READ for GET, WRITE for mutations.

## 4. Seed (`modules/crm/seed.py`)
Indexes: `accounts.status`, `contacts.account_id`, `contacts.email`,
`leads.status`, `deals (stage, expected_close_date)`, `deals.account_id`,
`activities.entity_ref.id`, `activities.due_at`.
Default: one `default` pipeline definition doc with ordered stages.

## 5. Calendar contribution
`deal_close` (expected_close_date), CRM `activity` (due_at).

## 6. Acceptance criteria
- Converting a lead produces linked account/contact/deal and marks the lead
  converted.
- Moving a deal to `lost` without a reason is rejected.
- Pipeline endpoint returns stage buckets with counts and summed amounts.
- `crm=NONE` users get `PERMISSION_DENIED` on all CRM routes and see no CRM
  activity/calendar entries.

---

## 7. CSV import & export

Bulk data movement for the four tabs: `accounts`, `contacts`, `leads`, `deals`.
Export is READ; import is WRITE.

### 7.1 One column spec, three consumers

Each entity declares its columns once (`modules/crm/csv_schema.py`, built on the
module-agnostic engine in `shared/`: `csv_io.py` reads and writes CSV,
`csv_spec.py` describes an entity, `csv_service.py` orchestrates, and
`csv_router.py` generates the four routes). That one list produces the import
template, the export column picker, and the import parser — so the template can
always be filled in and uploaded, and **any export re-imports cleanly**.

The engine is shared, not copied: Inventory runs the same code (see
`INVENTORY.md` §7), which is also where its extensions live — export-only and
append-only data sets, and entities whose writes must go through their module's
service.

A few columns are export-only (`Record ID`, `Created at`, `Updated at`,
`Closed at`): the database owns them, and letting a file name a record's id
would let one file address a row it was never given.

### 7.2 Relationship columns

Nobody hand-types an ObjectId, so references are written as human values and
resolved by lookup at import:

| Column | Resolves to | Looked up in |
|---|---|---|
| `Account` | `account_id` | `crm_accounts.name` (case-insensitive) |
| `Contact email` | `contact_id` | `contacts.email` |
| `Owner email` | `owner_id` | tenant `users.email` |

An unresolvable value is a **row error, never a silently created record** — a
typo must not spawn a phantom account. Blank owner means the importing user.

### 7.3 Import

`POST /crm/import/{entity}` takes a multipart `file` plus `mode`:

- `mode=validate` — parse, resolve, check, and report. **Writes nothing.**
- `mode=commit` — the same pass, then applied.

The client posts the same file twice, so the server holds no half-finished
import state. The report carries `rows / created / updated / failed`, the
recognised and ignored columns, and every row error as
`{row, column, value, message}` (row numbers are 1-based as the user sees them:
the header is row 1). Errors are capped at 500 with `errors_truncated`.

**Rows that fail are skipped; the rest still import.** A row with even one bad
cell is held out entirely — a half-read row never reaches the database.

**Upsert on a natural key**, so a re-import updates rather than duplicates:

| Entity | Key |
|---|---|
| accounts | `Name` (case-insensitive) |
| contacts | `Email` |
| leads | `Email` |
| deals | `Title` + `Account` |

A row whose key columns are blank can never match, so it is always created. A
key repeated inside one file updates the record its first occurrence created.
Soft-deleted records are neither matched nor resurrected.

Two rules make round-tripping safe:

1. **A column absent from the file is never touched.** Export three columns,
   edit them, re-import — the other fields keep their stored values.
2. **A blank cell means "nothing supplied", not "erase this".** On create the
   field's default applies; on update the stored value stands. Clearing a field
   is done in the UI, where the intent is unambiguous.

**A spreadsheet cannot do what the API forbids.** The import applies the same
rules service.py does: a converted lead is frozen, `converted` is not an
importable lead status (conversion is `POST /leads/{id}/convert`, which builds
the linked records), a terminal deal cannot be reopened, and a `lost` deal needs
a reason.

Limits are config-driven: `ERP_MAX_IMPORT_MB` (5) and `ERP_MAX_IMPORT_ROWS`
(5000). Dates are **ISO-8601 only** — `03/04/2026` means two different days
either side of the Atlantic, so it is rejected with a message naming the format
rather than silently misread.

### 7.4 Export

`GET /crm/export/{entity}` streams `text/csv` in batches, filtered by:

- `fields` — comma-separated column keys; omitted means every column. Output is
  always in spec order, so the same selection yields the same file.
- `status` — the entity's status column (`stage` for deals).
- `date_field` + `date_from` + `date_to` — the range is inclusive of `date_to`.
  Valid date columns per entity come from `/export/{entity}/fields`.
- `owner=mine`, `q`, `account_id`.

Everything is validated **before** the response starts streaming — once bytes
are on the wire an error can no longer be reported. Soft-deleted rows never
appear.

### 7.5 Audit

An import writes **one** `crm.import.completed` activity entry for the whole
file — with the entity, filename and counts — not one per row. A `validate` run
writes nothing at all.

### 7.6 Acceptance criteria
- Every template's headers are exactly the entity's importable columns, and a
  downloaded template can be filled in and uploaded without editing headings.
- Exporting and re-importing without edits reports `0 created, N updated` and
  leaves the record count unchanged.
- A file with bad rows imports the good ones and reports each bad row with its
  spreadsheet line number and the reason.
- `mode=validate` writes nothing.
- Re-importing the same file a second time updates instead of duplicating.
- An unknown `Account` value fails that row without creating an account.
- A file missing a required column is rejected whole, with the column named.
- Import cannot mark a lead `converted`, edit a converted lead, reopen a
  terminal deal, or set a deal `lost` without a reason.
- `crm=READ` can export and download templates but gets `PERMISSION_DENIED` on
  import; `crm=NONE` is denied on all four routes.
