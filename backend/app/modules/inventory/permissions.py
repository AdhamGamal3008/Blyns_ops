"""Inventory module RBAC surface + ledger vocabulary (docs/modules/INVENTORY.md).

RBAC resource: `inventory` — READ for GET, WRITE for products/warehouses and
any movement (§3).
"""

from __future__ import annotations

RESOURCE = "inventory"

# §1 movement types. `transfer` is only ever written as a paired issue+receipt
# by the transfers endpoint — never posted directly.
MOVEMENT_TYPES: list[str] = ["receipt", "issue", "transfer", "adjustment"]
DIRECT_MOVEMENT_TYPES: list[str] = ["receipt", "issue", "adjustment"]

UNITS: list[str] = ["pcs", "kg", "box"]

# Where the client-side "allow negative stock" switch lives (§2: "a company
# setting may allow it") — the tenant's company_profile doc, SETTINGS.md §1.1.
ALLOW_NEGATIVE_STOCK_FIELD = "allow_negative_stock"
