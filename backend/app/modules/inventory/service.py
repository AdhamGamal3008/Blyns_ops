"""Inventory business logic (docs/modules/INVENTORY.md §2).

The ledger is the truth: `movements` are immutable, and `stock_levels` is a
cache derived from them. Corrections are new `adjustment` entries, never edits
of past movements. Every movement writes the tenant activity_log (CLAUDE.md
rule 4).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from bson import ObjectId

from app.core.audit import write_activity
from app.core.errors import (
    INSUFFICIENT_STOCK,
    TENANT_NOT_FOUND,
    VALIDATION_ERROR,
    DomainError,
)
from app.modules.inventory import repository as repo
from app.modules.inventory.models import (
    MovementCreate,
    ProductCreate,
    ProductPatch,
    TransferCreate,
    WarehouseCreate,
    WarehousePatch,
)
from app.modules.inventory.permissions import ALLOW_NEGATIVE_STOCK_FIELD
from app.tenant.deps import ClientPrincipal


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
        module="inventory",
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


async def _allow_negative(principal: ClientPrincipal) -> bool:
    """§2: negative stock is rejected by default; a company setting may allow
    it. That setting is the tenant's own company_profile doc (SETTINGS.md §1.1)."""
    profile = await principal.tenant_db.company_profile.find_one(
        {"_id": "company_profile"}, {ALLOW_NEGATIVE_STOCK_FIELD: 1}
    )
    return bool((profile or {}).get(ALLOW_NEGATIVE_STOCK_FIELD, False))


# --- products ----------------------------------------------------------------

async def list_products(
    principal: ClientPrincipal, q: str | None, category: str | None,
    is_active: bool | None, skip: int, limit: int,
) -> tuple[list[dict], int]:
    query: dict[str, Any] = {}
    if q:
        query["$or"] = [
            {"name": {"$regex": q, "$options": "i"}},
            {"sku": {"$regex": q, "$options": "i"}},
        ]
    if category:
        query["category"] = category
    if is_active is not None:
        query["is_active"] = is_active
    return await repo.list_docs(
        principal.tenant_db, repo.PRODUCTS, query, skip, limit, sort=[("sku", 1)]
    )


async def create_product(principal: ClientPrincipal, payload: ProductCreate) -> dict:
    db = principal.tenant_db
    if await db[repo.PRODUCTS].find_one({"sku": payload.sku}):
        raise DomainError(VALIDATION_ERROR, f"SKU '{payload.sku}' already exists.", 409)
    doc = payload.model_dump()
    doc["created_by"] = str(principal.user["_id"])
    doc = await repo.insert(db, repo.PRODUCTS, doc)
    await _log(principal, "inventory.product.created",
               {"type": "product", "id": str(doc["_id"]), "label": doc["name"]},
               {"sku": doc["sku"]})
    return doc


async def patch_product(
    principal: ClientPrincipal, product_id: str, patch: ProductPatch
) -> dict:
    oid = _oid(product_id, "Product")
    product = await _require(principal, repo.PRODUCTS, oid, "Product")
    fields = {k: v for k, v in patch.model_dump(exclude_unset=True).items() if v is not None}
    if "sku" in fields and fields["sku"] != product["sku"]:
        clash = await principal.tenant_db[repo.PRODUCTS].find_one({"sku": fields["sku"]})
        if clash:
            raise DomainError(VALIDATION_ERROR, f"SKU '{fields['sku']}' already exists.", 409)
    if not fields:
        return product
    fields["updated_by"] = str(principal.user["_id"])
    updated = await repo.update(principal.tenant_db, repo.PRODUCTS, oid, fields)
    assert updated is not None
    await _log(principal, "inventory.product.updated",
               {"type": "product", "id": product_id, "label": updated["name"]},
               {"fields": [k for k in fields if k != "updated_by"]})
    return updated


