// The movement ledger (§3 GET /movements) — read-only by design: movements are
// immutable (§2), so there is nothing to edit here. Corrections are new
// adjustment entries posted from the Stock tab.

import { useCallback, useEffect, useState } from "react";
import { api } from "../../shared/api";
import { Badge, Card, ErrorNote, Spinner } from "../../shared/ui";
import type { Movement, Product, Warehouse } from "./types";

const TONE: Record<string, string> = {
  receipt: "ok", issue: "warn", transfer: "neutral", adjustment: "danger",
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

  if (!movements) return <Spinner />;

  const product = (id: string) => products.find((p) => p.id === id);
  const warehouse = (id: string) => warehouses.find((w) => w.id === id);

  return (
    <Card title={`Movement ledger (${movements.length})`}>
      <ErrorNote error={error} />
      <table className="table">
        <thead>
          <tr>
            <th>When</th><th>Product</th><th>Warehouse</th><th>Type</th>
            <th style={{ textAlign: "right" }}>Qty</th><th>Note</th>
          </tr>
        </thead>
        <tbody>
          {movements.map((m) => (
            <tr key={m.id}>
              <td className="muted">
                {new Date(m.occurred_at).toLocaleString()}
              </td>
              <td>
                <b>{product(m.product_id)?.name ?? "—"}</b>
                <div className="muted">{product(m.product_id)?.sku}</div>
              </td>
              <td className="muted">{warehouse(m.warehouse_id)?.name ?? "—"}</td>
              <td><Badge tone={TONE[m.type] ?? "neutral"}>{m.type}</Badge></td>
              <td style={{ textAlign: "right" }}>
                <b className={m.qty < 0 ? "qty-out" : "qty-in"}>
                  {m.qty > 0 ? `+${m.qty}` : m.qty}
                </b>
              </td>
              <td className="muted">{m.note ?? "—"}</td>
            </tr>
          ))}
          {movements.length === 0 && (
            <tr><td colSpan={6} className="muted">No movements yet.</td></tr>
          )}
        </tbody>
      </table>
    </Card>
  );
}
