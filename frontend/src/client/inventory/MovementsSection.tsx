// The movement ledger (§3 GET /movements) — read-only by design: movements are
// immutable (§2), so there is nothing to edit here. Corrections are new
// adjustment entries posted from the Stock tab.

import { useCallback, useEffect, useState } from "react";
import { api } from "../../shared/api";
import {
  Badge,
  type BadgeTone,
  CardHeader,
  DataState,
  DataTable,
  type DataTableColumn,
} from "../../shared/ui";
import type { Movement, Product, Warehouse } from "./types";
import styles from "./MovementsSection.module.css";

const TONE: Record<string, BadgeTone> = {
  receipt: "success", issue: "warning", transfer: "info", adjustment: "danger",
};

export function MovementsSection() {
  const [movements, setMovements] = useState<Movement[] | null>(null);
  const [products, setProducts] = useState<Product[]>([]);
  const [warehouses, setWarehouses] = useState<Warehouse[]>([]);
  const [error, setError] = useState<unknown>(null);

  const load = useCallback(() => {
    api<Movement[]>("/inventory/movements?page_size=100")
      .then((r) => setMovements(r.data)).catch(setError);
    api<Product[]>("/inventory/products?page_size=100")
      .then((r) => setProducts(r.data)).catch(() => {});
    api<Warehouse[]>("/inventory/warehouses?page_size=100")
      .then((r) => setWarehouses(r.data)).catch(() => {});
  }, []);

  useEffect(load, [load]);

  const product = (id: string) => products.find((p) => p.id === id);
  const warehouse = (id: string) => warehouses.find((w) => w.id === id);

  const columns: DataTableColumn<Movement>[] = [
    {
      key: "occurred_at",
      header: "When",
      sortable: true,
      accessor: (m) => new Date(m.occurred_at).toLocaleString(),
      sortValue: (m) => m.occurred_at,
    },
    {
      key: "product",
      header: "Product",
      sortable: true,
      accessor: (m) => (
        <>
          <b>{product(m.product_id)?.name ?? "—"}</b>
          <div>{product(m.product_id)?.sku}</div>
        </>
      ),
      sortValue: (m) => product(m.product_id)?.name ?? "",
    },
    {
      key: "warehouse",
      header: "Warehouse",
      sortable: true,
      accessor: (m) => warehouse(m.warehouse_id)?.name ?? "—",
      sortValue: (m) => warehouse(m.warehouse_id)?.name ?? "",
    },
    {
      key: "type",
      header: "Type",
      sortable: true,
      accessor: (m) => <Badge tone={TONE[m.type] ?? "neutral"}>{m.type}</Badge>,
      sortValue: (m) => m.type,
    },
    {
      key: "qty",
      header: "Qty",
      numeric: true,
      sortable: true,
      accessor: (m) => (
        <b className={m.qty < 0 ? styles.out : styles.in}>
          {m.qty > 0 ? `+${m.qty}` : m.qty}
        </b>
      ),
      sortValue: (m) => m.qty,
    },
    { key: "note", header: "Note", accessor: (m) => m.note ?? "—" },
  ];

  return (
    <section>
      <CardHeader
        title="Movement ledger"
        description="Immutable by design — corrections are posted as new adjustments."
      />
      <DataState
        loading={!movements && !error}
        error={movements ? null : error}
        onRetry={load}
        isEmpty={movements?.length === 0}
        emptyTitle="No movements yet"
      >
        <DataTable
          data={movements ?? []}
          columns={columns}
          getRowId={(m) => m.id}
          searchPlaceholder="Search movements…"
        />
      </DataState>
    </section>
  );
}