async def delete_product(principal: ClientPrincipal, product_id: str) -> None:
    """Soft delete. Refused while stock is still on hand — the ledger must not
    describe a product the module pretends is gone."""
    oid = _oid(product_id, "Product")
    product = await _require(principal, repo.PRODUCTS, oid, "Product")
    held = await repo.any_stock_for_product(principal.tenant_db, oid)
    if held:
        raise DomainError(
            VALIDATION_ERROR,
            "Product still has stock on hand; issue or adjust it to zero first.",
            http_status=409,
            details={"on_hand": held["on_hand"]},
        )
    await repo.soft_delete(
        principal.tenant_db, repo.PRODUCTS, oid, str(principal.user["_id"])
    )
    await _log(principal, "inventory.product.deleted",
               {"type": "product", "id": product_id, "label": product["name"]})


# --- warehouses --------------------------------------------------------------

async def list_warehouses(
    principal: ClientPrincipal, skip: int, limit: int
) -> tuple[list[dict], int]:
    return await repo.list_docs(
        principal.tenant_db, repo.WAREHOUSES, {}, skip, limit, sort=[("code", 1)]
    )


async def create_warehouse(principal: ClientPrincipal, payload: WarehouseCreate) -> dict:
    db = principal.tenant_db
    if await db[repo.WAREHOUSES].find_one({"code": payload.code}):
        raise DomainError(
            VALIDATION_ERROR, f"Warehouse code '{payload.code}' already exists.", 409
        )
    doc = payload.model_dump()
    doc["created_by"] = str(principal.user["_id"])
    doc = await repo.insert(db, repo.WAREHOUSES, doc)
    await _log(principal, "inventory.warehouse.created",
               {"type": "warehouse", "id": str(doc["_id"]), "label": doc["name"]},
               {"code": doc["code"]})
    return doc


async def patch_warehouse(
    principal: ClientPrincipal, warehouse_id: str, patch: WarehousePatch
) -> dict:
    oid = _oid(warehouse_id, "Warehouse")
    warehouse = await _require(principal, repo.WAREHOUSES, oid, "Warehouse")
    fields = {k: v for k, v in patch.model_dump(exclude_unset=True).items() if v is not None}
    if "code" in fields and fields["code"] != warehouse["code"]:
        clash = await principal.tenant_db[repo.WAREHOUSES].find_one({"code": fields["code"]})
        if clash:
            raise DomainError(
                VALIDATION_ERROR, f"Warehouse code '{fields['code']}' already exists.", 409
            )
    if not fields:
        return warehouse
    fields["updated_by"] = str(principal.user["_id"])
    updated = await repo.update(principal.tenant_db, repo.WAREHOUSES, oid, fields)
    assert updated is not None
    await _log(principal, "inventory.warehouse.updated",
               {"type": "warehouse", "id": warehouse_id, "label": updated["name"]},
               {"fields": [k for k in fields if k != "updated_by"]})
    return updated


async def delete_warehouse(principal: ClientPrincipal, warehouse_id: str) -> None:
    oid = _oid(warehouse_id, "Warehouse")
    warehouse = await _require(principal, repo.WAREHOUSES, oid, "Warehouse")
    held = await principal.tenant_db[repo.STOCK_LEVELS].find_one(
        {"warehouse_id": oid, "on_hand": {"$ne": 0}}
    )
    if held:
        raise DomainError(
            VALIDATION_ERROR,
            "Warehouse still holds stock; move or issue it out first.",
            http_status=409,
        )
    await repo.soft_delete(
        principal.tenant_db, repo.WAREHOUSES, oid, str(principal.user["_id"])
    )
    await _log(principal, "inventory.warehouse.deleted",
               {"type": "warehouse", "id": warehouse_id, "label": warehouse["name"]})


# --- movements (§2) ----------------------------------------------------------

def _signed_qty(mtype: str, qty: float) -> float:
    """+receipt, -issue (§1). An adjustment carries its own sign — it corrects
    a discrepancy in either direction."""
    if mtype == "receipt":
        return abs(qty)
    if mtype == "issue":
        return -abs(qty)
    return qty  # adjustment


