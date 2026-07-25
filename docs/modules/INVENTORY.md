# MODULE: Inventory Management

RBAC resource: `inventory`. Routes under `/api/v1/inventory`. Tenant-bound.
Stock levels are **derived from movements** — never edited directly — so the
ledger is always auditable.

---

## 1. Entities

### Product / Item
```json
{ "_id":"…","sku":"SKU-001","name":"…","description":"…",
  "category":"…","unit":"pcs|kg|box","barcode":"…",
  "cost_price":0,"sale_price":0,"currency":"USD",
  "reorder_point":0,"reorder_qty":0,"is_active":true,
  "created_at":"…","updated_at":"…","created_by":"…","is_deleted":false }
```

### Warehouse / Location
```json
{ "_id":"…","name":"Main WH","code":"WH1","address":{},"is_active":true }
```

### Stock Movement (immutable ledger entry)
```json
{ "_id":"…","product_id":"…","warehouse_id":"…",
  "type":"receipt|issue|transfer|adjustment",
  "qty":10,                          // signed: +receipt, -issue
  "ref":{"module":"finance|manual|transfer","doc_id":"… | null"},
  "note":"…","occurred_at":"…","created_by":"…" }
```

### Stock Level (derived cache: product × warehouse)
```json
{ "_id":"…","product_id":"…","warehouse_id":"…","on_hand":0,"updated_at":"…" }
```

---

## 2. Behavior

- **On-hand** = sum of movement `qty` for a product/warehouse. Maintain a
  `stock_levels` cache updated transactionally with each movement (recomputable
  from the ledger for integrity checks).
- **Receipts** increase, **issues** decrease, **transfers** create a paired
  issue+receipt across two warehouses, **adjustments** correct discrepancies with
  a mandatory `note`.
- **Negative stock:** rejected by default (`INSUFFICIENT_STOCK`); a company
  setting may allow it.
- **Low stock:** `on_hand <= reorder_point` flags the item; feeds dashboard KPI
  (`low_stock_items`) and optionally a calendar reorder reminder.
- Movements are **immutable**: corrections are new adjustment entries, never
  edits/deletes of past movements.
- All movements write `activity_log` (`inventory.receipt`, etc.).

**Manual updates via the UI.** Products are edited in place through
`PATCH /products/{id}` (audited `inventory.product.updated`). Stock is **not**
edited in place — the Stock tab's "Adjust" sets a row to a new on-hand *count*
by posting an `adjustment` for the difference, so the ledger stays the source of
truth and the correction is audited as `inventory.adjustment`. Both, like every
write, surface in the dashboard Activity panel.

---

## 3. API surface

```
GET/POST/PATCH/DELETE   /api/v1/inventory/products[/{id}]
GET/POST/PATCH/DELETE   /api/v1/inventory/warehouses[/{id}]
POST                    /api/v1/inventory/movements          # receipt/issue/adjustment
POST                    /api/v1/inventory/transfers          # paired movement
GET                     /api/v1/inventory/movements          # ledger, filterable
GET                     /api/v1/inventory/stock-levels       # on-hand by product/warehouse
GET                     /api/v1/inventory/low-stock

GET   /api/v1/inventory/export/{entity}/fields    # columns + filters (drives the UI)
GET   /api/v1/inventory/export/{entity}           # text/csv, column- and filter-scoped
GET   /api/v1/inventory/import/{entity}/template  # text/csv, headers to fill in
POST  /api/v1/inventory/import/{entity}           # multipart; mode=validate|commit
```
Guarded: READ for GET, WRITE for movement/product/warehouse changes.

## 4. Seed (`modules/inventory/seed.py`)
Indexes: `products.sku` (unique), `products.is_active`,
`movements (product_id, warehouse_id, occurred_at)`,
`stock_levels (product_id, warehouse_id)` (unique).
Default: one `Main WH` warehouse.

