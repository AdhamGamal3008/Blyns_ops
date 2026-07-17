// Low stock (§3 /low-stock) — the same predicate the dashboard's
// `low_stock_items` KPI counts, so the two always agree.

import { useEffect, useState } from "react";
import { api } from "../../shared/api";
import { Card, ErrorNote, Spinner } from "../../shared/ui";
import type { LowStockRow } from "./types";

export function LowStockSection() {
  const [rows, setRows] = useState<LowStockRow[] | null>(null);
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    api<LowStockRow[]>("/inventory/low-stock")
      .then((r) => setRows(r.data)).catch(setError);
  }, []);

  if (!rows) return <Spinner />;

  return (
    <Card title={`Low stock (${rows.length})`}>
      <ErrorNote error={error} />
      <p className="muted" style={{ marginBottom: 12, fontSize: 13 }}>
        Items at or below their reorder point. Products without a reorder point
        are not tracked here.
      </p>
      <table className="table">
        <thead>
          <tr>
            <th>SKU</th><th>Product</th>
            <th style={{ textAlign: "right" }}>On hand</th>
            <th style={{ textAlign: "right" }}>Reorder point</th>
            <th style={{ textAlign: "right" }}>Suggested order</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={`${r.product_id}:${r.warehouse_id}`}>
              <td className="muted">{r.sku}</td>
              <td><b>{r.name}</b></td>
              <td style={{ textAlign: "right" }}>
                <b className="qty-out">{r.on_hand}</b>{" "}
                <span className="muted">{r.unit}</span>
              </td>
              <td style={{ textAlign: "right" }} className="muted">
                {r.reorder_point}
              </td>
              <td style={{ textAlign: "right" }}>
                {r.reorder_qty > 0
                  ? <b>{r.reorder_qty}</b>
                  : <span className="muted">—</span>}
              </td>
            </tr>
          ))}
          {rows.length === 0 && (
            <tr><td colSpan={5} className="muted">
              Nothing below its reorder point.
            </td></tr>
          )}
        </tbody>
      </table>
    </Card>
  );
}