async def _post_movement(
    principal: ClientPrincipal, product: dict, warehouse: dict, mtype: str,
    signed: float, note: str | None, occurred_at: datetime,
    ref: dict, allow_negative: bool,
) -> dict:
    """Claim the stock, then write the immutable ledger entry.

    The claim is atomic and comes first so two concurrent issues can't both pass
    a check and drive on_hand negative. If the ledger write then fails we undo
    the claim, so the cache can never drift from the ledger (acceptance #1) —
    the same compensating idiom as the control-plane seat claim.
    """
    db = principal.tenant_db
    claimed = await repo.claim_stock(
        db, product["_id"], warehouse["_id"], signed, allow_negative
    )
    if not claimed:
        current = await repo.on_hand(db, product["_id"], warehouse["_id"])
        raise DomainError(
            INSUFFICIENT_STOCK,
            f"Only {current:g} on hand in {warehouse['name']}; cannot move {-signed:g}.",
            http_status=409,
            details={
                "product_id": str(product["_id"]),
                "warehouse_id": str(warehouse["_id"]),
                "on_hand": current, "requested": -signed,
            },
        )
    try:
        movement = await repo.insert(db, repo.MOVEMENTS, {
            "product_id": product["_id"],
            "warehouse_id": warehouse["_id"],
            "type": mtype,
            "qty": signed,
            "ref": ref,
            "note": note,
            "occurred_at": occurred_at,
            "created_by": str(principal.user["_id"]),
        })
    except Exception:
        await repo.release_stock(db, product["_id"], warehouse["_id"], signed)
        raise
    return movement


async def create_movement(principal: ClientPrincipal, payload: MovementCreate) -> dict:
    if payload.type == "adjustment" and not (payload.note or "").strip():
        raise DomainError(
            VALIDATION_ERROR, "An adjustment requires a note explaining it.", 422
        )
    if payload.qty == 0:
        raise DomainError(VALIDATION_ERROR, "Movement qty cannot be zero.", 422)
    if payload.type in ("receipt", "issue") and payload.qty < 0:
        raise DomainError(
            VALIDATION_ERROR,
            f"A {payload.type} takes a positive qty; its direction comes from the type.",
            http_status=422,
        )

    product = await _require(
        principal, repo.PRODUCTS, _oid(payload.product_id, "Product"), "Product"
    )
    warehouse = await _require(
        principal, repo.WAREHOUSES, _oid(payload.warehouse_id, "Warehouse"), "Warehouse"
    )
    signed = _signed_qty(payload.type, payload.qty)
    movement = await _post_movement(
        principal, product, warehouse, payload.type, signed, payload.note,
        payload.occurred_at or datetime.now(UTC),
        {"module": payload.ref_module, "doc_id": payload.ref_doc_id},
        await _allow_negative(principal),
    )
    await _log(principal, f"inventory.{payload.type}",
               {"type": "product", "id": str(product["_id"]), "label": product["name"]},
               {"qty": signed, "warehouse": warehouse["name"],
                "on_hand": await repo.on_hand(
                    principal.tenant_db, product["_id"], warehouse["_id"])})
    return movement


