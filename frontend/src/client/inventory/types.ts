// Shared shapes for the Inventory section (docs/modules/INVENTORY.md §1).

// Mongo is schemaless: documents written before a field existed simply lack it,
// and a TS type cannot enforce otherwise at runtime. Anything the API may omit
// on an older doc is optional here, and callers default it — the server's
// low-stock view already does the same (`.get("unit", "pcs")`).
export interface Product {
  id: string;
  sku: string;
  name: string;
  category?: string | null;
  unit?: string;
  cost_price?: number;
  sale_price?: number;
  currency?: string;
  reorder_point?: number;
  reorder_qty?: number;
  is_active: boolean;
}

export const DEFAULT_UNIT = "pcs";

export interface Warehouse {
  id: string;
  name: string;
  code: string;
  is_active: boolean;
}

export interface StockLevel {
  id: string;
  product_id: string;
  warehouse_id: string;
  on_hand: number;
}

export interface Movement {
  id: string;
  product_id: string;
  warehouse_id: string;
  type: string;
  qty: number;
  note?: string | null;
  occurred_at: string;
  ref?: { module: string; doc_id: string | null };
}

export interface LowStockRow {
  product_id: string;
  warehouse_id: string;
  sku: string;
  name: string;
  on_hand: number;
  reorder_point: number;
  reorder_qty: number;
  unit: string;
}