## 5. Integration with Finance
When Finance issues an invoice that ships goods, it may post an `issue` movement
referencing the invoice (`ref.module="finance"`). Keep the coupling one-way and
explicit; no hidden side effects.

## 6. Acceptance criteria
- On-hand equals the signed sum of the movement ledger for every product/
  warehouse.
- Issuing more than on-hand is rejected unless negative stock is enabled.
- Transfers move quantity between warehouses with a balanced pair of entries.
- Low-stock list matches `on_hand <= reorder_point`.

---

## 7. CSV import & export

Served by the **shared engine** (`app/shared/csv_io.py`, `csv_spec.py`,
`csv_service.py`, `csv_router.py`) — the same code CRM uses, driven by
`modules/inventory/csv_schema.py`. See `CRM.md` §7 for the parts common to every
module: one column spec drives template + export + parser, blank cells mean
"nothing supplied", absent columns are never touched, bad rows are reported
while good rows still import, and import is two-phase (`mode=validate` writes
nothing; `mode=commit` applies).

What is **specific to Inventory** is that its four data sets do not behave
alike, because the module's own rules differ:

| entity | export | import | matching |
|---|---|---|---|
| `products` | ✓ | ✓ | upsert on `SKU` — **case-sensitive** |
| `warehouses` | ✓ | ✓ | upsert on `Code` — case-sensitive |
| `movements` | ✓ | ✓ | **append-only**, posted through the service |
| `stock-levels` | ✓ | ✗ | **derived — export only** |

### 7.1 Products and warehouses

Plain upserts. Matching is **case-sensitive**, unlike CRM's names: a SKU is an
exact identifier backed by a unique index, so folding case would let `sku-001`
silently rename `SKU-001` on the next import. A row whose SKU differs only in
case is therefore a different product.

### 7.2 Movements — append-only, and posted through the service

The ledger is immutable (§2), so **there is no natural key and nothing is ever
updated**: importing the same file twice records the movements twice. That is
the correct reading — the same receipt happening again is a second receipt.

Rows are written by `service.create_movement`, **never inserted directly**.
This is not a stylistic preference: posting a movement also claims stock with an
atomic conditional `$inc`, refuses to go negative unless the company allows it,
and unwinds the claim if the ledger write fails. A raw insert would move the
ledger without moving `stock_levels` and silently break acceptance #1.

Consequences worth knowing:

- **Stock sufficiency is checked at commit, not at validate.** The dry run
  cannot know whether stock will be there, because claiming it *is* the check.
  A row refused for insufficient stock is reported like any other bad row, the
  rest of the file still posts, and the UI shows those failures in the result as
  well as the preview.
- `type` accepts `receipt`, `issue`, `adjustment`. **`transfer` is exportable
  but not importable** — a transfer is a *pair* of balanced entries written
  together by `POST /transfers`, and one row of a pair would unbalance the
  ledger.
- Every rule the API enforces applies: an adjustment needs a note, a receipt or
  issue takes a positive qty (direction comes from the type), qty cannot be
  zero, and the SKU and warehouse must already exist.

### 7.3 Stock levels — derived

Export-only. `on_hand` is computed from the ledger and never edited directly
(§2), so the import route refuses it with a 422 pointing at adjustments instead.
The export resolves ids to SKU, product name and warehouse code.

### 7.4 Acceptance criteria
- Importing movements moves `stock_levels`, and `/reconcile` still reports
  `consistent` afterwards — on-hand equals the signed sum of the ledger.
- Importing the same movement file twice creates two sets of entries, never an
  update.
- An issue beyond on-hand is refused for that row; the other rows still post.
- A CSV cannot post a `transfer`, an unnoted adjustment, a negative receipt, or
  a zero-qty movement.
- `stock-levels` has no template and refuses import.
- Product matching is case-sensitive: `sku-001` does not update `SKU-001`.
- `inventory=READ` can export but not import; `inventory=NONE` is denied on all
  four routes.