async def create_transfer(principal: ClientPrincipal, payload: TransferCreate) -> dict:
    """§2: a transfer is a paired issue+receipt across two warehouses.

    The issue is claimed first; if the receipt side fails, the issue is unwound
    so a transfer never leaves stock in limbo (acceptance #3).
    """
    if payload.from_warehouse_id == payload.to_warehouse_id:
        raise DomainError(
            VALIDATION_ERROR, "Source and destination warehouse must differ.", 422
        )
    product = await _require(
        principal, repo.PRODUCTS, _oid(payload.product_id, "Product"), "Product"
    )
    src = await _require(
        principal, repo.WAREHOUSES, _oid(payload.from_warehouse_id, "Warehouse"),
        "Source warehouse",
    )
    dst = await _require(
        principal, repo.WAREHOUSES, _oid(payload.to_warehouse_id, "Warehouse"),
        "Destination warehouse",
    )
    occurred_at = payload.occurred_at or datetime.now(UTC)
    ref: dict = {"module": "transfer", "doc_id": None}
    allow_negative = await _allow_negative(principal)

    out = await _post_movement(
        principal, product, src, "transfer", -payload.qty, payload.note,
        occurred_at, ref, allow_negative,
    )
    try:
        into = await _post_movement(
            principal, product, dst, "transfer", payload.qty, payload.note,
            occurred_at, ref, allow_negative,
        )
    except Exception:
        # unwind the issue side: drop its ledger row and give the stock back
        await principal.tenant_db[repo.MOVEMENTS].delete_one({"_id": out["_id"]})
        await repo.release_stock(
            principal.tenant_db, product["_id"], src["_id"], -payload.qty
        )
        raise

    # tie the pair together so the ledger shows they belong to one transfer
    for doc, other in ((out, into), (into, out)):
        await principal.tenant_db[repo.MOVEMENTS].update_one(
            {"_id": doc["_id"]},
            {"$set": {"ref.doc_id": str(other["_id"]), "transfer_pair_id": other["_id"]}},
        )

    await _log(principal, "inventory.transfer",
               {"type": "product", "id": str(product["_id"]), "label": product["name"]},
               {"qty": payload.qty, "from": src["name"], "to": dst["name"]})
    return {
        "product_id": str(product["_id"]),
        "qty": payload.qty,
        "from_warehouse_id": str(src["_id"]),
        "to_warehouse_id": str(dst["_id"]),
        "issue_movement_id": str(out["_id"]),
        "receipt_movement_id": str(into["_id"]),
    }


async def list_movements(
    principal: ClientPrincipal, product_id: str | None, warehouse_id: str | None,
    mtype: str | None, skip: int, limit: int,
) -> tuple[list[dict], int]:
    query: dict[str, Any] = {}
    if product_id:
        query["product_id"] = _oid(product_id, "Product")
    if warehouse_id:
        query["warehouse_id"] = _oid(warehouse_id, "Warehouse")
    if mtype:
        query["type"] = mtype
    db = principal.tenant_db
    total = await db[repo.MOVEMENTS].count_documents(query)
    cursor = (
        db[repo.MOVEMENTS].find(query)
        .sort([("occurred_at", -1)]).skip(skip).limit(limit)
    )
    return await cursor.to_list(length=limit), total


# --- stock views -------------------------------------------------------------

async def list_stock_levels(
    principal: ClientPrincipal, product_id: str | None, warehouse_id: str | None,
    skip: int, limit: int,
) -> tuple[list[dict], int]:
    query: dict[str, Any] = {}
    if product_id:
        query["product_id"] = _oid(product_id, "Product")
    if warehouse_id:
        query["warehouse_id"] = _oid(warehouse_id, "Warehouse")
    return await repo.stock_levels(principal.tenant_db, query, skip, limit)


async def list_low_stock(principal: ClientPrincipal) -> list[dict]:
    """Acceptance #4 — the same predicate the dashboard KPI counts."""
    rows = await repo.low_stock(principal.tenant_db)
    return [
        {
            "product_id": str(r["product_id"]),
            "warehouse_id": str(r["warehouse_id"]),
            "sku": r["product"]["sku"],
            "name": r["product"]["name"],
            "on_hand": r["on_hand"],
            "reorder_point": r["product"]["reorder_point"],
            "reorder_qty": r["product"].get("reorder_qty", 0),
            "unit": r["product"].get("unit", "pcs"),
        }
        for r in rows
    ]


async def reconcile(principal: ClientPrincipal) -> dict:
    """Integrity check (§2): recompute every cached on_hand from the ledger and
    report any drift. Read-only — it reports, it does not silently rewrite."""
    db = principal.tenant_db
    drift: list[dict] = []
    checked = 0
    async for level in db[repo.STOCK_LEVELS].find({}):
        checked += 1
        actual = await repo.ledger_sum(db, level["product_id"], level["warehouse_id"])
        if abs(actual - float(level["on_hand"])) > 1e-9:
            drift.append({
                "product_id": str(level["product_id"]),
                "warehouse_id": str(level["warehouse_id"]),
                "cached_on_hand": float(level["on_hand"]),
                "ledger_sum": actual,
            })
    return {"checked": checked, "drift": drift, "consistent": not drift}
