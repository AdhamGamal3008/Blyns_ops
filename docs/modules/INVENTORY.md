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
