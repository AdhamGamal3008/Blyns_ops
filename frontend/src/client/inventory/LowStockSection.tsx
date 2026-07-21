// Low stock (§3 /low-stock) — the same predicate the dashboard's
// `low_stock_items` KPI counts, so the two always agree.

import { PackageCheck } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "../../shared/api";
import {
  CardHeader,
  DataState,
  DataTable,
  type DataTableColumn,
  EmptyState,
} from "../../shared/ui";
import type { LowStockRow } from "./types";
import styles from "./MovementsSection.module.css";

export function LowStockSection() {
  const [rows, setRows] = useState<LowStockRow[] | null>(null);
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    api<LowStockRow[]>("/inventory/low-stock")
      .then((r) => setRows(r.data)).catch(setError);
  }, []);

  const columns: DataTableColumn<LowStockRow>[] = [
    { key: "sku", header: "SKU", sortable: true },
    { key: "name", header: "Product", sortable: true, accessor: (r) => <b>{r.name}</b> },
    {
      key: "on_hand",
      header: "On hand",
      numeric: true,
      sortable: true,
      accessor: (r) => <b className={styles.out}>{r.on_hand} {r.unit}</b>,
      sortValue: (r) => r.on_hand,
    },
    { key: "reorder_point", header: "Reorder point", numeric: true, sortable: true },
    {
      key: "reorder_qty",
      header: "Suggested order",
      numeric: true,
      sortable: true,
      accessor: (r) => (r.reorder_qty > 0 ? <b>{r.reorder_qty}</b> : "—"),
      sortValue: (r) => r.reorder_qty,
    },
  ];

  return (
    <section>
      <CardHeader
        title="Low stock"
        description="Items at or below their reorder point. Products without a reorder point are not tracked here."
      />
      <DataState
        loading={!rows && !error}
        error={rows ? null : error}
        isEmpty={rows?.length === 0}
        empty={
          <EmptyState
            icon={<PackageCheck size={24} />}
            title="Nothing below its reorder point"
            description="Every tracked product is above its threshold."
          />
        }
      >
        <DataTable
          data={rows ?? []}
          columns={columns}
          getRowId={(r) => `${r.product_id}:${r.warehouse_id}`}
          searchPlaceholder="Search low stock…"
        />
      </DataState>
    </section>
  );
}
