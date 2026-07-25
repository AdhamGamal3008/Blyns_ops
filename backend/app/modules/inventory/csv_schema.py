"""Inventory's CSV column specs (docs/modules/INVENTORY.md §7).

Four data sets, and unlike CRM's they do not all behave the same way — the
module's own rules decide:

* **products / warehouses** — plain documents, upserted on their identifier.
  `key_fold=False`: a SKU is an exact identifier backed by a unique index, so
  matching it case-insensitively would let a re-import silently rename one.
* **movements** — the ledger is immutable (§2), so the import is append-only:
  a repeated file means more entries, never an edit of old ones. Rows are
  written through `service.create_movement`, not inserted, because posting a
  movement also claims stock atomically and can be refused for insufficient
  stock. A raw insert would move the ledger without moving `stock_levels` and
  quietly break acceptance #1 ("on-hand equals the signed sum of the ledger").
* **stock_levels** — derived from the ledger and never edited directly (§2), so
  it is export-only. Correcting stock means posting an `adjustment`.

Products and warehouses are referenced by SKU and warehouse code rather than
ObjectId, since those are what a person has in a spreadsheet.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.modules.inventory import repository as repo
from app.modules.inventory.models import MOVEMENT_TYPES, UNITS, MovementCreate
from app.shared.csv_io import CsvField
from app.shared.csv_spec import CsvEntity, CsvRef, RowRejected

# --- references --------------------------------------------------------------

PRODUCT_REF = CsvRef(
    key="sku_ref", doc_key="product_id", collection=repo.PRODUCTS,
    match_field="sku", label="Product", fold_case=False,
)
WAREHOUSE_REF = CsvRef(
    key="warehouse_code", doc_key="warehouse_id", collection=repo.WAREHOUSES,
    match_field="code", label="Warehouse", fold_case=False,
)
# stock_levels shows the product's name as well as its SKU, which needs a second
# lookup against the same collection on a different field.
PRODUCT_NAME_REF = CsvRef(
    key="product_name", doc_key="product_id", collection=repo.PRODUCTS,
    match_field="name", label="Product",
)


def _record_fields() -> tuple[CsvField, ...]:
    """Export-only provenance columns — the database owns these."""
    return (
        CsvField(key="id", header="Record ID", importable=False),
        CsvField(key="created_at", header="Created at", kind="datetime",
                 importable=False),
        CsvField(key="updated_at", header="Updated at", kind="datetime",
                 importable=False),
    )


# --- products ----------------------------------------------------------------

PRODUCTS = CsvEntity(
    name="products",
    label="Products",
    collection=repo.PRODUCTS,
    natural_key=("sku",),
    key_fold=False,
    status_field="is_active",
    status_choices=("yes", "no"),
    search_fields=("sku", "name"),
    default_sort=("sku", 1),
    create_defaults={
        "unit": "pcs", "cost_price": 0.0, "sale_price": 0.0, "currency": "USD",
        "reorder_point": 0.0, "reorder_qty": 0.0, "is_active": True,
    },
    fields=(
        CsvField(key="sku", header="SKU", required=True, example="SKU-001",
                 hint="Identifies the product — a matching SKU updates it "
                      "instead of adding a second one. Case-sensitive."),
        CsvField(key="name", header="Name", required=True, example="Oak plank 2m"),
        CsvField(key="description", header="Description", example="Kiln-dried"),
        CsvField(key="category", header="Category", example="Timber"),
        CsvField(key="unit", header="Unit", kind="enum", choices=UNITS,
                 example="pcs"),
        CsvField(key="barcode", header="Barcode", example="5901234123457"),
        CsvField(key="cost_price", header="Cost price", kind="float",
                 example="12.50"),
        CsvField(key="sale_price", header="Sale price", kind="float",
                 example="24.00"),
        CsvField(key="currency", header="Currency", example="USD"),
        CsvField(key="reorder_point", header="Reorder point", kind="float",
                 example="20",
                 hint="Stock at or below this flags the item as low."),
        CsvField(key="reorder_qty", header="Reorder qty", kind="float",
                 example="100"),
        CsvField(key="is_active", header="Active", kind="bool", example="yes"),
        *_record_fields(),
    ),
)


# --- warehouses --------------------------------------------------------------

WAREHOUSES = CsvEntity(
    name="warehouses",
    label="Warehouses",
    collection=repo.WAREHOUSES,
    natural_key=("code",),
    key_fold=False,
    status_field="is_active",
    status_choices=("yes", "no"),
    search_fields=("code", "name"),
    default_sort=("code", 1),
    create_defaults={"is_active": True},
    fields=(
        CsvField(key="code", header="Code", required=True, example="WH1",
                 hint="Identifies the warehouse on re-import."),
        CsvField(key="name", header="Name", required=True, example="Main WH"),
        CsvField(key="address.street", header="Address", example="1 Dock Road"),
        CsvField(key="address.city", header="City", example="Springfield"),
        CsvField(key="address.country", header="Country", example="USA"),
        CsvField(key="is_active", header="Active", kind="bool", example="yes"),
        *_record_fields(),
    ),
)


# --- movements (the ledger) --------------------------------------------------

def _guard_movement(doc: dict, existing: dict | None) -> None:
    """The rules create_movement enforces, checked before anything is posted so
    a bad row is reported rather than half-applied."""
    mtype = doc.get("type")
    qty = doc.get("qty")

    if mtype == "adjustment" and not (doc.get("note") or "").strip():
        raise RowRejected(
            "An adjustment requires a note explaining it.", column="Note",
        )
    if qty in (None, 0):
        raise RowRejected("Movement qty cannot be zero.", column="Qty")
    if mtype in ("receipt", "issue") and isinstance(qty, int | float) and qty < 0:
        raise RowRejected(
            f"A {mtype} takes a positive qty; its direction comes from the type "
            "(+receipt, -issue). Use an adjustment to correct downwards.",
            column="Qty",
        )
    if not doc.get("product_id"):
        raise RowRejected("A movement needs a product SKU.", column="SKU")
    if not doc.get("warehouse_id"):
        raise RowRejected("A movement needs a warehouse code.", column="Warehouse")


async def _post_movement(principal: Any, doc: dict) -> Any:
    """Write one ledger row through the module's own service.

    This is the whole reason `writer` exists. `create_movement` claims stock
    with an atomic conditional `$inc`, refuses to go negative unless the company
    allows it, and unwinds the claim if the ledger write fails. Inserting the
    document directly would skip all three and leave `stock_levels` describing a
    quantity the ledger disagrees with.
    """
    from app.modules.inventory import service as inventory_service

    return await inventory_service.create_movement(principal, MovementCreate(
        product_id=str(doc["product_id"]),
        warehouse_id=str(doc["warehouse_id"]),
        type=doc["type"],
        qty=float(doc["qty"]),
        note=doc.get("note"),
        occurred_at=doc.get("occurred_at") or datetime.now(UTC),
        ref_module="manual",
        ref_doc_id=None,
    ))


MOVEMENTS = CsvEntity(
    name="movements",
    label="Movements",
    collection=repo.MOVEMENTS,
    # No natural key: the ledger is immutable, so every row is a new entry and
    # there is nothing to match an existing one against.
    append_only=True,
    writer=_post_movement,
    row_guard=_guard_movement,
    status_field="type",
    status_choices=MOVEMENT_TYPES,
    date_fields=("occurred_at",),
    default_sort=("occurred_at", -1),
    refs=(PRODUCT_REF, WAREHOUSE_REF),
    fields=(
        CsvField(key="sku_ref", header="SKU", required=True, example="SKU-001",
                 hint="Must already exist — import Products first."),
        CsvField(key="warehouse_code", header="Warehouse", required=True,
                 example="WH1", hint="Must already exist."),
        CsvField(key="type", header="Type", kind="enum",
                 # A transfer is a *pair* of ledger rows created together by
                 # POST /transfers; one row of a pair would unbalance the ledger.
                 import_choices=("receipt", "issue", "adjustment"),
                 choices=MOVEMENT_TYPES, required=True, example="receipt",
                 hint="Transfers are made in the app, not here — they post two "
                      "balanced entries at once."),
        CsvField(key="qty", header="Qty", kind="float", required=True,
                 example="25",
                 hint="Always positive for receipt/issue — the direction comes "
                      "from the type. An adjustment may be negative."),
        CsvField(key="note", header="Note", example="Opening balance",
                 hint="Required for an adjustment."),
        CsvField(key="occurred_at", header="Occurred at", kind="datetime",
                 example="2026-07-01",
                 hint="Defaults to now. ISO format: YYYY-MM-DD."),
        CsvField(key="ref.module", header="Source", importable=False),
        CsvField(key="ref.doc_id", header="Source document", importable=False),
        CsvField(key="id", header="Record ID", importable=False),
        CsvField(key="created_at", header="Recorded at", kind="datetime",
                 importable=False),
    ),
)


# --- stock levels (derived — export only) ------------------------------------

STOCK_LEVELS = CsvEntity(
    name="stock-levels",
    label="Stock levels",
    collection=repo.STOCK_LEVELS,
    importable=False,
    date_fields=("updated_at",),
    default_sort=("on_hand", 1),
    refs=(PRODUCT_REF, PRODUCT_NAME_REF, WAREHOUSE_REF),
    fields=(
        CsvField(key="sku_ref", header="SKU", importable=False),
        CsvField(key="product_name", header="Product", importable=False),
        CsvField(key="warehouse_code", header="Warehouse", importable=False),
        CsvField(key="on_hand", header="On hand", kind="float", importable=False),
        CsvField(key="updated_at", header="Updated at", kind="datetime",
                 importable=False),
    ),
)


ENTITIES: dict[str, CsvEntity] = {
    e.name: e for e in (PRODUCTS, WAREHOUSES, MOVEMENTS, STOCK_LEVELS)
}
